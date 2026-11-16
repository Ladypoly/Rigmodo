"""Render every named generator in a native sidebar in an isolated GUI process."""
import bpy,addon_utils,importlib,sys,time,json,traceback,os
from pathlib import Path
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
bpy.context.preferences.use_preferences_save=False;bpy.context.preferences.view.show_splash=False
for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
s=bpy.context.scene.lc_settings;s.ui_step='MOTION';s.animation_view='CREATE';a.motion_sources.refresh(bpy.context)
views=[('CREATE','KIMODO'),('CREATE','MOTIONBRICKS'),('CREATE','VIDEO'),('CREATE','UNIMATE'),('EDIT','VIDEO'),('BROWSE','VIDEO')];state=dict(index=0,wait=0,started=time.monotonic(),screens=[])
def tick():
 try:
  if time.monotonic()-state['started']>60:raise AssertionError('Sidebar GUI timed out')
  window=bpy.context.window_manager.windows[0];area=next(a for a in window.screen.areas if a.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW');ui_region=next(r for r in area.regions if r.type=='UI')
  if not state.get('shown'):
   area.spaces.active.show_region_ui=True;state['shown']=True;return .5
  if time.monotonic()<state['wait']:return .2
  with bpy.context.temp_override(window=window,area=area,region=region):
   if state.get('capture'):
    label=state.pop('capture');bpy.ops.screen.screenshot(filepath=str(out/(label+'.png')));state['screens'].append(label)
   if state['index']<len(views):
    view,system=views[state['index']];s.animation_view=view;s.motion_system=system;area.spaces.active.show_region_ui=True;ui_region.active_panel_category='Rigmodo';area.tag_redraw()
    state.update(index=state['index']+1,capture=view.lower()+'-'+system.lower(),wait=time.monotonic()+.8)
   else:
    assert not bpy.context.scene.objects and not hasattr(a.animation_ui,'_editors') and not hasattr(bpy.types,'LC_OT_motion_editor')
    assert ui_region.active_panel_category=='Rigmodo'
    # Validate RNA/operator references even inside collapsed sections.
    class Layout:
     enabled=True;scale_y=1.;use_property_split=False
     def row(self,**kw):return self
     def column(self,**kw):return self
     def grid_flow(self,**kw):return self
     def box(self):return self
     def panel(self,*args,**kw):return self,self
     def label(self,**kw):pass
     def separator(self,**kw):pass
     def menu(self,*args,**kw):pass
     def template_list(self,*args,**kw):pass
     def prop(self,data,key,**kw):assert key in data.bl_rna.properties,key
     def prop_search(self,data,key,target,collection,**kw):assert key in data.bl_rna.properties and hasattr(target,collection)
     def operator(self,name,**kw):getattr(getattr(bpy.ops,name.split('.')[0]),name.split('.')[1]).get_rna_type();return type('Props',(),{})()
    for view,system in views:s.animation_view=view;s.motion_system=system;a.ui.draw(Layout(),bpy.context)
    rig=a.skeleton.create_armature(bpy.context);s.pose_source_rig=rig;a.character_context.pin(bpy.context,rig,[])
    for view,system in views:
     s.animation_view=view;s.motion_system=system;s.motion_use_keyframes=True;a.ui.draw(Layout(),bpy.context)
    bpy.ops.object.mode_set(mode='POSE');s.animation_view='CREATE';s.motion_system='MOTIONBRICKS';a.ui.draw(Layout(),bpy.context);bpy.ops.object.mode_set(mode='OBJECT')
    for step in ('RIG','SKIN'):s.ui_step=step;a.ui.draw(Layout(),bpy.context)
    report=dict(passed=True,native_sidebar=True,named_systems=['Kimodo','MotionBricks','Video to Motion','UniMate'],no_avatar_required_for_panel=True,all_stage_draws=True,advanced_rna_references=True,no_custom_editor=True,screens=state['screens'])
    (out/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8');os._exit(0)
 except Exception:
  (out/'error.txt').write_text(traceback.format_exc(),encoding='utf-8');os._exit(1)
 return .2
bpy.app.timers.register(tick,first_interval=1)
