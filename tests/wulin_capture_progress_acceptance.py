import bpy,addon_utils,importlib,json,sys,time
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True);p=a.configuration.settings(ctx);p.video_jobs=str(out/'Jobs');p.motion_library_directory=str(out/'Library');s=ctx.scene.lc_settings
s.motion_system='VIDEO';s.video_input='FILES';s.video_path='C:/Users/Elin/Downloads/wulin2.mp4';s.capture_whole_video=False;s.video_start=0;s.motion_duration=2;s.source_loop=False;s.source_in_place=False;s.source_name='Wulin progress acceptance'
assert a.motion_sources.start(ctx)=={'FINISHED'};folder=Path(s.source_job);states={};began=time.monotonic();print('WULIN_PROGRESS_JOB',folder,flush=True)
while True:
 state=a.skinning.poll(folder)
 if state.get('total'):
  key=state['phase'];previous=states.get(key,dict(completed=0));assert state['completed']>=previous['completed'] and 0<=state['completed']<=state['total'];states[key]=state
 if state['status']!='running':break
 if time.monotonic()-began>180:a.skinning.cancel(folder);raise AssertionError('Progress capture timed out')
 time.sleep(.1)
assert state['status']=='complete',(state,(folder/'worker.log').read_text(errors='replace')[-2500:])
assert len(states)>=3,states;assert bpy.ops.local_character.finish_motion_source()=={'FINISHED'};assert len(ctx.window_manager.lc_motion_library.entries)==1
report=dict(passed=True,real_capture=True,job=str(folder),measured_stages=states,working_list_only_created_motion=True)
(out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print('WULIN_PROGRESS_PASS',json.dumps(report),flush=True)
