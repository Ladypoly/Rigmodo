"""Check exact in-place seams, sampled angular/linear velocities and source Action safety."""
import bpy,importlib.util,json,sys
from pathlib import Path
from mathutils import Quaternion
r=Path(__file__).resolve().parents[1];out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('rigmodo_loop_test',r/'__init__.py',submodule_search_locations=[str(r)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register()
rig=a.skeleton.create_armature(bpy.context);rig.animation_data_create();action=bpy.data.actions.new('Noncyclic');rig.animation_data.action=action
for frame in range(1,41):
 for name in ('Root','Hips','LeftArm'):
  p=rig.pose.bones[name];p.rotation_mode='QUATERNION';p.rotation_quaternion=Quaternion((0,0,1),frame*.015)
  p.location.x=frame*.002
  p.keyframe_insert('rotation_quaternion',frame=frame);p.keyframe_insert('location',frame=frame)
action['lc_source_fps']=30;action['lc_in_place']=True;before=a.unimate.source_signature(rig)
loop=a.motion_finish.loop(bpy.context,rig,8);assert loop!=action and action.use_fake_user
samples={}
for frame in (1,2,39,40):
 bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();samples[frame]={n:(p.rotation_quaternion.copy(),p.location.copy()) for n,p in ((n,rig.pose.bones[n]) for n in ('Root','Hips','LeftArm'))}
for name in samples[1]:
 q0,p0=samples[1][name];q1,p1=samples[2][name];qprev,pprev=samples[39][name];qend,pend=samples[40][name]
 assert q0.rotation_difference(qend).angle<1e-5 and (p0-pend).length<1e-6
 assert ((q0.conjugated()@q1).to_exponential_map()-(qprev.conjugated()@qend).to_exponential_map()).length<1e-5
 assert ((p1-p0)-(pend-pprev)).length<1e-6
rig.animation_data.action=action;assert a.unimate.source_signature(rig)==before
result=dict(passed=True,exact_pose_seam=True,angular_and_linear_sample_velocities_matched=True,in_place_root_closed=True,original_action_preserved=True)
(out/'results.json').write_text(json.dumps(result,indent=2));print('LOOP_SEAM_ACCEPTANCE',json.dumps(result),flush=True)
