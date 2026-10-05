# SPDX-License-Identifier: GPL-3.0-or-later
"""Real Blender keymap/modal events, in a separate factory-startup GUI process.

blender --factory-startup --enable-event-simulate --python THIS -- OUTPUT
"""
import addon_utils
import importlib
import json
import math
import sys
import time
import traceback
from pathlib import Path
import bpy
from mathutils import Matrix, Quaternion
from bpy_extras import view3d_utils

assert '--factory-startup' in sys.argv and '--enable-event-simulate' in sys.argv
out = Path(sys.argv[sys.argv.index('--') + 1]); out.mkdir(parents=True, exist_ok=True)
addon_utils.enable('bl_ext.user_default.local_character', default_set=True)
addon = importlib.import_module('bl_ext.user_default.local_character')
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
rig = addon.skeleton.create_armature(bpy.context, 1.75, 20); rig.name = 'AutoPose_Interaction_Test'
bpy.ops.object.mode_set(mode='POSE'); rig.lc_auto_pose.enabled = True
bpy.context.scene.tool_settings.use_keyframe_insert_auto = False
window = bpy.context.window
area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
region = next(r for r in area.regions if r.type == 'WINDOW')
view = area.spaces.active.region_3d
view.view_rotation = Quaternion((1, 0, 0), math.pi / 2)
view.view_location = (0, 0, .9); view.view_distance = 3.2; view.view_perspective = 'ORTHO'
bpy.ops.wm.save_as_mainfile(filepath=str(out / 'interaction.blend'))
rows = []; actions = []; state = {}; deadline = time.monotonic() + 2


def current(): return bpy.data.objects['AutoPose_Interaction_Test']
def snapshot(): return {p.name: [float(v) for row in p.matrix_basis for v in row] for p in current().pose.bones}
def difference(a, b): return max(abs(x-y) for n in a for x, y in zip(a[n], b[n]))
def queue(key, value='PRESS', dx=0, dy=0, ctrl=False, shift=False):
    char = {'PERIOD': '.', 'ZERO': '0', 'FIVE': '5'}.get(key, '')
    extra = {'unicode':char} if char and value=='PRESS' else {}
    window.event_simulate(type=key, value='NOTHING' if key == 'MOUSEMOVE' else value,
                          x=state['x'] + dx, y=state['y'] + dy, ctrl=ctrl, shift=shift, **extra)
def key(key, **kwargs): queue(key, **kwargs); queue(key, 'RELEASE', **kwargs)


def begin(label, enabled=True):
    r = current()
    for p in r.pose.bones: p.matrix_basis = Matrix.Identity(4); p.select = False
    r.pose.bones['LeftHand'].select = True; r.data.bones.active = r.data.bones['LeftHand']
    r.lc_auto_pose.enabled = enabled; r.lc_auto_pose.pins = '{}'
    bpy.context.view_layer.update()
    point = view3d_utils.location_3d_to_region_2d(region, view, r.matrix_world @ r.pose.bones['LeftHand'].head)
    state.update(label=label, before=snapshot(), x=int(region.x + point.x + 70), y=int(region.y + point.y + 10), after=None)
    with bpy.context.temp_override(window=window, area=area, region=region): bpy.ops.ed.undo_push(message='Before ' + label)


def inspect_modal(expected):
    identifiers = [op.bl_idname for op in window.modal_operators]
    assert expected in identifiers, identifiers


def finished(cancel=False, native=False):
    r = current(); after = snapshot(); delta = difference(state['before'], after)
    assert not addon.auto_pose._sessions
    if cancel: assert delta < 1e-7, delta
    else:
        assert delta > .001, delta
        if not native:
            assert max(p.location.length for p in r.pose.bones if p.name not in {'Root', 'Hips'}) < 2e-6
            for name in ('LeftFoot', 'RightFoot'):
                assert (r.pose.bones[name].head - r.data.bones[name].head_local).length < 1e-5
    state['after'] = after
    rows.append(dict(case=state['label'], changed=delta, cancelled=cancel, native=native, passed=True))
    print('INTERACTION_CASE', json.dumps(rows[-1]), flush=True)


