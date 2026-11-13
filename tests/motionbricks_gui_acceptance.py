"""Real MotionBricks panel, cancellation, source scope and successful modal application."""
import bpy,importlib.util,json,sys,time,traceback
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True);source=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('rigmodo_mb_gui',source/'__init__.py',submodule_search_locations=[str(source)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register();bpy.context.preferences.addons.new().module=spec.name
bpy.context.preferences.view.show_splash=False;bpy.ops.wm.open_mainfile(filepath=args[1]);state={'phase':-1,'started':time.monotonic()}
def tick():
 try:
  if time.monotonic()-state['started']>70:raise AssertionError('GUI timeout')
  window=bpy.context.window or bpy.context.window_manager.windows[0];area=next(ar for ar in window.screen.areas if ar.type=='VIEW_3D');region=next(re for re in area.regions if re.type=='WINDOW')
  with bpy.context.temp_override(window=window,area=area,region=region):
   scene=bpy.context.scene;s=scene.lc_settings
   if state['phase']==-1:
    rig=next(o for o in scene.objects if o.type=='ARMATURE' and o.animation_data and o.animation_data.action and o.animation_data.action.name.startswith('Artist pose keys'))
    meshes=[o for o in scene.objects if o.type=='MESH' and o.parent==rig]
    for o in scene.objects:o.hide_set(o not in [rig,*meshes])
    for o in bpy.context.selected_objects:o.select_set(False)
    rig.select_set(True);bpy.context.view_layer.objects.active=rig
    s.rig_type='HUMANOID';s.ui_step='MOTION';s.motion_engine='MOTIONBRICKS';s.motion_in_place=False
    area.spaces.active.show_region_ui=True;bpy.ops.view3d.view_selected(use_all_regions=False)
    state.update(rig=rig,meshes=meshes,digest=a.skinning._digest(rig,meshes),action=a.unimate.source_signature(rig),count=len(bpy.data.objects),phase=0)
   elif state['phase']==0:
    next(re for re in area.regions if re.type=='UI').active_panel_category='Rigmodo'
    assert bpy.ops.local_character.generate_motion()=={'RUNNING_MODAL'};assert a.processing_visuals.active(scene)
    state.update(phase=1,wait=time.monotonic()+.5)
   elif state['phase']==1 and time.monotonic()>state['wait']:
    bpy.ops.screen.screenshot(filepath=str(out/'running.png'));bpy.ops.local_character.cancel_processing();state['phase']=2
   elif state['phase']==2 and not a.skinning._jobs and not a.processing_visuals._sessions:
    assert len(bpy.data.objects)==state['count'] and a.skinning._digest(state['rig'],state['meshes'])==state['digest']
    assert not a.processing_visuals._handles
    assert bpy.ops.local_character.generate_motion()=={'RUNNING_MODAL'};state['phase']=3
   elif state['phase']==3 and not a.skinning._jobs and not a.processing_visuals._sessions:
    rig=bpy.context.active_object;assert rig.get('lc_motion_provider')=='motionbricks_soma30',s.motion_status
    assert a.unimate.source_signature(state['rig'])==state['action'] and a.skinning._digest(state['rig'],state['meshes'])==state['digest']
    assert not a.processing_visuals._handles and not bpy.app.timers.is_registered(a.processing_visuals.tick)
    bpy.ops.view3d.view_selected(use_all_regions=False);scene.frame_set(25);state['phase']=4
   elif state['phase']==4:
    bpy.ops.screen.screenshot(filepath=str(out/'motion.png'))
    report=dict(passed=True,real_modal_motionbricks=True,real_worker_cancelled=True,no_objects_added_on_cancel=True,source_preserved=True,armature_only_selection=True,effects_cleaned_up=True,real_avatar=True)
    (out/'results.json').write_text(json.dumps(report,indent=2));bpy.ops.wm.quit_blender();return None
 except Exception:
  (out/'error.txt').write_text(traceback.format_exc());traceback.print_exc();a.skinning.cancel_all();bpy.ops.wm.quit_blender();return None
 return .1
bpy.app.timers.register(tick,first_interval=1.)
