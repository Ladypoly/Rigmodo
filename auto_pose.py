# SPDX-License-Identifier: GPL-3.0-or-later
"""Opt-in Auto Pose transactions, scoped G/R input, pins and a quiet pose panel."""
import json
import math
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator, PropertyGroup
from bpy_extras import view3d_utils
from mathutils import Matrix, Quaternion, Vector
from . import auto_pose_solver as solver, skeleton, twists

_sessions = set()
_keymaps = []
_draw_handle = None
PIN_BONES = ('Hips', 'LeftHand', 'RightHand', 'LeftFoot', 'RightFoot')


class AP_Settings(PropertyGroup):
    enabled: BoolProperty(name='Auto Pose', default=False)
    feet: BoolProperty(name='Keep feet planted', default=True,
                       description='Hold both ankle positions and rotations; the foot being moved is released')
    body_follow: BoolProperty(name='Body follows reach', default=True,
                              description='Allow spine, shoulders and pelvis to help reach the selected target')
    joint_limits: BoolProperty(name='Joint limits', default=True,
                               description='Apply conservative swing and twist limits; preserve the existing authored pose')
    pins: StringProperty(default='{}', options={'HIDDEN'})
    pin_mode: EnumProperty(name='Pin', items=[('POSITION', 'Position', 'Hold the joint in place'),
                                             ('FRAME', 'Position + rotation', 'Hold its complete orientation too')], default='POSITION')


def rig_of(context):
    rig = context.active_object
    return rig if rig and rig.type == 'ARMATURE' and context.mode == 'POSE' else None


def active_name(context):
    rig = rig_of(context)
    bone = rig.data.bones.active if rig else None
    return skeleton.canonical_name(bone.name) if bone and not bone.hide and rig.pose.bones[bone.name].select else ''


def pins_of(rig):
    try:
        pins = json.loads(rig.lc_auto_pose.pins)
        if not isinstance(pins, dict) or any(n not in PIN_BONES or mode not in {'POSITION', 'FRAME'} for n, mode in pins.items()):
            raise ValueError()
        return pins
    except (ValueError, TypeError):
        raise ValueError('Stored Auto Pose pins are invalid; clear pins and set them again') from None


def validate(context, rig):
    if not rig or rig.type != 'ARMATURE' or rig.library or rig.data.library or rig.override_library:
        raise ValueError('Auto Pose needs a local editable Rigmodo humanoid')
    mapping = {}
    for p in rig.pose.bones:
        n = skeleton.canonical_name(p.name)
        if n in mapping: raise ValueError('Ambiguous humanoid bone names')
        mapping[n] = p
        if any(not math.isfinite(v) for row in p.matrix_basis for v in row) or any(not math.isfinite(v) for row in p.bone.matrix_local for v in row):
            raise ValueError('Auto Pose needs finite rest and pose transforms')
        if any(not c.mute and c.influence > 0 for c in p.constraints):
            raise ValueError('Auto Pose currently needs a rig without active bone constraints')
        b = p.bone
        if not b.use_inherit_rotation or not b.use_local_location or b.inherit_scale != 'FULL':
            raise ValueError('Auto Pose needs standard rotation, location and scale inheritance')
        if max(abs(v - 1) for v in p.scale) > 1e-5:
            raise ValueError('Remove pose-bone scaling before Auto Pose')
        if n not in {'Root', 'Hips'} and p.location.length > 1e-5:
            raise ValueError('Remove translated non-root pose bones before Auto Pose')
        if n in solver.BODY and (any(p.lock_rotation) or p.lock_rotation_w or any(p.lock_location) and n == 'Hips'):
            raise ValueError('Unlock the humanoid pose channels before Auto Pose')
    required = set(solver.BODY) | {'Root'}
    if not required <= mapping.keys():
        raise ValueError('Auto Pose currently supports the complete Rigmodo humanoid hierarchy')
    for j in skeleton.template():
        if j.name not in required: continue
        p = mapping[j.name]
        actual_parent = skeleton.canonical_name(p.parent.name) if p.parent else None
        if actual_parent != j.parent: raise ValueError('Auto Pose needs the standard Rigmodo parent hierarchy')
    for owner in (rig, rig.data):
        ad = owner.animation_data
        if ad and ad.drivers: raise ValueError('Auto Pose does not yet support driven rigs')
    if any(not c.mute and c.influence > 0 for c in rig.constraints):
        raise ValueError('Auto Pose does not yet support constrained armature objects')
    world = rig.matrix_world.to_3x3()
    if any(not math.isfinite(v) for row in rig.matrix_world for v in row):
        raise ValueError('Auto Pose needs a finite armature object transform')
    axes = [world.col[i] for i in range(3)]
    lengths = [v.length for v in axes]
    if min(lengths) < 1e-8 or world.determinant() <= 0 or max(lengths) - min(lengths) > max(lengths) * 1e-5 or any(abs(axes[i].normalized().dot(axes[j].normalized())) > 1e-5 for i in range(3) for j in range(i)):
        raise ValueError('Apply nonuniform or mirrored armature object scale before Auto Pose')
    if rig.pose.use_auto_ik or rig.pose.use_mirror_x:
        raise ValueError('Turn off Blender Auto IK and X-Axis Mirror before Auto Pose')
    if bpy.app.is_job_running('RENDER'):
        raise ValueError('Wait for rendering to finish before posing')
    if context.screen and context.screen.is_animation_playing:
        raise ValueError('Stop animation playback before posing')
    if context.scene.tool_settings.use_keyframe_insert_auto:
        raise ValueError('Turn off Auto Keying; use Insert Pose Key or Capture Pose after the gesture')
    from . import skinning, workflow, hands, landmarks
    if skinning._jobs or workflow._runs or hands._sessions or landmarks._sessions:
        raise ValueError('Finish the current Rigmodo editor or background job before posing')
    return mapping


