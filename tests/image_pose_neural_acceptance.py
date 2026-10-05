# SPDX-License-Identifier: GPL-3.0-or-later
"""Real pinned SAM inference and production apply on a private skinned avatar.

Run in factory-startup background Blender, with an installed provider. Images,
predictions and avatar geometry remain in the requested private output folder.
"""
import addon_utils, importlib, json, math, subprocess, sys, time
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

assert bpy.app.background and '--factory-startup' in sys.argv
out = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
out.mkdir(parents=True, exist_ok=True)
addon_utils.enable('bl_ext.user_default.local_character', default_set=True)
addon = importlib.import_module('bl_ext.user_default.local_character')
ip = addon.image_pose
provider = ip.cache()
fixture = Path.home() / 'AppData/Local/Temp/rigmodo-auto-skin-acceptance/skin-review.blend'
assert fixture.is_file() and (provider / 'installation.json').is_file()
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
with bpy.data.libraries.load(str(fixture), link=False) as (src, dst):
    dst.objects = src.objects
for obj in dst.objects:
    if obj:
        bpy.context.scene.collection.objects.link(obj)
        obj.hide_set(False)
        obj.hide_viewport = False
rig = next(o for o in dst.objects if o and o.type == 'ARMATURE')
meshes = [o for o in dst.objects if o and o.type == 'MESH' and
          any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
for obj in bpy.context.selected_objects:
    obj.select_set(False)
rig.select_set(True)
bpy.context.view_layer.objects.active = rig
bpy.context.scene.lc_settings.ui_step = 'MOTION'
bpy.context.view_layer.update()
before = addon.auto_pose.channel_snapshot(rig)
counts = (len(bpy.data.objects), len(bpy.data.armatures), len(bpy.data.meshes), len(bpy.data.actions))
geometry = addon.skinning._digest(rig, meshes)
signature = addon.motion_keyframes.signature(bpy.context, rig)
action = rig.animation_data.action if rig.animation_data else None
rows = []
for hands in (True, False):
    addon.auto_pose.restore_channels(rig, before)
    bpy.context.view_layer.update()
    folder = ip.prepare(bpy.context, rig, provider / 'source/notebook/images/dancing.jpg',
                        provider, hands=hands, parent=out)
    began = time.monotonic()
    with (folder / 'worker.log').open('w') as log:
        process = subprocess.run([str(provider / 'runtime/Scripts/python.exe'), '-I',
                                  str(Path(ip.__file__).with_name('sam_pose_worker.py')), str(folder)],
                                 stdout=log, stderr=subprocess.STDOUT, timeout=300,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    assert process.returncode == 0, (folder / 'worker.log').read_text()
    wall = time.monotonic() - began
    request, result = ip.read_result(folder)
    addon.skinning._state(folder, 'complete')
    assert bpy.ops.local_character.apply_image_pose(folder=str(folder)) == {'FINISHED'}
    bpy.context.view_layer.update()
    assert counts == (len(bpy.data.objects), len(bpy.data.armatures), len(bpy.data.meshes), len(bpy.data.actions))
    assert geometry == addon.skinning._digest(rig, meshes)
    assert signature == addon.motion_keyframes.signature(bpy.context, rig)
    assert (rig.animation_data.action if rig.animation_data else None) == action
    assert all(abs(v) < 1e-6 for row in (rig.pose.bones['Root'].matrix_basis - before['Root']['basis']) for v in row)
    if not hands:
        assert all(p.matrix_basis == before[p.name]['basis'] for p in rig.pose.bones
                   if 'Hand' in p.name and p.name[-1:] in {'1', '2', '3'})
    dg = bpy.context.evaluated_depsgraph_get()
    assert meshes and all(math.isfinite(c) for m in meshes for v in m.evaluated_get(dg).data.vertices for c in v.co)
    change = max(abs(v) for p in rig.pose.bones for row in (p.matrix_basis - before[p.name]['basis']) for v in row)
    assert change > .1
    # Independent transport of actual source segment directions, including A-pose calibration.
    conversion = Matrix(((1, 0, 0), (0, 0, -1), (0, 1, 0)))
    anchor = rig.pose.bones['Root'].matrix.to_quaternion().to_matrix() @ rig.data.bones['Root'].matrix_local.to_quaternion().to_matrix().transposed()
    errors = []
    for name in ('LeftArm', 'RightArm', 'LeftForeArm', 'RightForeArm'):
        source = result['joints'][name]
        expected = anchor @ conversion @ Matrix(source['rotation']) @ Matrix(source['neutral_rotation']).transposed() @ Vector(source['neutral_direction'])
        actual = rig.pose.bones[name].tail - rig.pose.bones[name].head
        errors.append(actual.normalized().angle(expected.normalized()))
    assert max(errors) < .001, errors
    bpy.ops.wm.save_as_mainfile(filepath=str(out / ('full.blend' if hands else 'body.blend')))
    rows.append(dict(hands=hands, image_sha256=request['input_sha256'], pose_sha256=ip.sha(folder / 'pose.json'),
                     worker_wall_seconds=wall, diagnostics=result['diagnostics'], joints=len(result['joints']),
                     arm_direction_error_rad=max(errors), same_objects_and_action=True, rest_and_geometry_preserved=True,
                     finite_skin_deformation=True, folder=str(folder)))
receipt = dict(passed=True, version=addon.exporter.VERSION, sam_neural_inference_tested=True,
               source_revision=addon.sam_pose_protocol.SAM_REV, avatar_vertices=sum(len(m.data.vertices) for m in meshes),
               cases=rows, accuracy_limit='One upstream demonstration image; no statistical pose-accuracy benchmark',
               memory_limit='Torch peak allocated bytes; not total GPU usage or proof of fit on physical 16 GB hardware')
(out / 'results.json').write_text(json.dumps(receipt, indent=2))
print('IMAGE_POSE_NEURAL_ACCEPTANCE', json.dumps(receipt), flush=True)
