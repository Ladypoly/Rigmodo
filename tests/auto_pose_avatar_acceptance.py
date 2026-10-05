# SPDX-License-Identifier: GPL-3.0-or-later
"""Private skinned-avatar acceptance; input geometry and renders stay outside Git."""
import addon_utils
import importlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Vector

assert bpy.app.background and '--factory-startup' in sys.argv
args = sys.argv[sys.argv.index('--') + 1:]
fixture, out = Path(args[0]), Path(args[1]); out.mkdir(parents=True, exist_ok=True)
addon_utils.enable('bl_ext.user_default.local_character', default_set=True)
addon = importlib.import_module('bl_ext.user_default.local_character'); ap = addon.auto_pose
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()
with bpy.data.libraries.load(str(fixture), link=False) as (source, destination): destination.objects = source.objects
for obj in destination.objects:
    if obj:
        bpy.context.scene.collection.objects.link(obj); obj.hide_set(False); obj.hide_viewport = False
rig = next(o for o in destination.objects if o and o.type == 'ARMATURE')
meshes = [o for o in destination.objects if o and o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
for obj in bpy.context.selected_objects: obj.select_set(False)
rig.select_set(True); bpy.context.view_layer.objects.active = rig
bpy.ops.object.mode_set(mode='POSE'); rig.lc_auto_pose.enabled = True
ap.validate(bpy.context, rig)
snapshot = ap.channel_snapshot(rig)
action = rig.animation_data.action if rig.animation_data else None
counts = (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures), len(bpy.data.actions))
t = ap.Transaction(bpy.context, rig, 'LeftHand')
origin = Vector(t.model.reference[1][t.model.semantic['LeftHand']]); height = t.model.height
times = []; residuals = []; before_vertices = [np.array([v.co[:] for v in mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]) for mesh in meshes]
for index in range(60):
    goal = origin + Vector((-.04, -.035, .025 + .008 * math.sin(index * .15))) * height
    start = time.perf_counter(); result = t.apply(goal); bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    evaluated = [np.array([v.co[:] for v in mesh.evaluated_get(dg).data.vertices]) for mesh in meshes]
    times.append((time.perf_counter() - start) * 1000)
    residual = (rig.pose.bones[t.model.names[t.model.semantic['LeftHand']]].head - goal).length / height
    residuals.append(residual)
    assert np.isfinite(np.concatenate(evaluated)).all()
    assert result.pin_error < height * 2e-5
    assert max(p.location.length for p in rig.pose.bones if addon.skeleton.canonical_name(p.name) not in {'Root','Hips'}) < 1e-5
    assert residual < .002, residual
assert any(np.max(np.abs(a - b)) > .001 for a, b in zip(before_vertices, evaluated))
t.close(cancel=True); bpy.context.view_layer.update()
assert all(max(abs(v) for row in (p.matrix_basis - snapshot[p.name]['basis']) for v in row) < 1e-6 for p in rig.pose.bones)
assert counts == (len(bpy.data.objects), len(bpy.data.meshes), len(bpy.data.armatures), len(bpy.data.actions))
assert (rig.animation_data.action if rig.animation_data else None) == action
# Capture the resulting actual body pose without changing its source Action.
t = ap.Transaction(bpy.context, rig, 'LeftHand'); t.apply(origin + Vector((-.04,-.035,.025)) * height); t.close()
bpy.context.view_layer.update(); addon.motion_keyframes.capture(bpy.context, rig)
assert (rig.animation_data.action if rig.animation_data else None) == action
# Explicit whole-pose keys produce exportable direct-bone Actions in both profiles.
rig.animation_data.action = None
bpy.context.scene.frame_set(1)
assert bpy.ops.local_character.auto_pose_key()=={'FINISHED'}
bpy.context.scene.frame_set(20)
t=ap.Transaction(bpy.context,rig,'LeftHand')
next_goal=Vector(t.model.reference[1][t.model.semantic['LeftHand']])+Vector((-.025,-.02,.02))*height
t.apply(next_goal);t.close()
assert bpy.ops.local_character.auto_pose_key()=={'FINISHED'}
bpy.ops.object.mode_set(mode='OBJECT')
for mesh in meshes:mesh.data.materials.clear()
exports=[]
import tempfile
export_root=Path(tempfile.mkdtemp(prefix='exports-',dir=out))
for profile in ('HUMANOID','GENERIC'):
    bundle=addon.exporter.export_bundle(bpy.context,rig,meshes,str(export_root),'AutoPose'+profile,profile,include_action=True)
    exports.append(str(bundle))
    for mesh in meshes:addon.exporter._prune(mesh,rig)
    sys.path.insert(0,str(Path(__file__).parent));import motion_reference
    motion_reference.write(rig,meshes,bundle,frames=(1,5,10,15,20))

# Private visual inspection view, independent of the live user's camera/scene.
bpy.ops.object.mode_set(mode='OBJECT')
for obj in bpy.context.scene.objects:
    if obj not in meshes and obj != rig: obj.hide_render = True
camera_data = bpy.data.cameras.new('AcceptanceCamera'); camera = bpy.data.objects.new('AcceptanceCamera', camera_data)
bpy.context.scene.collection.objects.link(camera); bpy.context.scene.camera = camera
points = [mesh.matrix_world @ v.co for mesh in meshes for v in mesh.data.vertices]
lo = Vector(tuple(min(p[k] for p in points) for k in range(3))); hi = Vector(tuple(max(p[k] for p in points) for k in range(3)))
center = (lo + hi) * .5; span = max(hi.z - lo.z, hi.x - lo.x)
camera.location = center + Vector((span * .45, -span * 2.2, span * .2))
camera.rotation_euler = (center - camera.location).to_track_quat('-Z','Y').to_euler()
camera.data.type = 'ORTHO'; camera.data.ortho_scale = span * 1.4
scene = bpy.context.scene; scene.render.engine = 'BLENDER_WORKBENCH'; scene.render.resolution_x = 700; scene.render.resolution_y = 700; scene.render.resolution_percentage = 100
scene.display.shading.light = 'STUDIO'; scene.display.shading.color_type = 'MATERIAL'; scene.display.shading.show_shadows = True
scene.render.filepath = str(out / 'avatar-pose.png'); bpy.ops.render.render(write_still=True)
report = dict(passed=True, samples=60, vertices=sum(len(m.data.vertices) for m in meshes), bones=len(rig.data.bones),
              max_target_error_height=max(residuals), full_pipeline_median_ms=statistics.median(times), full_pipeline_p95_ms=float(np.percentile(times,95)),
              scope='owned transaction solve, all bone writes, depsgraph and skinned vertex evaluation; excludes viewport drawing',
              no_helpers=True, action_preserved=True, cancel_restored=True, kimodo_capture_passed=True)
report['two_pose_action_exported_profiles']=['HUMANOID','GENERIC']
report['export_scope']='Blender bundle creation; existing Unity importer is unchanged'
report['private_exports']=exports
(out / 'avatar-results.json').write_text(json.dumps(report,indent=2) + '\n')
print('AUTO_POSE_AVATAR_COMPLETE', json.dumps(report), flush=True)