def channel_snapshot(rig):
    return {p.name: dict(mode=p.rotation_mode, location=p.location.copy(), scale=p.scale.copy(),
                         quaternion=p.rotation_quaternion.copy(), euler=p.rotation_euler.copy(),
                         axis=tuple(p.rotation_axis_angle), basis=p.matrix_basis.copy()) for p in rig.pose.bones}


def restore_channels(rig, snapshot):
    for name, saved in snapshot.items():
        p = rig.pose.bones.get(name)
        if p:
            p.rotation_mode = saved['mode']; p.location = saved['location']; p.scale = saved['scale']
            p.rotation_quaternion = saved['quaternion']; p.rotation_euler = saved['euler']; p.rotation_axis_angle = saved['axis']


class Transaction:
    def __init__(self, context, rig, active):
        validate(context, rig)
        if active not in solver.BODY: raise ValueError('Select a humanoid body bone; fingers use normal Blender posing')
        self.context = context
        self.rig = rig
        self.active = active
        self.snapshot = channel_snapshot(rig)
        self.scene = context.scene
        self.frame = (context.scene.frame_current, context.scene.frame_subframe)
        self.world = rig.matrix_world.copy()
        self.data = rig.data
        self.settings = (rig.lc_auto_pose.feet, rig.lc_auto_pose.body_follow, rig.lc_auto_pose.joint_limits, rig.lc_auto_pose.pins)
        self.rest = tuple((b.name, b.parent.name if b.parent else None, tuple(v for row in b.matrix_local for v in row), b.length) for b in rig.data.bones)
        pins = pins_of(rig)
        if active in pins: raise ValueError('Unpin the selected joint before moving it')
        if rig.lc_auto_pose.feet:
            for n in ('LeftFoot', 'RightFoot'):
                if n != active: pins.setdefault(n, 'FRAME')
        self.model = solver.Model(rig, {n: s['basis'] for n, s in self.snapshot.items()}, pins,
                                  rig.lc_auto_pose.joint_limits, rig.lc_auto_pose.body_follow)
        self.last = None
        self.changed = False
        self.closed = False
        self.area = context.area
        self.timer = None
        self.window_manager = context.window_manager
        _sessions.add(self)

    def valid(self, context):
        try:
            return (context.scene == self.scene and rig_of(context) == self.rig and self.rig.data == self.data
                    and self.rig.lc_auto_pose.enabled and self.frame == (self.scene.frame_current, self.scene.frame_subframe)
                    and self.world == self.rig.matrix_world
                    and self.settings == (self.rig.lc_auto_pose.feet, self.rig.lc_auto_pose.body_follow, self.rig.lc_auto_pose.joint_limits, self.rig.lc_auto_pose.pins)
                    and not self.scene.tool_settings.use_keyframe_insert_auto
                    and not (context.screen and context.screen.is_animation_playing)
                    and not bpy.app.is_job_running('RENDER')
                    and self.rest == tuple((b.name, b.parent.name if b.parent else None, tuple(v for row in b.matrix_local for v in row), b.length) for b in self.rig.data.bones))
        except (ReferenceError, AttributeError): return False

    def apply(self, target, orientation=None):
        result = self.model.solve(self.active, target, orientation)
        # Stage all bones, including twist helpers, before touching the scene.
        rs, ts = self.model.fk(np_rotations(result.bases, self.model.names), np_translations(result.bases, self.model.names))
        poses = {}
        for i, name in enumerate(self.model.names):
            matrix = Matrix(rs[i].tolist()).to_4x4(); matrix.translation = Vector(ts[i]); poses[name] = matrix
        twists.update_matrices(self.rig, poses)
        for module in twists.modules(self.rig):
            b = self.rig.data.bones[module['helper']]
            result.bases[b.name] = b.convert_local_to_pose(poses[b.name], b.matrix_local, parent_matrix=poses[b.parent.name], parent_matrix_local=b.parent.matrix_local, invert=True)
        for name, basis in result.bases.items():
            p = self.rig.pose.bones[name]
            if max(abs(v) for row in (basis - self.snapshot[name]['basis']) for v in row) < 1e-7:
                # Reset a bone which moved in a previous mouse sample.
                saved = self.snapshot[name]
                p.location = saved['location']; p.scale = saved['scale']
                p.rotation_quaternion = saved['quaternion']; p.rotation_euler = saved['euler']; p.rotation_axis_angle = saved['axis']
                continue
            q = basis.to_quaternion()
            p.location = basis.translation; p.scale = (1, 1, 1)
            if p.rotation_mode == 'QUATERNION':
                if q.dot(self.snapshot[name]['quaternion']) < 0: q.negate()
                p.rotation_quaternion = q
            elif p.rotation_mode == 'AXIS_ANGLE': p.rotation_axis_angle = (q.angle, *q.axis)
            else: p.rotation_euler = q.to_euler(p.rotation_mode, self.snapshot[name]['euler'])
        self.changed = any(max(abs(v) for row in (m - self.snapshot[n]['basis']) for v in row) > 1e-6 for n, m in result.bases.items())
        self.last = result
        self.target = Vector(target)
        return result

    def close(self, cancel=False):
        if self.closed: return
        try:
            if cancel: restore_channels(self.rig, self.snapshot)
        except ReferenceError: pass
        try:
            if self.timer: self.window_manager.event_timer_remove(self.timer)
            if self.area: self.area.header_text_set(None); self.area.tag_redraw()
        except (ReferenceError, RuntimeError): pass
        self.timer = None
        self.closed = True
        _sessions.discard(self)


