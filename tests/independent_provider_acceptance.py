import bpy,addon_utils,importlib,json,sys,time
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True);addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True);mode=sys.argv[sys.argv.index('--')+2]
if mode=='UNIMATE':bpy.ops.wm.open_mainfile(filepath='R:/BLENDER/Rigmodo/Scorpion_WalkFast_Attack.blend',load_ui=False)
p=a.configuration.settings(ctx);p.video_jobs=str(out/'Jobs');p.motion_library_directory=str(out/'Library');s=ctx.scene.lc_settings
before=set(bpy.data.objects);actions={o:o.animation_data.action if o.animation_data else None for o in ctx.scene.objects}
if mode=='UNIMATE':
 rig=next(o for o in ctx.scene.objects if o.type=='ARMATURE');signature=a.skinning._digest(rig,a.motion_jobs.character_meshes(ctx,rig));s.motion_system='UNIMATE';s.pose_source_rig=rig;s.motion_prompt='A scorpion strikes forward with its tail.';s.motion_duration=1.;s.source_loop=False;s.source_in_place=False;s.source_name='Independent Scorpion Attack'
else:
 from urllib.request import urlopen
 with urlopen(p.comfy_url+'/queue',timeout=5) as response:q=json.load(response)
 assert not q['queue_running'] and not q['queue_pending'],'Shared ComfyUI is busy; do not interrupt it'
 s.motion_system='VIDEO';s.video_input='COMFY';s.video_reference='R:/AI/Rigmodo/Jobs/Acceptance/full-avatar-walk/0000.png';s.motion_prompt='Standing pose';s.motion_duration=2;s.source_loop=False;s.source_in_place=False;s.source_name='Independent Comfy Capture'
 graph={'image':dict(class_type='LoadImage',inputs=dict(image='REPLACED')),'repeat':dict(class_type='RepeatImageBatch',inputs=dict(image=['image',0],amount=48)),'video':dict(class_type='CreateVideo',inputs=dict(images=['repeat',0],fps=24)),'save':dict(class_type='SaveVideo',inputs=dict(video=['video',0],filename_prefix='REPLACED',format='mp4',**{'format.codec':'h264'}))}
 workflow=out/'cpu-video-workflow.json';workflow.write_text(json.dumps(graph));p.comfy_workflow=str(workflow);p.comfy_output_node='save';p.comfy_bindings=json.dumps(dict(image='image.image',output_prefix='save.filename_prefix'))
assert a.motion_sources.start(ctx)=={'FINISHED'};folder=Path(s.source_job);print('EXTRA_SOURCE_JOB',mode,folder,flush=True);began=time.monotonic()
while True:
 state=a.skinning.poll(folder)
 if state['status']!='running':break
 if time.monotonic()-began>600:a.skinning.cancel(folder);raise AssertionError('Source generation timed out')
 time.sleep(.5)
assert state['status']=='complete',(state,(folder/'worker.log').read_text(errors='replace')[-3000:])
assert bpy.ops.local_character.finish_motion_source()=={'FINISHED'};result=json.loads((folder/'results.json').read_text());assert len(result['added'])==1
assert set(bpy.data.objects)==before and all((o.animation_data.action if o.animation_data else None)==action for o,action in actions.items())
data=a.motion_store.read(Path(p.motion_library_directory),result['added'][0]);a.motion_store.validate(data)
report=dict(passed=True,system=mode,seconds=round(time.monotonic()-began,2),job=str(folder),source_scene_unchanged=True,reusable_source=True,h3_sampling_tested=False)
if mode=='UNIMATE':
 assert signature==a.skinning._digest(rig,a.motion_jobs.character_meshes(ctx,rig))
 assert any(str(label).strip() for label in data['labels']);report.update(creature_joint_labels_preserved=True,original_scorpion_preserved=True)
else:
 cleanup=json.loads((folder/'captures/0000/comfy-memory.json').read_text());assert cleanup['released'],cleanup;report.update(real_comfy_api=True,actual_gemx_capture=True,owned_models_released=True,no_avatar=True)
(out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('EXTRA_SOURCE_PASS',json.dumps(report),flush=True)
