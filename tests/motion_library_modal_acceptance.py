import bpy,addon_utils,importlib,sys,time,json,traceback,os
from pathlib import Path
out=Path(sys.argv[sys.argv.index('--')+1]);fixture=Path(sys.argv[sys.argv.index('--')+2]);out.mkdir(parents=True,exist_ok=True)
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
bpy.context.preferences.use_preferences_save=False;bpy.context.preferences.view.show_splash=False
a.configuration.settings(bpy.context).motion_library_directory=str(out/'Library')
rig=a.skeleton.create_armature(bpy.context);objects=set(bpy.data.objects);started=time.monotonic();state={'phase':0}
def tick():
    try:
        if time.monotonic()-started>50:raise AssertionError('Modal worker timeout: '+bpy.context.scene.lc_settings.motion_status)
        window=bpy.context.window_manager.windows[0]
        area=next(ar for ar in window.screen.areas if ar.type==('VIEW_3D' if state['phase']==0 else 'FILE_BROWSER'));region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            if state['phase']==0:
                assert bpy.ops.local_character.open_motion_assets()=={'FINISHED'}
                state['phase']=1
            elif state['phase']==1:
                assert a.motion_library.start_job(bpy.context,'import',[fixture])=={'FINISHED'}
                state.update(phase=2,job=Path(bpy.context.scene.lc_settings.library_job))
            elif state['phase']==2 and not a.skinning._jobs and not a.processing_visuals._sessions:
                catalog=a.motion_store.catalog(out/'Library');assert len(catalog['clips'])==1
                assert len(bpy.context.window_manager.lc_motion_library.entries)==1
                assert set(bpy.data.objects)==objects and rig.animation_data is None
                assert not a.processing_visuals._sessions
                (out/'results.json').write_text(json.dumps(dict(passed=True,real_modal_batch_import=True,asset_browser_context=True,worker_finished=True,catalog_refreshed=True,no_new_scene_objects=True,processing_effects_cleaned=True),indent=2))
                os._exit(0)
    except Exception:
        (out/'error.txt').write_text(traceback.format_exc());os._exit(1)
    return .2
bpy.app.timers.register(tick,first_interval=1)