def np_rotations(bases, names):
    import numpy as np
    return np.array([bases[n].to_3x3() for n in names], dtype=float)


def np_translations(bases, names):
    import numpy as np
    return np.array([bases[n].translation for n in names], dtype=float)


class AP_OT_toggle(Operator):
    bl_idname = 'local_character.auto_pose_toggle'
    bl_label = 'Toggle Auto Pose'
    bl_options = {'UNDO'}
    @classmethod
    def poll(cls, context): return bool(rig_of(context)) and not _sessions
    def execute(self, context):
        rig = rig_of(context)
        if rig.lc_auto_pose.enabled: rig.lc_auto_pose.enabled = False
        else:
            try: validate(context, rig)
            except ValueError as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
            rig.lc_auto_pose.enabled = True
        return {'FINISHED'}


class AP_OT_pin(Operator):
    bl_idname = 'local_character.auto_pose_pin'
    bl_label = 'Pin Joint'
    bl_options = {'UNDO'}
    clear: BoolProperty(default=False, options={'HIDDEN'})
    @classmethod
    def poll(cls, context): return bool(rig_of(context)) and not _sessions
    def execute(self, context):
        rig = rig_of(context)
        if self.clear: rig.lc_auto_pose.pins = '{}'; return {'FINISHED'}
        name = active_name(context)
        if name not in PIN_BONES: self.report({'WARNING'}, 'Pin hands, feet or pelvis'); return {'CANCELLED'}
        try: pins = pins_of(rig)
        except ValueError as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        if name in pins: del pins[name]
        else: pins[name] = 'FRAME' if name == 'Hips' else rig.lc_auto_pose.pin_mode
        rig.lc_auto_pose.pins = json.dumps(pins)
        return {'FINISHED'}


