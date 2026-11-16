import bpy,addon_utils,importlib,json,sys,time
from pathlib import Path
from types import SimpleNamespace
from mathutils import Quaternion
bpy.ops.wm.read_factory_settings(use_empty=True);addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True);p=a.configuration.settings(ctx);p.video_jobs=str(out/'Jobs');p.motion_library_directory=str(out/'Library')
rig=a.skeleton.create_armature(ctx);s=ctx.scene.lc_settings;s.pose_source_rig=rig;s.motion_system='MOTIONBRICKS';s.source_loop=True;s.source_in_place=True;s.source_name='Exact Guide Loop';s.ui_step='MOTION';s.animation_view='CREATE'
ctx.scene.render.fps=24;ctx.scene.frame_start=100;original=a.motion_clips.new(ctx,rig,'Artist Guides')
for frame,angle in [(100,0),(112,.7),(124,0)]:
 for bone in rig.pose.bones:
  bone.rotation_mode='QUATERNION';bone.rotation_quaternion=Quaternion((0,1,0),angle if bone.name=='LeftArm' else 0)
  for prop in ('location','rotation_quaternion','scale'):bone.keyframe_insert(prop,frame=frame)
fake=SimpleNamespace(area=SimpleNamespace(type='VIEW_3D'),region=SimpleNamespace(type='UI',active_panel_category='Rigmodo'),scene=ctx.scene,active_object=rig,mode='POSE')
assert a.image_pose.drop_surface(fake);s.motion_system='VIDEO';assert not a.image_pose.drop_surface(fake);s.animation_view='EDIT';assert a.image_pose.drop_surface(fake);s.motion_system='MOTIONBRICKS';s.animation_view='CREATE'
assert a.motion_sources.start(ctx)=={'FINISHED'};folder=Path(s.source_job);began=time.monotonic()
while True:
 state=a.skinning.poll(folder)
 if state['status']!='running':break
 if time.monotonic()-began>180:a.skinning.cancel(folder);raise AssertionError('Keyed loop timed out')
 time.sleep(.5)
assert state['status']=='complete',(state,(folder/'worker.log').read_text(errors='replace')[-2000:]);result=json.loads((folder/'results.json').read_text());assert not result['errors'] and rig.animation_data.action==original
data=a.motion_store.read(Path(p.motion_library_directory),result['added'][0]);preview=a.motion_assets.source_rig(ctx,data);action=a.motion_sources.motion_retarget(ctx,preview,data,dict(name='Loop verification',loop=True));error=0
for frame,angle in [(1,0),(13,.7),(25,0)]:
 ctx.scene.frame_set(frame);ctx.view_layer.update();error=max(error,1-abs(preview.pose.bones['LeftArm'].rotation_quaternion.dot(Quaternion((0,1,0),angle))))
assert error<1e-5,error
entry=next(e for e in a.motion_store.catalog(Path(p.motion_library_directory))['clips'] if e['id']==result['added'][0]);assert entry['loop']
report=dict(passed=True,real_motionbricks_inference=True,exact_guides_after_loop_finishing=True,maximum_quaternion_error=error,arbitrary_start_and_24fps=True,scoped_image_drops=True,source_action_preserved=True,job=str(folder))
(out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('KEYED_SOURCE_LOOP_PASS',report)
