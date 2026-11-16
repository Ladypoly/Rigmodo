"""Real inference and library-to-many-character acceptance, using isolated fixtures."""
import bpy,addon_utils,importlib,json,sys,time,traceback
from pathlib import Path
import numpy as np
from mathutils import Quaternion
bpy.ops.wm.read_factory_settings(use_empty=True);addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
p=a.configuration.settings(ctx);p.video_jobs=str(out/'Jobs');p.motion_library_directory=str(out/'Library');p.motion_steps=10
s=ctx.scene.lc_settings;report={}
def run(label,files=()):
    assert a.motion_sources.start(ctx,files)=={'FINISHED'}
    folder=Path(s.source_job);print('SOURCE_ACCEPTANCE_JOB',label,str(folder),flush=True);began=time.monotonic()
    while True:
        state=a.skinning.poll(folder)
        if state['status']!='running':break
        if time.monotonic()-began>600:a.skinning.cancel(folder);raise AssertionError(label+' timed out')
        time.sleep(.5)
    assert state['status']=='complete',(label,state,(folder/'worker.log').read_text(errors='replace')[-4000:])
    assert bpy.ops.local_character.finish_motion_source()=={'FINISHED'}
    result=json.loads((folder/'results.json').read_text());report[label]=dict(job=str(folder),seconds=round(time.monotonic()-began,2),**result)
    (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return result
video=Path('R:/AI/Rigmodo/Jobs/Acceptance/full-avatar-walk/avatar-walk.mp4');bad=out/'bad.mp4';bad.write_bytes(b'Invalid video acceptance fixture')
s.motion_system='VIDEO';s.video_input='FILES';s.capture_whole_video=True;s.source_loop=True;s.source_in_place=True;s.source_name=''
video_result=run('video_batch',[video,video,bad]);assert len(video_result['completed'])==2 and len(video_result['added'])==1 and len(video_result['errors'])==1
assert not ctx.scene.objects and not bpy.data.actions
report['video_without_avatar']=True;report['batch_dedup_and_failure_isolation']=True
s.motion_system='KIMODO';s.motion_use_keyframes=False;s.source_loop=False;s.source_in_place=False;s.motion_duration=1.;s.source_name='Independent Wave';s.motion_prompt='A person waves their right hand.'
kimodo=run('kimodo');assert not ctx.scene.objects and not bpy.data.actions
report['kimodo_without_avatar']=True
rig=a.skeleton.create_armature(ctx,1.75,35);s.pose_source_rig=rig;ctx.scene.render.fps=24;ctx.scene.frame_start=100
action=a.motion_clips.new(ctx,rig,'Source pose keys');s.motion_system='MOTIONBRICKS';s.source_name='Independent Pose Transition'
for frame,angle in [(100,0),(112,.7),(124,0)]:
    for bone in rig.pose.bones:
        bone.rotation_mode='QUATERNION';bone.rotation_quaternion=Quaternion((0,1,0),angle if bone.name=='LeftArm' else 0)
        for prop in ('rotation_quaternion','location','scale'):bone.keyframe_insert(prop,frame=frame)
before=a.skinning._digest(rig,[]);ctx.scene.frame_set(107)
mb=run('motionbricks');assert rig.animation_data.action==action and a.skinning._digest(rig,[])==before and ctx.scene.frame_current==107
data=a.motion_store.read(Path(p.motion_library_directory),mb['added'][0]);preview=a.motion_assets.source_rig(ctx,data,'Guide verification');a.motion_retarget.apply(ctx,preview,data,'Guide verification')
err=0
for frame,angle in [(1,0),(13,.7),(25,0)]:
    ctx.scene.frame_set(frame);ctx.view_layer.update();err=max(err,1-abs(preview.pose.bones['LeftArm'].rotation_quaternion.dot(Quaternion((0,1,0),angle))))
assert err<1e-5,err
data_block=preview.data;bpy.data.objects.remove(preview,do_unlink=True);bpy.data.armatures.remove(data_block)
report['motionbricks_ordinary_keyframes']=True;report['anchor_quaternion_error']=err
ctx.scene.frame_set(107);objects=set(bpy.data.objects);selected=list(ctx.selected_objects);active=ctx.view_layer.objects.active
a.motion_sources.refresh(ctx,[video_result['added'][0]])
assert bpy.ops.local_character.preview_source_motion()=={'FINISHED'};assert len(bpy.data.objects)==len(objects)+1
assert bpy.ops.local_character.stop_source_preview()=={'FINISHED'};assert set(bpy.data.objects)==objects and ctx.scene.frame_current==107 and ctx.view_layer.objects.active==active
report['disposable_preview_restores_scene']=True
other=a.skeleton.create_armature(ctx,2.1,35)
for o in ctx.selected_objects:o.select_set(False)
for o in (rig,other):o.select_set(True)
ctx.view_layer.objects.active=rig;s.retarget_selected_characters=True;s.motion_contacts=True;s.retarget_in_place=True;s.retarget_loop='SOURCE'
originals={o:a.skinning._digest(o,[]) for o in (rig,other)}
assert bpy.ops.local_character.retarget_sources()=={'FINISHED'}
assert not json.loads(s.retarget_report),s.retarget_report
for o in (rig,other):
    assert a.skinning._digest(o,[])==originals[o]
    assert o.animation_data.action.get('lc_clip_loop') and o.animation_data.action.get('lc_contact_report')
    assert o.animation_data.action.lc_clip_owner==o
assert rig.animation_data.action!=other.animation_data.action
assert other.animation_data.action not in [v[0] for v in a.motion_clips.available(rig)]
report['retarget_two_proportions_contacts_loop']=True;report['separate_character_actions']=True
assert not a.skinning._jobs
report['passed']=True;(out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('INDEPENDENT_ACCEPTANCE_PASS',json.dumps(report),flush=True)