def move_on_plane(region, view, mouse, pivot, normal):
    ray = view3d_utils.region_2d_to_vector_3d(region, view, mouse)
    origin = view3d_utils.region_2d_to_origin_3d(region, view, mouse)
    divisor = normal.dot(ray)
    if abs(divisor) < 1e-6: raise ValueError('View is parallel to the movement plane; change the view')
    return origin + ray * ((pivot - origin).dot(normal) / divisor)


class Drag:
    bl_options = {'UNDO', 'BLOCKING'}
    @classmethod
    def poll(cls, context):
        rig = rig_of(context)
        return bool(rig and rig.lc_auto_pose.enabled and active_name(context) in solver.BODY and not _sessions
                    and context.area and context.area.type == 'VIEW_3D' and context.region and context.region.type == 'WINDOW')

    def invoke(self, context, event):
        self.transaction = None
        try:
            self.transaction = Transaction(context, rig_of(context), active_name(context))
            self.area = context.area; self.region = context.region; self.view = context.region_data
            if not self.view: raise ValueError('Invoke Auto Pose in the 3D viewport')
            self.start = Vector((event.mouse_region_x, event.mouse_region_y)); self.mouse = self.start.copy()
            self.previous_mouse = self.start.copy()
            i = self.transaction.model.semantic[self.transaction.active]
            self.initial_position = Vector(self.transaction.model.reference[1][i])
            self.initial_rotation = Matrix(self.transaction.model.reference[0][i].tolist()).to_quaternion()
            self.pivot = self.transaction.world @ self.initial_position
            self.normal = (self.view.view_rotation @ Vector((0, 0, 1))).normalized()
            self.plane_start = move_on_plane(self.region, self.view, self.start, self.pivot, self.normal)
            self.view_matrix = self.view.view_matrix.copy()
            self.axis = ''; self.local = False; self.number = ''; self.precision = False; self.status = ''
            self.transaction.timer = context.window_manager.event_timer_add(.1, window=context.window)
            self.area.header_text_set('Auto Pose · G/R · X/Y/Z axis · Enter confirm · Esc cancel')
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        except (ValueError, RuntimeError, KeyError) as exc:
            self.finish(True); self.report({'WARNING'}, str(exc)); return {'CANCELLED'}

    def finish(self, cancel=False):
        if self.transaction: self.transaction.close(cancel)
        try:
            if getattr(self, 'area', None): self.area.header_text_set(None); self.area.tag_redraw()
        except ReferenceError: pass

    def cancel(self, context): self.finish(True)

    def axis_direction(self):
        direction = Vector((1, 0, 0) if self.axis == 'X' else (0, 1, 0) if self.axis == 'Y' else (0, 0, 1))
        if self.local: direction = self.transaction.world.to_quaternion() @ self.initial_rotation @ direction
        return direction.normalized()

    def update(self, context):
        t = self.transaction
        factor = 1.  # Precision is accumulated per mouse increment, without a jump.
        if self.kind == 'MOVE':
            current = move_on_plane(self.region, self.view, self.mouse, self.pivot, self.normal)
            delta = (current - self.plane_start) * factor
            if self.axis:
                axis = self.axis_direction()
                # Closest points on ray and constrained axis, referenced to invocation.
                ray = view3d_utils.region_2d_to_vector_3d(self.region, self.view, self.mouse)
                origin = view3d_utils.region_2d_to_origin_3d(self.region, self.view, self.mouse)
                ray0 = view3d_utils.region_2d_to_vector_3d(self.region, self.view, self.start)
                origin0 = view3d_utils.region_2d_to_origin_3d(self.region, self.view, self.start)
                def parameter(o, r):
                    d = axis.dot(r); denom = 1 - d * d
                    if denom < 1e-5: raise ValueError('Axis points into the view; use numeric input or change the view')
                    v = o - self.pivot
                    return (axis.dot(v) - d * r.dot(v)) / denom
                amount = float(self.number) / context.scene.unit_settings.scale_length if self.number not in {'', '-', '.', '-.'} else (parameter(origin, ray) - parameter(origin0, ray0)) * factor
                delta = axis * amount
            elif self.number:
                if self.number not in {'-', '.', '-.'}:
                    if delta.length < 1e-8: raise ValueError('Choose X, Y or Z for numeric movement')
                    delta = delta.normalized() * (float(self.number) / context.scene.unit_settings.scale_length)
            target = t.world.inverted() @ (self.pivot + delta)
            result = t.apply(target)
        else:
            projected = view3d_utils.location_3d_to_region_2d(self.region, self.view, self.pivot)
            if projected is None: raise ValueError('Selected joint is behind the view')
            a, b = self.start - projected, self.mouse - projected
            angle = math.atan2(a.x * b.y - a.y * b.x, a.dot(b)) * factor
            if self.number not in {'', '-', '.', '-.'}: angle = math.radians(float(self.number))
            axis = self.axis_direction() if self.axis else self.normal
            # Screen-plane sign matches view direction; axis rotation follows right-hand rule.
            armature_axis = t.world.to_quaternion().inverted() @ axis
            orientation = (Quaternion(armature_axis, angle) @ self.initial_rotation).to_matrix()
            result = t.apply(self.initial_position, orientation)
        label = ('Local ' if self.local else '') + self.axis if self.axis else 'View'
        self.status = 'Reach limit · pins held' if result.limited else 'Pins held'
        self.area.header_text_set(f'Auto Pose {"Move" if self.kind == "MOVE" else "Rotate"} · {label} {self.number} · {self.status} · Enter confirm / Esc cancel')
        self.area.tag_redraw()

    def modal(self, context, event):
        if not self.transaction or self.transaction.closed or not self.transaction.valid(context):
            self.finish(True); return {'CANCELLED'}
        if self.view.view_matrix != self.view_matrix:
            self.finish(True); self.report({'WARNING'}, 'View changed; Auto Pose gesture cancelled'); return {'CANCELLED'}
        if event.type in {'ESC', 'RIGHTMOUSE', 'WINDOW_DEACTIVATE'} and event.value in {'PRESS', 'NOTHING'}:
            self.finish(True); return {'CANCELLED'}
        if event.type in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'} and event.value == 'PRESS':
            changed = self.transaction.changed
            self.finish(not changed); return {'FINISHED'} if changed else {'CANCELLED'}
        dirty = False
        if event.type == 'MOUSEMOVE':
            current_mouse = Vector((event.mouse_region_x, event.mouse_region_y))
            self.mouse += (current_mouse - self.previous_mouse) * (.1 if event.shift else 1.)
            self.previous_mouse = current_mouse; self.precision = event.shift; dirty = True
        elif event.value == 'PRESS' and event.type in {'X', 'Y', 'Z'}:
            if self.axis == event.type:
                if self.local: self.axis = ''; self.local = False
                else: self.local = True
            else: self.axis = event.type; self.local = False
            dirty = True
        elif event.value == 'PRESS' and event.type in {'G', 'R'}:
            # One gesture has one ownership scope; switching tools starts a new gesture.
            return {'RUNNING_MODAL'}
        elif event.value == 'PRESS' and event.type == 'BACK_SPACE':
            self.number = self.number[:-1]; dirty = True
        elif event.value == 'PRESS' and event.type in {'MINUS', 'NUMPAD_MINUS'}:
            self.number = self.number[1:] if self.number.startswith('-') else '-' + self.number; dirty = True
        elif event.value == 'PRESS' and event.unicode and event.unicode in '0123456789.':
            if event.unicode != '.' or '.' not in self.number:
                self.number += event.unicode; dirty = True
        if dirty:
            try: self.update(context)
            except (ValueError, RuntimeError, KeyError) as exc:
                # Invalid proposals leave the last accepted pose intact.
                self.area.header_text_set('Auto Pose · ' + str(exc) + ' · Esc cancel')
        return {'RUNNING_MODAL'}


