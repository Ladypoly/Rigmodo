# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated exact-FK, pins, targets, proportions and authored-pose acceptance."""
import addon_utils
import importlib
import json
import math
import statistics
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Vector

assert bpy.app.background and '--factory-startup' in sys.argv
args=sys.argv[sys.argv.index('--')+1:]
if len(args)>1:
    import importlib.util
    source=Path(args[1])
    spec=importlib.util.spec_from_file_location('rigmodo_archive',source/'__init__.py',submodule_search_locations=[str(source)])
    addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
else:
    addon_utils.enable('bl_ext.user_default.local_character', default_set=True)
    addon = importlib.import_module('bl_ext.user_default.local_character')
solver = importlib.import_module(addon.__package__ + '.auto_pose_solver')
out = Path(sys.argv[sys.argv.index('--') + 1]); out.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
rows = []
for height in (.875, 1.75, 3.5):
    rig = addon.skeleton.create_armature(bpy.context, height, 20)
    bpy.ops.object.mode_set(mode='EDIT')
    for i, b in enumerate(rig.data.edit_bones): b.roll += (i % 7 - 3) * .13
    bpy.ops.object.mode_set(mode='OBJECT')
    bases = {p.name: p.matrix_basis.copy() for p in rig.pose.bones}
    model = solver.Model(rig, bases)
    rs, ps = model.reference
    bpy.context.view_layer.update()
    roundtrip = max(np.max(np.abs(rs[i] - np.array(rig.pose.bones[n].matrix.to_3x3()))) for i, n in enumerate(model.names))
    position_roundtrip = max(np.linalg.norm(ps[i] - np.array(rig.pose.bones[n].matrix.translation)) for i, n in enumerate(model.names))
    assert roundtrip < 2e-6 and position_roundtrip < height * 2e-6, (roundtrip, position_roundtrip)
    cases = [
        ('small_hand', 'LeftHand', (-.025, -.025, .025), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('far_hand', 'LeftHand', (.07, -.08, .07), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('shorten_arm', 'LeftHand', (-.10, 0., 0.), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('pelvis_down', 'Hips', (0., 0., -.07), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('pelvis_sideways', 'Hips', (.04, 0., 0.), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('foot', 'LeftFoot', (0., -.09, .08), {'RightFoot': 'FRAME'}),
        ('multiple_pins', 'LeftHand', (-.02, -.10, .07), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME', 'RightHand': 'POSITION'}),
        ('hips_pin', 'LeftFoot', (0., -.12, .07), {'Hips': 'FRAME', 'RightFoot': 'FRAME'}),
        ('elbow', 'LeftForeArm', (-.02, -.02, .01), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('knee', 'LeftLeg', (0., -.035, .025), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('extreme_arm', 'LeftHand', (1., -1., 1.), {'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
        ('target_is_pin', 'LeftHand', (-.05, -.05, .05), {'LeftHand': 'POSITION', 'LeftFoot': 'FRAME', 'RightFoot': 'FRAME'}),
    ]
    for label, active, delta, pins in cases:
        model = solver.Model(rig, bases, pins)
        target = model.reference[1][model.semantic[active]] + np.array(delta) * height
        result = model.solve(active, target)
        # Actual Blender evaluation independently checks the internal FK tree.
        for p in rig.pose.bones: p.matrix_basis = result.bases[p.name]
        bpy.context.view_layer.update()
        actual = rig.pose.bones[active].matrix.translation
        error = (actual - Vector(target)).length / height
        max_pin = max(((rig.pose.bones[n].matrix.translation - Vector(model.reference[1][model.semantic[n]])).length / height for n in pins), default=0.)
        max_length = max(abs((p.tail - p.head).length - p.bone.length) / height for p in rig.pose.bones)
        assert max_pin < 2e-5 and max_length < 2e-6
        if label in {'small_hand','far_hand','shorten_arm','pelvis_down','foot','multiple_pins','hips_pin','elbow'}:
            assert error < 1e-4 and not result.limited, (label, error)
        if label in {'extreme_arm','target_is_pin'}: assert result.limited
        assert all(p.location.length < 3e-6 for p in rig.pose.bones if p.name not in {'Root', 'Hips'})
        assert all(abs(v - 1) < 3e-6 for p in rig.pose.bones for v in p.scale)
        rows.append(dict(case=label, height=height, target_error_height=error, pin_error_height=max_pin, length_error_height=max_length,
                         limited=result.limited, milliseconds=result.milliseconds, iterations=result.iterations))
        print('CASE', json.dumps(rows[-1]), flush=True)
    for p in rig.pose.bones: p.matrix_basis = bases[p.name]

ap = addon.auto_pose
rig = addon.skeleton.create_armature(bpy.context, 1.75, 0)
bpy.ops.object.mode_set(mode='POSE')
rig.lc_auto_pose.enabled = True
ap.validate(bpy.context, rig)
# Preserve Euler winding, fingers, mode and exact inactive rotation channels.
rig.pose.bones['LeftHandIndex1'].rotation_euler.x = 7.1
rig.pose.bones['LeftForeArm'].rotation_euler.y = .5
before = ap.channel_snapshot(rig)
counts = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures), len(bpy.data.actions))
t = ap.Transaction(bpy.context, rig, 'LeftHand')
goal = Vector(t.model.reference[1][t.model.semantic['LeftHand']]) + Vector((-.09, -.05, .03))
t.apply(goal); bpy.context.view_layer.update()
assert t.changed and t.valid(bpy.context)
assert abs(rig.pose.bones['LeftHandIndex1'].rotation_euler.x - 7.1) < 1e-6
try:
    addon.motion_keyframes.capture(bpy.context, rig)
    raise AssertionError('Capture during gesture accepted')
except ValueError as exc: assert 'gesture' in str(exc)
t.close(cancel=True)
after = ap.channel_snapshot(rig)
assert all(before[n]['mode'] == after[n]['mode'] and before[n]['euler'] == after[n]['euler'] and before[n]['quaternion'] == after[n]['quaternion']
           and before[n]['axis'] == after[n]['axis'] and before[n]['location'] == after[n]['location'] and before[n]['scale'] == after[n]['scale'] for n in before)
assert counts == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures), len(bpy.data.actions))
# Real orientation targets, uniform world transforms, authored reference poses.
t = ap.Transaction(bpy.context, rig, 'LeftHand')
i = t.model.semantic['LeftHand']; orientation = Matrix.Rotation(.5, 3, 'X') @ Matrix(t.model.reference[0][i].tolist())
r = t.apply(t.model.reference[1][i], orientation)
assert r.orientation_error < 1e-4 and r.pin_error < 1e-5
t.close(cancel=True)
rig.matrix_world = Matrix.Translation((2, -3, .5)) @ Matrix.Rotation(.4, 4, 'Z') @ Matrix.Scale(2, 4)
bpy.context.view_layer.update(); ap.validate(bpy.context, rig)
rig.scale = (1, 2, 1); bpy.context.view_layer.update()
try: ap.validate(bpy.context, rig); raise AssertionError('Nonuniform scale accepted')
except ValueError as exc: assert 'scale' in str(exc)
rig.matrix_world = Matrix.Identity(4); bpy.context.view_layer.update()
for attribute, value, message in (('use_keyframe_insert_auto', True, 'Auto Keying'),):
    setattr(bpy.context.scene.tool_settings, attribute, value)
    try: ap.validate(bpy.context, rig); raise AssertionError('Unsafe setup accepted')
    except ValueError as exc: assert message in str(exc)
    setattr(bpy.context.scene.tool_settings, attribute, False)
c = rig.pose.bones['LeftHand'].constraints.new('LIMIT_ROTATION')
try: ap.validate(bpy.context, rig); raise AssertionError('Constraint accepted')
except ValueError as exc: assert 'constraints' in str(exc)
rig.pose.bones['LeftHand'].constraints.remove(c)
p=rig.pose.bones['LeftHand'];p.location.x=float('nan')
try:ap.validate(bpy.context,rig);raise AssertionError('Nonfinite pose accepted')
except ValueError as exc:assert 'finite' in str(exc)
p.location.x=0.
rig.lc_auto_pose.pins = '{"Hips":"FRAME"}'
t = ap.Transaction(bpy.context, rig, 'LeftHand'); t.apply(goal); t.close(cancel=True)
rig.lc_auto_pose.pins = '{}'
assert bpy.ops.local_character.auto_pose_key() == {'FINISHED'}
assert rig.animation_data.action
assert rig.animation_data.action.get('lc_explicit_root_motion')
# Whole-body curves exist rather than keying only the dragged hand.
slot = rig.animation_data.action_slot
curves = [c for layer in rig.animation_data.action.layers for strip in layer.strips for c in strip.channelbag(slot).fcurves]
assert all(any(c.data_path.startswith(p.path_from_id()) for c in curves) for p in rig.pose.bones)
assert not ap._sessions
rig.animation_data_clear()
# Optional helpers follow the solved forearm without joining the solver graph.
bpy.ops.object.mode_set(mode='EDIT'); modules=[]
for side in ('Left','Right'):
    source=rig.data.edit_bones[side+'ForeArm']; helper=rig.data.edit_bones.new(side+'ForeArmTwist')
    helper.head=source.head; helper.tail=source.tail; helper.roll=source.roll; helper.parent=source.parent
    modules.append(dict(source=source.name,helper=helper.name,fraction=.5))
bpy.ops.object.mode_set(mode='POSE'); rig['lc_twists']=json.dumps(modules)
addon.twists.update_pose(rig)
t=ap.Transaction(bpy.context,rig,'LeftHand'); t.apply(goal); t.close()
bpy.context.view_layer.update(); addon.motion_keyframes.capture(bpy.context,rig)
for module in modules:
    expected=addon.twists.reduced(rig.pose.bones[module['source']].matrix_basis.to_quaternion(),.5)
    actual=rig.pose.bones[module['helper']].matrix_basis.to_quaternion()
    assert abs(abs(expected.dot(actual))-1)<1e-6
# Lifecycle invalidation restores and removes ownership, without changing mode.
t=ap.Transaction(bpy.context,rig,'LeftHand'); t.apply(goal)
rig.lc_auto_pose.enabled=False; assert not t.valid(bpy.context)
ap.reset_sessions(); assert t.closed and not ap._sessions
rig.lc_auto_pose.enabled=True
# Keymap/handler teardown is idempotent and re-registers once.
ap.cleanup(); assert not hasattr(bpy.types.Object,'lc_auto_pose') and not ap._keymaps
ap.register(); assert hasattr(bpy.types.Object,'lc_auto_pose')
assert bpy.app.handlers.load_pre.count(ap.reset_sessions)==1
report = dict(passed=True, cases=rows, solver_median_ms=statistics.median(r['milliseconds'] for r in rows),
              full_channels_restored=True, no_helper_objects=True, rotation_target_passed=True, capture_guard=True,
              unsafe_setup_rejected=True, whole_pose_keys=True, twist_helpers=True, lifecycle_cleanup=True,
              extracted_extension=len(args)>1,version=addon.exporter.VERSION)
(out / 'solver-results.json').write_text(json.dumps(report, indent=2) + '\n')
print('AUTO_POSE_ACCEPTANCE', json.dumps(report), flush=True)
