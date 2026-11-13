"""Real official SOMA ONNX inference, sparse Action guides, stale rejection and export."""
import bpy,importlib.util,json,math,sys,time
from pathlib import Path
import numpy as np
from mathutils import Quaternion
root=Path(__file__).resolve().parents[1];out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('rigmodo_mb_test',root/'__init__.py',submodule_search_locations=[str(root)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register();bpy.context.preferences.addons.new().module=spec.name
scene=bpy.context.scene;scene.render.fps=24
if '--avatar' in sys.argv:
    before_objects=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=sys.argv[sys.argv.index('--avatar')+1])
    rig=next(o for o in set(bpy.data.objects)-before_objects if o.type=='ARMATURE')
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    if 'Root' not in rig.data.bones:
        bpy.ops.object.mode_set(mode='EDIT');bone=rig.data.edit_bones.new('Root');bone.head=(0,0,0);bone.tail=(0,0,.1);bone.use_deform=False
        hips=next(b for b in rig.data.edit_bones if a.skeleton.canonical_name(b.name)=='Hips');hips.parent=bone;bpy.ops.object.mode_set(mode='OBJECT')
else:rig=a.skeleton.create_armature(bpy.context,1.75,35)
mapping=a.motion_jobs.validate_rig(bpy.context,rig)
rig.animation_data_create();rig.animation_data.action=bpy.data.actions.new('Artist pose keys')
for frame,angle in ((1,0.),(25,-.7),(49,.3)):
    for p in rig.pose.bones:p.matrix_basis.identity();p.rotation_mode='QUATERNION'
    rig.pose.bones[mapping['LeftArm'].name].rotation_quaternion=Quaternion((0,1,0),angle)
    rig.pose.bones['Root'].location.x=(frame-1)/120
    for p in rig.pose.bones:
        for prop in ('rotation_quaternion','location','scale'):p.keyframe_insert(prop,frame=frame)
source_action=rig.animation_data.action;saved=[]
for frame in (1,25,49):
    scene.frame_set(frame);bpy.context.view_layer.update();saved.append({p.name:np.asarray(p.matrix).copy() for p in rig.pose.bones})
scene.frame_set(7);bpy.context.view_layer.update();before=a.skinning._digest(rig,[]);signature=a.unimate.source_signature(rig)
folder=a.motionbricks.prepare(bpy.context,rig,101,False,str(a.motionbricks.cache()),parent=out);a.motionbricks.start(folder)
(out/'job.txt').write_text(str(folder))
started=time.monotonic()
while True:
    status=a.skinning.poll(folder)
    if status['status']!='running':break
    if time.monotonic()-started>180:raise AssertionError('Inference timed out')
    time.sleep(.3)
assert status['status']=='complete',(status,(folder/'worker.log').read_text(errors='replace')[-3000:])
original=(folder/'request.json').read_bytes();(folder/'request.json').write_bytes(original+b' ')
counts=(len(bpy.data.objects),len(bpy.data.actions))
try:a.motion_apply.apply(bpy.context,folder);raise AssertionError('Changed request accepted')
except ValueError:pass
assert counts==(len(bpy.data.objects),len(bpy.data.actions))
(folder/'request.json').write_bytes(original)
collection,target,meshes,action,diagnostics=a.motion_apply.apply(bpy.context,folder,contacts=True,heading=True)
assert scene.frame_current==7 and source_action==rig.animation_data.action and before==a.skinning._digest(rig,[]) and signature==a.unimate.source_signature(rig)
error=0.
for frame,expected in zip((1,25,49),saved):
    scene.frame_set(frame);bpy.context.view_layer.update()
    for p in target.pose.bones:error=max(error,float(np.max(np.abs(np.asarray(p.matrix)-expected[p.name]))))
assert error<1e-5,error
assert target['lc_motion_provider']=='motionbricks_soma30'
frames=sorted({float(k.co.x) for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves for k in c.keyframe_points})
sample=[]
for frame in frames[::10]:
    scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update();sample.append(tuple(target.pose.bones[mapping['LeftHand'].name].head))
assert np.ptp(np.asarray(sample),axis=0).max()>.01
for obj in bpy.context.selected_objects:obj.select_set(False)
target.select_set(True);bpy.context.view_layer.objects.active=target
report=dict(passed=True,actual_motionbricks_inference=True,diagnostics=diagnostics,artist_anchor_max_matrix_error=error,source_action_rest_preserved=True,changed_request_rejected_before_allocation=True,scene_fps_preserved=scene.render.fps==24,source_frames=len(frames))
if meshes:
    bundle=a.exporter.export_bundle(bpy.context,target,meshes,str(out/'export'),'MotionBricksAvatar','HUMANOID',True,False)
    report.update(real_avatar=True,fbx_export=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'motionbricks-review.blend'),copy=True)
(out/'results.json').write_text(json.dumps(report,indent=2));print('MOTIONBRICKS_ACCEPTANCE',json.dumps(report),flush=True)