class AP_OT_move(Drag, Operator):
    bl_idname = 'local_character.auto_pose_move'
    bl_label = 'Auto Pose Move'
    bl_description = 'Move the active body joint with procedural full-body IK; G in the viewport'
    kind = 'MOVE'


class AP_OT_rotate(Drag, Operator):
    bl_idname = 'local_character.auto_pose_rotate'
    bl_label = 'Auto Pose Rotate'
    bl_description = 'Rotate the active body joint while preserving its position and pins; R in the viewport'
    kind = 'ROTATE'


class AP_OT_key(Operator):
    bl_idname = 'local_character.auto_pose_key'
    bl_label = 'Insert Pose Key'
    bl_description = 'Key the complete current pose, including every bone changed by Auto Pose'
    bl_options = {'UNDO'}
    @classmethod
    def poll(cls, context): return bool(rig_of(context)) and not _sessions
    def execute(self, context):
        rig = rig_of(context)
        try:
            validate(context, rig)
            ad = rig.animation_data
            if ad and (any(not t.mute for t in ad.nla_tracks) or ad.action and ad.action.users > 1):
                raise ValueError('Use a single-user Action without active NLA tracks for pose keys')
            if ad and ad.action and (ad.action.library or not ad.action.is_editable):
                raise ValueError('Make the Action local and editable before inserting pose keys')
            rig.animation_data_create()
            if not rig.animation_data.action:
                rig.animation_data.action = bpy.data.actions.new('Rigmodo Auto Pose')
            # The existing Unity companion must use the authored Root trajectory
            # instead of Humanoid's body-center projection, including stationary clips.
            rig.animation_data.action['lc_explicit_root_motion'] = True
            frame = context.scene.frame_current + context.scene.frame_subframe
            for p in rig.pose.bones:
                rotation = 'rotation_quaternion' if p.rotation_mode == 'QUATERNION' else 'rotation_axis_angle' if p.rotation_mode == 'AXIS_ANGLE' else 'rotation_euler'
                for path in ('location', rotation, 'scale'): p.keyframe_insert(data_path=path, frame=frame, group=p.name)
        except (ValueError, RuntimeError) as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        self.report({'INFO'}, 'Complete pose keyed'); return {'FINISHED'}


