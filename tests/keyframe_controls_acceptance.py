"""Pose transport guards, twist coherence, cancellation and unchanged model channels."""
import importlib.util,json,sys,shutil,math
from pathlib import Path
import bpy,numpy as np
from mathutils import Quaternion
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import motion_keyframes,motion_jobs,motion_apply,motion_data,skeleton,skinning,twists
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
roots,rotations=motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
bpy.context.scene.render.fps=30
rig=skeleton.create_armature(bpy.context,1.75,35);bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode='EDIT');modules=[]
for side in ('Left','Right'):
    bone=rig.data.edit_bones[side+'ForeArm'];helper=rig.data.edit_bones.new(side+'ForeArmTwist');helper.head=bone.head;helper.tail=bone.tail;helper.roll=bone.roll;helper.parent=bone.parent
    modules.append(dict(source=bone.name,helper=helper.name,fraction=.5))
bpy.ops.object.mode_set(mode='OBJECT');rig['lc_twists']=json.dumps(modules)
motion_apply.bake(bpy.context,rig,roots,rotations)
for frame in (1,45,90):
    bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();motion_keyframes.capture(bpy.context,rig)
before=rig[motion_keyframes.PROPERTY]
bpy.context.scene.frame_set(45);rig.pose.bones['LeftForeArm'].rotation_quaternion=Quaternion((0,1,0),.5);bpy.context.view_layer.update()
try:motion_keyframes.capture(bpy.context,rig);raise AssertionError('Stale twist pose accepted')
except ValueError as error:assert 'Twist Pose' in str(error)
assert before==rig[motion_keyframes.PROPERTY];twists.update_pose(rig);bpy.context.view_layer.update();motion_keyframes.capture(bpy.context,rig)
folder=motion_jobs.prepare(bpy.context,rig,'walk',90,parent=output,keyframes=True)
for name in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copy2(motion_jobs.cache()/'evaluation/walk'/name,folder/name)
motion_jobs.finish(folder);skinning._state(folder,'complete');_,copy,_,action,_=motion_apply.apply(bpy.context,folder)
maximum=0.
for frame in (2,43,46,49,75,88):
    bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
    for module in modules:
        expected=twists.reduced(copy.pose.bones[module['source']].rotation_quaternion,.5)
        actual=copy.pose.bones[module['helper']].rotation_quaternion
        maximum=max(maximum,1-abs(expected.dot(actual)))
assert maximum<1e-6,maximum
settings=bpy.context.scene.lc_settings
saved=rig[motion_keyframes.PROPERTY];bad=json.loads(saved);bad['poses'][0]['basis']['Hips']['rotation'][0]=float('nan');rig[motion_keyframes.PROPERTY]=json.dumps(bad)
counts=(len(bpy.data.objects),len(bpy.data.actions))
try:motion_jobs.prepare(bpy.context,rig,'walk',90,parent=output,keyframes=True);raise AssertionError('Malformed pose accepted')
except ValueError:pass
assert counts==(len(bpy.data.objects),len(bpy.data.actions));rig[motion_keyframes.PROPERTY]=saved
for frames,start,in_place in ((15,1,False),(90,10,False),(90,1,True)):
    try:motion_keyframes.prepare(bpy.context,rig,frames,start,in_place);raise AssertionError('Invalid interval/in-place accepted')
    except ValueError:pass
cancel=motion_jobs.prepare(bpy.context,rig,'walk',90,parent=output,keyframes=True);motion_jobs.start(cancel);skinning.cancel(cancel)
assert not skinning._jobs and skinning.poll(cancel)['status']=='cancelled'
bpy.context.scene.frame_set(-4);motion_keyframes.capture(bpy.context,rig)
for obj in bpy.context.selected_objects:obj.select_set(False)
rig.select_set(True);bpy.context.view_layer.objects.active=rig
assert bpy.ops.local_character.key_pose(frame=-4,remove=True)=={'FINISHED'}
assert len(motion_keyframes.data(rig)['poses'])==3
bpy.context.scene.frame_set(-4,subframe=.75);motion_keyframes.capture(bpy.context,rig)
bpy.context.scene.frame_set(-2)
assert bpy.ops.local_character.key_pose(frame=-3.25)=={'FINISHED'}
assert abs(bpy.context.scene.frame_current+bpy.context.scene.frame_subframe+3.25)<1e-6
assert bpy.ops.local_character.key_pose(frame=-3.25,remove=True)=={'FINISHED'}
assert bpy.ops.local_character.key_pose(clear=True)=={'FINISHED'} and not motion_keyframes.data(rig)['poses']
result=dict(passed=True,twist_correction_coherent=True,max_twist_dot_error=maximum,stale_twist_capture_rejected=True,
    invalid_interval_and_in_place_rejected=True,malformed_pose_rejected_before_allocation=True,verification_cancelled=True,negative_frame_remove_and_clear=True,negative_subframe_recall=True,cached_arrays_for_controls=True)
(output/'results.json').write_text(json.dumps(result,indent=2));print('KEYFRAME_CONTROLS_ACCEPTANCE_PASSED',json.dumps(result))