def check_undo():
    assert difference(state['before'], snapshot()) < 2e-6
    rows[-1]['undo'] = True
def check_redo():
    assert difference(state['after'], snapshot()) < 2e-6
    rows[-1]['redo'] = True


for label, kind, cancel in (('G_confirm', 'G', False), ('G_cancel', 'G', True), ('R_confirm', 'R', False), ('R_cancel', 'R', True), ('numeric_axis', 'G', False)):
    actions += [lambda label=label: begin(label), lambda kind=kind: key(kind),
                lambda kind=kind: inspect_modal('LOCAL_CHARACTER_OT_auto_pose_move' if kind == 'G' else 'LOCAL_CHARACTER_OT_auto_pose_rotate')]
    if label == 'numeric_axis':
        actions += [lambda: key('Z'), lambda: key('PERIOD'), lambda: key('ZERO'), lambda: key('FIVE')]
    else:
        for dx, dy in ((-10, 8), (-20, 15), (-30, 20), (-40, 25)):
            actions.append(lambda dx=dx, dy=dy: queue('MOUSEMOVE', dx=dx, dy=dy))
    actions += [lambda cancel=cancel: key('ESC' if cancel else 'RET'), lambda cancel=cancel: finished(cancel)]
    if not cancel:
        actions += [lambda: key('Z', ctrl=True), check_undo, lambda: key('Z', ctrl=True, shift=True), check_redo]
actions += [lambda: begin('disabled_native_G', False), lambda: key('G'), lambda: inspect_modal('TRANSFORM_OT_translate'),
            lambda: queue('MOUSEMOVE', dx=-25, dy=20), lambda: key('RET'), lambda: finished(native=True)]
actions += [lambda: begin('sidebar_move_button'), lambda: queue('MOUSEMOVE'),
            lambda: bpy.ops.local_character.auto_pose_start(kind='MOVE'),
            lambda: inspect_modal('LOCAL_CHARACTER_OT_auto_pose_move'),
            lambda: queue('MOUSEMOVE',dx=-30,dy=25), lambda: key('RET'), lambda: finished(),
            lambda: key('Z',ctrl=True), check_undo, lambda: key('Z',ctrl=True,shift=True), check_redo]
actions += [lambda: begin('disabled_during_gesture'), lambda: key('G'), lambda: queue('MOUSEMOVE',dx=-30,dy=25),
            lambda: setattr(current().lc_auto_pose,'enabled',False), lambda: finished(cancel=True)]
def deselect():
    for p in current().pose.bones:p.select=False
def no_session():assert not addon.auto_pose._sessions
actions += [lambda:begin('no_selected_bone'),deselect,lambda:key('G'),no_session,
            lambda:queue('MOUSEMOVE',dx=-20,dy=15),lambda:key('ESC'),lambda:finished(cancel=True,native=True)]


def finish():
    assert all(r['passed'] for r in rows) and not addon.auto_pose._sessions
    report = dict(passed=True, real_keymap_events=True, cases=rows, blender=bpy.app.version_string)
    (out / 'interaction-results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('AUTO_POSE_INTERACTION_COMPLETE', json.dumps(report), flush=True)
    bpy.ops.wm.quit_blender()
actions.append(finish)


def tick():
    global deadline
    if time.monotonic() < deadline: return .05
    try:
        with bpy.context.temp_override(window=window, area=area, region=region): actions.pop(0)()
        deadline = time.monotonic() + .25
    except Exception:
        (out / 'error.txt').write_text(traceback.format_exc())
        traceback.print_exc(); bpy.ops.wm.quit_blender(); return None
    return .05 if actions else None
bpy.app.timers.register(tick, first_interval=.5)