def draw(layout, context):
    rig = rig_of(context)
    if not rig: return
    settings = rig.lc_auto_pose
    box = layout.box()
    box.operator('local_character.auto_pose_toggle', text='Auto Pose', icon='POSE_HLT', depress=settings.enabled)
    if not settings.enabled: return
    box.label(text='Select a body bone · G move · R rotate')
    row = box.row(align=True)
    # Buttons route invocation to the WINDOW region, not the sidebar region.
    row.operator('local_character.auto_pose_start', text='Move').kind = 'MOVE'
    row.operator('local_character.auto_pose_start', text='Rotate').kind = 'ROTATE'
    box.prop(settings, 'feet')
    name = active_name(context)
    try: pins = pins_of(rig)
    except ValueError: pins = {}
    row = box.row(align=True); row.enabled = name in PIN_BONES and not _sessions
    row.operator('local_character.auto_pose_pin', text='Unpin ' + name if name in pins else 'Pin ' + (name or 'Joint'), icon='PINNED' if name in pins else 'UNPINNED')
    header, body = box.panel('lc_auto_pose_details', default_closed=True); header.label(text='Pose options')
    if body:
        body.prop(settings, 'pin_mode'); body.prop(settings, 'body_follow'); body.prop(settings, 'joint_limits')
        if name=='Hips': body.label(text='Pelvis pins hold position + rotation')
        if pins: body.label(text='Pinned: ' + ', '.join(pins))
        body.operator('local_character.auto_pose_pin', text='Clear Explicit Pins').clear = True
    box.operator('local_character.auto_pose_key', icon='KEY_HLT')


