import bpy,importlib.util,sys,json,time,traceback
from pathlib import Path
base=Path(sys.argv[sys.argv.index('--')+1]);source=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('creature_gui_test',source/'__init__.py',submodule_search_locations=[str(source)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register()
bpy.context.preferences.addons.new().module=spec.name
bpy.context.preferences.view.show_splash=False
bpy.ops.wm.open_mainfile(filepath=str(base/'acceptance-final/creature-review.blend'))
state={'phase':-1,'started':time.monotonic()}
def run():
    try:
        if time.monotonic()-state['started']>30:raise AssertionError('GUI cancel test timed out')
        window=bpy.context.window or bpy.context.window_manager.windows[0]
        area=next(ar for ar in window.screen.areas if ar.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            scene=bpy.context.scene
            if state['phase']==-1:
                rig=next(o for o in scene.objects if a.creatures.is_creature(o))
                meshes=[o for o in scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
                a.workflow.select(bpy.context,rig,meshes)
                scene.lc_settings.rig_type='CREATURE';scene.lc_settings.ui_step='RIG'
                a.configuration.preferences(bpy.context).creature_provider=str(a.creatures.cache())
                area.spaces.active.show_region_ui=True
                bpy.ops.view3d.view_selected(use_all_regions=False)
                state.update(rig=rig,meshes=meshes,before=a.skinning._digest(rig,meshes),counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes)),phase=0)
            elif state['phase']==0:
                assert bpy.ops.local_character.generate_creature_rig()=={'RUNNING_MODAL'}
                assert a.processing_visuals.active(scene);state['phase']=1;state['wait']=time.monotonic()+.5
            elif state['phase']==1 and time.monotonic()>state['wait']:
                bpy.ops.screen.screenshot(filepath=str(base/'creature-gui-running.png'))
                assert bpy.ops.local_character.cancel_processing()=={'FINISHED'};state['phase']=2
            elif state['phase']==2 and not a.skinning._jobs:
                assert a.skinning._digest(state['rig'],state['meshes'])==state['before']
                assert state['counts']==(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes))
                assert not a.processing_visuals._sessions and not a.processing_visuals._handles
                assert not bpy.app.timers.is_registered(a.processing_visuals.tick)
                assert 'Cancelled' in scene.lc_settings.creature_status
                (base/'gui-results.json').write_text(json.dumps(dict(passed=True,version=a.exporter.VERSION,real_creature_operator=True,real_worker_cancelled=True,source_preserved=True,no_scene_objects_added_on_cancel=True,processing_effects_cleaned_up=True),indent=2))
                bpy.ops.wm.quit_blender();return None
    except Exception:
        (base/'gui-error.txt').write_text(traceback.format_exc());traceback.print_exc();a.skinning.cancel_all();bpy.ops.wm.quit_blender();return None
    return .1
bpy.app.timers.register(run,first_interval=1.)
