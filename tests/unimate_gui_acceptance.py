"""Real modal cancellation and generation, in a separate Blender window."""
import bpy,importlib.util,sys,json,time,traceback
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];base=Path(args[0]);base.mkdir(parents=True,exist_ok=True)
source=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('unimate_gui_test',source/'__init__.py',submodule_search_locations=[str(source)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register()
bpy.context.preferences.addons.new().module=spec.name;bpy.context.preferences.view.show_splash=False
bpy.ops.wm.open_mainfile(filepath=args[1]);state={'phase':-1,'started':time.monotonic()}
def run():
    try:
        if time.monotonic()-state['started']>65:raise AssertionError('GUI test timed out')
        window=bpy.context.window or bpy.context.window_manager.windows[0]
        area=next(ar for ar in window.screen.areas if ar.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            scene=bpy.context.scene;s=scene.lc_settings
            if state['phase']==-1:
                rig=bpy.context.active_object
                assert rig and rig.type=='ARMATURE'
                for obj in scene.objects:obj.hide_set(obj!=rig and not (obj.type=='MESH' and obj.parent==rig))
                for obj in bpy.context.selected_objects:obj.select_set(False)
                rig.select_set(True);rig.lc_unimate_forward='X'
                meshes=a.motion_jobs.character_meshes(bpy.context,rig)
                s.rig_type='CREATURE';s.ui_step='MOTION';s.motion_prompt='An object walks forward.';s.unimate_frames=60
                a.configuration.preferences(bpy.context).unimate_provider=str(a.unimate.cache())
                area.spaces.active.show_region_ui=True;bpy.ops.view3d.view_selected(use_all_regions=False)
                state.update(rig=rig,meshes=meshes,before=a.skinning._digest(rig,meshes),action=a.unimate.source_signature(rig),counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes)),phase=0)
            elif state['phase']==0:
                next(r for r in area.regions if r.type=='UI').active_panel_category='Rigmodo'
                assert bpy.ops.local_character.generate_creature_motion()=={'RUNNING_MODAL'}
                assert a.processing_visuals.active(scene);state['phase']=1;state['wait']=time.monotonic()+.7
            elif state['phase']==1 and time.monotonic()>state['wait']:
                bpy.ops.screen.screenshot(filepath=str(base/'running.png'))
                assert bpy.ops.local_character.cancel_processing()=={'FINISHED'};state['phase']=2
            elif state['phase']==2 and not a.skinning._jobs and not a.processing_visuals._sessions:
                assert a.skinning._digest(state['rig'],state['meshes'])==state['before']
                assert state['counts']==(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes))
                assert not a.processing_visuals._handles and not bpy.app.timers.is_registered(a.processing_visuals.tick)
                assert 'Cancelled' in s.motion_status
                assert bpy.ops.local_character.generate_creature_motion()=={'RUNNING_MODAL'};state['phase']=3
            elif state['phase']==3 and not a.skinning._jobs and not a.processing_visuals._sessions:
                assert 'UniMate motion ready' in s.motion_status,s.motion_status
                assert a.skinning._digest(state['rig'],state['meshes'])==state['before']
                assert a.unimate.source_signature(state['rig'])==state['action']
                assert len(bpy.data.objects)==state['counts'][0]+2
                assert bpy.context.active_object.animation_data.action
                bpy.ops.view3d.view_selected(use_all_regions=False);scene.frame_set(24);state['phase']=4
            elif state['phase']==4:
                bpy.ops.screen.screenshot(filepath=str(base/'motion.png'))
                (base/'results.json').write_text(json.dumps(dict(passed=True,real_worker_cancelled=True,source_preserved=True,
                    no_scene_objects_added_on_cancel=True,processing_effects_cleaned_up=True,armature_only_selection=True,real_modal_generation=True),indent=2))
                bpy.ops.wm.quit_blender();return None
    except Exception:
        (base/'error.txt').write_text(traceback.format_exc());traceback.print_exc();a.skinning.cancel_all();bpy.ops.wm.quit_blender();return None
    return .1
bpy.app.timers.register(run,first_interval=1.)