class AP_OT_start(Operator):
    bl_idname = 'local_character.auto_pose_start'
    bl_label = 'Start Auto Pose'
    kind: EnumProperty(items=[('MOVE', 'Move', ''), ('ROTATE', 'Rotate', '')])
    @classmethod
    def poll(cls, context):
        rig = rig_of(context)
        return bool(rig and rig.lc_auto_pose.enabled and active_name(context) in solver.BODY
                    and context.area and context.area.type=='VIEW_3D' and not _sessions)
    def execute(self, context):
        region = next((r for r in context.area.regions if r.type == 'WINDOW'), None)
        if not region: return {'CANCELLED'}
        with context.temp_override(region=region):
            operator = bpy.ops.local_character.auto_pose_move if self.kind == 'MOVE' else bpy.ops.local_character.auto_pose_rotate
            result = operator('INVOKE_DEFAULT')
            return {'FINISHED'} if result == {'RUNNING_MODAL'} else {'CANCELLED'}


@persistent
def reset_sessions(*_):
    for transaction in list(_sessions): transaction.close(cancel=True)


def draw_pins():
    """No hidden scene objects: viewport-only pin markers follow the current rig."""
    context = bpy.context
    rig = rig_of(context)
    if not rig or not rig.lc_auto_pose.enabled: return
    try:
        import gpu
        from gpu_extras.batch import batch_for_shader
        explicit = pins_of(rig)
        names = set(explicit)
        if rig.lc_auto_pose.feet: names.update(('LeftFoot', 'RightFoot'))
        session = next((s for s in _sessions if s.rig==rig), None)
        points = []
        for p in rig.pose.bones:
            name = skeleton.canonical_name(p.name)
            if name not in names or session and name==session.active and name not in explicit: continue
            head = Vector(session.model.reference[1][session.model.semantic[name]]) if session else p.head
            points.append(rig.matrix_world @ head)
        if points:
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
            gpu.state.blend_set('ALPHA')
            shader.bind(); shader.uniform_float('color', (.15, .8, 1., 1.))
            for point in points:
                screen = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, point)
                if screen is not None:
                    circle = [(screen.x + 8*math.cos(k*math.tau/24), screen.y + 8*math.sin(k*math.tau/24)) for k in range(25)]
                    batch_for_shader(shader,'LINE_STRIP',{'pos':circle}).draw(shader)
            if session and session.last and session.last.limited:
                target = view3d_utils.location_3d_to_region_2d(context.region,context.region_data,session.world@session.target)
                actual = view3d_utils.location_3d_to_region_2d(context.region,context.region_data,rig.matrix_world@rig.pose.bones[session.model.names[session.model.semantic[session.active]]].head)
                if target is not None and actual is not None:
                    shader.uniform_float('color',(1.,.55,.15,1.))
                    batch_for_shader(shader,'LINES',{'pos':[actual,target]}).draw(shader)
    except (ReferenceError, ValueError, RuntimeError, KeyError): pass
    finally:
        # Restore GPU state used by other editors/overlays.
        if 'gpu' in locals(): gpu.state.blend_set('NONE')


CLASSES = (AP_Settings, AP_OT_toggle, AP_OT_pin, AP_OT_move, AP_OT_rotate, AP_OT_key, AP_OT_start)


def register():
    global _draw_handle
    bpy.types.Object.lc_auto_pose = PointerProperty(type=AP_Settings)
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        keymap = config.keymaps.new(name='Pose', space_type='EMPTY')
        for key, operator in (('G', AP_OT_move.bl_idname), ('R', AP_OT_rotate.bl_idname)):
            _keymaps.append((keymap, keymap.keymap_items.new(operator, key, 'PRESS')))
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        handlers.append(reset_sessions)
    if not bpy.app.background:
        _draw_handle = bpy.types.SpaceView3D.draw_handler_add(draw_pins, (), 'WINDOW', 'POST_PIXEL')


def cleanup():
    global _draw_handle
    reset_sessions()
    for keymap, item in _keymaps: keymap.keymap_items.remove(item)
    _keymaps.clear()
    for handlers in (bpy.app.handlers.load_pre, bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre):
        if reset_sessions in handlers: handlers.remove(reset_sessions)
    if hasattr(bpy.types.Object, 'lc_auto_pose'): del bpy.types.Object.lc_auto_pose
    if _draw_handle:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle, 'WINDOW'); _draw_handle = None
