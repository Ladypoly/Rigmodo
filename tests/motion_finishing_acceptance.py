"""Actual walk contact correction plus analytic limb reach and bind preservation."""
import importlib.util
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector
import numpy as np

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import skeleton,motion_data,motion_jobs,motion_apply,kinematics,motion_finish
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
bpy.context.scene.render.fps=30
roots,rotations=motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
masks=motion_data.contact_masks(roots,rotations)
results=[]
for angle,scale in ((0,1.),(55,1.),(55,2.)):
    rig=skeleton.create_armature(bpy.context,1.75,angle);rig.scale=(scale,)*3
    bpy.context.view_layer.update()
    baseline=motion_apply.bake(bpy.context,rig,roots,rotations,contacts=False)
    original=[]
    for frame in range(90):
        bpy.context.scene.frame_set(frame+1);original.append([tuple(rig.matrix_world@rig.pose.bones[side+'Foot'].head) for side in ('Left','Right')])
    baseline_pose=rig.data.bones['LeftArm'].matrix_local.copy()
    corrected=motion_apply.bake(bpy.context,rig,roots,rotations,contacts=True)
    positions=[];max_length_error=0.
    for frame in range(90):
        bpy.context.scene.frame_set(frame+1);positions.append([tuple(rig.matrix_world@rig.pose.bones[side+'Foot'].head) for side in ('Left','Right')])
        for side in ('Left','Right'):
            for bone in ('UpLeg','Leg'):
                pose=rig.pose.bones[side+bone];max_length_error=max(max_length_error,abs((pose.tail-pose.head).length-pose.bone.length))
    assert rig.data.bones['LeftArm'].matrix_local==baseline_pose
    original=np.asarray(original);positions=np.asarray(positions);before=[];after=[]
    for foot in range(2):
        for frame in range(2,87):
            if masks[frame-2:frame+4,foot].all():
                before.append(float(np.linalg.norm(original[frame+1,foot]-original[frame,foot])))
                after.append(float(np.linalg.norm(positions[frame+1,foot]-positions[frame,foot])))
    print('CONTACT_DIAGNOSTICS',angle,scale,corrected['lc_contact_correction'],flush=True)
    assert before and max(after)<1e-5,(max(before),max(after))
    assert max_length_error<1e-5,max_length_error
    results.append(dict(angle=angle,scale=scale,maximum_contact_ankle_step_before_m=max(before),maximum_contact_ankle_step_after_m=max(after),
        maximum_local_limb_length_error=max_length_error,diagnostics=json.loads(corrected['lc_contact_correction'])))
    original_keys=[(c.data_path,c.array_index,[(tuple(k.co),k.interpolation) for k in c.keyframe_points]) for l in corrected.layers for s in l.strips for b in s.channelbags for c in b.fcurves]
    bpy.context.scene.frame_set(1)
    first={p.name:(p.rotation_quaternion.copy(),p.location.copy()) for p in rig.pose.bones}
    bpy.context.scene.frame_set(90);travel=rig.pose.bones['Root'].location.copy()
    looped=motion_finish.loop(bpy.context,rig,8)
    assert original_keys==[(c.data_path,c.array_index,[(tuple(k.co),k.interpolation) for k in c.keyframe_points]) for l in corrected.layers for s in l.strips for b in s.channelbags for c in b.fcurves]
    bpy.context.scene.frame_set(90)
    for p in rig.pose.bones:
        if p.name!='Root':
            assert p.rotation_quaternion.rotation_difference(first[p.name][0]).angle<1e-3,p.name
            assert (p.location-first[p.name][1]).length<1e-5,p.name
    assert (rig.pose.bones['Root'].location-travel).length<1e-6
    results[-1]['loop_pose_endpoint_matches']=True
knee,end,clamped=kinematics.two_bone((0,0,0),(0,0,1),(0,0,2),(0,0,4),(0,-1,0))
assert clamped and abs(knee.length-1)<1e-6 and abs((end-knee).length-1)<1e-6
knee,end,clamped=kinematics.two_bone((0,0,0),(0,0,1),(0,0,2),(0,0,0),(0,-1,0))
assert clamped and abs(knee.length-1)<1e-6 and abs((end-knee).length-1)<1e-6
(output/'results.json').write_text(json.dumps(results,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(output/'contact-review.blend'))
print('CONTACT_ACCEPTANCE',json.dumps(results))
