"""Protected painted rerig, optional joints and distinct per-hand controls."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import bpy
import numpy as np
from mathutils import Vector
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import placement,skinning,regions,rig_modules,workflow,motion_apply,motion_data,motion_jobs,exporter,hand_pose
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source/'one-click-review.blend'),load_ui=False)
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
for o in [rig,*meshes]:o.animation_data_clear()
names=[b.name for b in rig.data.bones if b.use_deform]
mesh=meshes[0]
# Use the production mask operator rather than guessing its attribute name.
workflow.select(bpy.context,rig,meshes)
for m in meshes:
    for v in m.data.vertices:v.select=False
for v in mesh.data.vertices[:12]:v.select=True
bpy.context.view_layer.objects.active=mesh
assert bpy.ops.local_character.protect_region(enabled=True)=={'FINISHED'}
mesh.vertex_groups[names[0]].lock_weight=True;rig.data.bones['RightToeBase']['lc_joint_locked']=True
before=skinning._digest(rig,meshes);weights=[regions.dense_weights(m,names) for m in meshes]
folder=placement.prepare(bpy.context,meshes,rig,parent=output)
placement.start(folder)
while skinning.poll(folder)['status']=='running':time.sleep(.2)
assert skinning.poll(folder)['status']=='complete',(folder/'worker.log').read_text()
_,rerig,copies,_=placement.apply(bpy.context,folder)
assert before==skinning._digest(rig,meshes)
for m,a,b in zip(copies,weights,meshes):
    assert np.array_equal(regions.dense_weights(m,names),a)
    assert [g.lock_weight for g in m.vertex_groups]==[g.lock_weight for g in b.vertex_groups]
assert rerig.data.bones['RightToeBase'].head_local==rig.data.bones['RightToeBase'].head_local
initial={b.name:b.matrix_local.copy() for b in rerig.data.bones};original=skinning._digest(rerig,copies)
for kind,offset in [('LEFT_EYE',Vector((.025,-.05,0))),('RIGHT_EYE',Vector((-.025,-.05,0))),('JAW',Vector((0,-.02,-.06))),('SOCKET',Vector((0,0,0)))]:
    parent=rerig.data.bones['RightHand'] if kind=='SOCKET' else rerig.data.bones['Head']
    bpy.context.scene.cursor.location=rerig.matrix_world@(parent.head_local+offset)
    _,rerig,copies=rig_modules.add(bpy.context,rerig,copies,kind,'RightHand','WeaponSocket')
assert all(rerig.data.bones[n].matrix_local==matrix for n,matrix in initial.items())
assert len(rerig.data.bones)==57 and not rerig.data.bones['WeaponSocket'].use_deform
assert {e['human'] for e in addon.skeleton.resolve_mapping(rerig.data.bones)} >= {'LeftEye','RightEye','Jaw'}
for m,a in zip(copies,weights):assert np.array_equal(regions.dense_weights(m,names),a)
roots,q=motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
hands={'Left':dict(zip(addon.skeleton.FINGERS,hand_pose.PRESETS['POINT'])),'Right':dict(zip(addon.skeleton.FINGERS,hand_pose.PRESETS['FIST']))}
action=motion_apply.bake(bpy.context,rerig,roots,q,heading=True,hands=hands)
bpy.context.scene.frame_set(1)
assert abs(rerig.pose.bones['LeftHandIndex1'].rotation_quaternion.angle)<1e-4
assert abs(rerig.pose.bones['RightHandIndex1'].rotation_quaternion.angle-math.radians(45))<1e-4
assert action.get('lc_hand_pose')
bundle=exporter.export_bundle(bpy.context,rerig,copies,str(output),'OptionalControls',include_action=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output/'controls-review.blend'))
result=dict(passed=True,painted_rerig_preserved=True,joint_locks_exact=True,optional_core_rest_unchanged=True,
    bones=57,eye_jaw_mapping=True,socket_non_deforming=True,distinct_hand_poses=True,bundle=str(bundle))
(output/'results.json').write_text(json.dumps(result,indent=2));print('CONTROLS_ACCEPTANCE',json.dumps(result))
