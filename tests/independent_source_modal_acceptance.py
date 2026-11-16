"""Cancel real video inference through the shared GUI progress controls."""
import bpy,addon_utils,importlib,json,sys,time,os,traceback
from pathlib import Path
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
ctx.preferences.use_preferences_save=False;ctx.preferences.view.show_splash=False
p=a.configuration.settings(ctx);p.video_jobs=str(out/'Jobs');p.motion_library_directory=str(out/'Library')
s=ctx.scene.lc_settings;s.ui_step='MOTION';s.animation_view='CREATE';s.motion_system='VIDEO';s.video_input='FILES';s.video_path='R:/AI/Rigmodo/Jobs/Acceptance/full-avatar-walk/avatar-walk.mp4';s.source_loop=False
state=dict(started=time.monotonic(),phase=0,objects=set(bpy.data.objects))
def tick():
 try:
  if time.monotonic()-state['started']>90:raise AssertionError('Source modal cancellation timed out')
  window=ctx.window_manager.windows[0];area=next(ar for ar in window.screen.areas if ar.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
  with ctx.temp_override(window=window,area=area,region=region):
   if state['phase']==0:
    assert bpy.ops.local_character.create_motion_source()=={'FINISHED'};state.update(phase=1,folder=Path(s.source_job));state['process']=a.skinning._jobs[str(state['folder'])]['process']
   elif state['phase']==1:
    active=state['folder']/'active.json'
    if active.is_file():
     job=Path(json.loads(active.read_text())['folder']);progress=job/'progress.json'
     if progress.is_file() and 'Extracting' in json.loads(progress.read_text()).get('phase',''):
      assert a.processing_visuals.active(ctx.scene);bpy.ops.local_character.cancel_processing();state['phase']=2
   elif not a.skinning._jobs:
    assert state['process'].poll() is not None and not a.processing_visuals.active(ctx.scene)
    assert set(bpy.data.objects)==state['objects'] and 'torch' not in sys.modules
    status=json.loads((state['folder']/'status.json').read_text());assert status['status']=='cancelled',status
    report=dict(passed=True,real_video_worker_cancelled=True,source_scene_unchanged=True,main_blender_has_no_torch=True,processing_visuals_cleaned=True,owned_process_exited=True)
    (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');os._exit(0)
 except Exception:
  a.skinning.cancel_all();(out/'error.txt').write_text(traceback.format_exc(),encoding='utf-8');os._exit(1)
 return .25
bpy.app.timers.register(tick,first_interval=1.)
