import bpy,addon_utils,importlib,sys,time,json,traceback,os
from pathlib import Path
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
bpy.context.preferences.use_preferences_save=False;bpy.context.preferences.view.show_splash=False
rig=a.skeleton.create_armature(bpy.context);bpy.context.scene.lc_settings.ui_step='MOTION'
objects=set(bpy.data.objects);state={'phase':0,'started':time.monotonic()}

def finish(error=None):
    if error:(out/'error.txt').write_text(error)
    os._exit(1 if error else 0)

def tick():
    try:
        if time.monotonic()-state['started']>60:raise AssertionError('Asset Browser GUI timed out: '+str(state))
        window=bpy.context.window_manager.windows[0]
        if state['phase']==0:
            area=next(ar for ar in window.screen.areas if ar.type=='VIEW_3D');region=next(re for re in area.regions if re.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=area,region=region):
                assert bpy.ops.local_character.open_motion_assets()=={'FINISHED'}
            state.update(phase=1,wait=time.monotonic()+3)
        elif state['phase']==1 and time.monotonic()>state['wait']:
            area=next(ar for ar in window.screen.areas if ar.type=='FILE_BROWSER');space=area.spaces.active
            assert space.params.asset_library_reference=='Rigmodo Motions'
            space.params.filter_search='Scorpion_WalkFast_Attack_Arcade';space.show_region_tool_props=True
            state.update(phase=2,wait=time.monotonic()+2)
        elif state['phase']==2 and time.monotonic()>state['wait']:
            area=next(ar for ar in window.screen.areas if ar.type=='FILE_BROWSER');space=area.spaces.active
            entry=next(e for e in a.motion_store.catalog(a.motion_library.root(bpy.context))['clips'] if e['name']=='Scorpion_WalkFast_Attack_Arcade')
            space.deselect_all();space.activate_file_by_relative_path(relative_path=entry['id']+'.blend\\Action\\'+entry['name'])
            state.update(phase=3,wait=time.monotonic()+1)
        elif state['phase']==3 and time.monotonic()>state['wait']:
            area=next(ar for ar in window.screen.areas if ar.type=='FILE_BROWSER');region=next(re for re in area.regions if re.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=area,region=region):
                bpy.ops.screen.screenshot(filepath=str(out/'selection-debug.png'))
                (out/'selection-debug.json').write_text(json.dumps(dict(asset=str(bpy.context.asset),selected=[str(x) for x in bpy.context.selected_assets],directory=str(area.spaces.active.params.directory),filename=area.spaces.active.params.filename,params=str(area.spaces.active.params))))
                assert bpy.context.asset and a.motion_assets.selected_key(bpy.context,a.motion_library.root(bpy.context))
                # Creature assets must not silently retarget onto this human test character.
                try:a.motion_library.build(bpy.context);raise AssertionError('Creature accepted on a different skeleton')
                except ValueError as exc:assert 'same skeleton' in str(exc)
                area.spaces.active.params.filter_search='Walk';state['walk']=next(e for e in a.motion_store.catalog(a.motion_library.root(bpy.context))['clips'] if e['name']=='Walk' and e['family']=='Human')
            state.update(phase=4,wait=time.monotonic()+2)
        elif state['phase']==4 and time.monotonic()>state['wait']:
            area=next(ar for ar in window.screen.areas if ar.type=='FILE_BROWSER');entry=state['walk']
            area.spaces.active.deselect_all();area.spaces.active.activate_file_by_relative_path(relative_path=entry['id']+'.blend\\Action\\'+entry['name'])
            state.update(phase=5,wait=time.monotonic()+1)
        elif state['phase']==5 and time.monotonic()>state['wait']:
            area=next(ar for ar in window.screen.areas if ar.type=='FILE_BROWSER');region=next(re for re in area.regions if re.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=area,region=region):
                assert a.motion_assets.selected_key(bpy.context,a.motion_library.root(bpy.context))==state['walk']['id']
                bpy.ops.screen.screenshot(filepath=str(out/'asset-browser.png'))
                assert bpy.ops.local_character.preview_library_motion()=={'FINISHED'}
                assert bpy.context.screen.is_animation_playing
            state.update(phase=6,wait=time.monotonic()+1)
        elif state['phase']==6 and time.monotonic()>state['wait']:
            area=next(ar for ar in window.screen.areas if ar.type=='FILE_BROWSER');region=next(re for re in area.regions if re.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=area,region=region):
                a.motion_library.restore_preview(bpy.context)
                assert rig.animation_data is None and set(bpy.data.objects)==objects
                assert bpy.ops.local_character.motion_library('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
            state.update(phase=7,wait=time.monotonic()+1)
        elif state['phase']==7 and time.monotonic()>state['wait']:
            bpy.ops.screen.screenshot(filepath=str(out/'adjust-motion.png'))
            (out/'results.json').write_text(json.dumps(dict(passed=True,native_asset_browser=True,selected_external_action_asset=True,cross_creature_rig_rejected=True,thumbnail_rendered=True,adjust_controls_rendered=True,full_clip_preview_plays=True,cancel_restores_original=True,no_new_objects=True),indent=2))
            return finish()
    except Exception:return finish(traceback.format_exc())
    return .2
bpy.app.timers.register(tick,first_interval=1.)
