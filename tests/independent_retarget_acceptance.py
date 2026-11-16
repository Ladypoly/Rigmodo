import bpy,addon_utils,importlib,json,sys,tempfile
from pathlib import Path
import numpy as np
from mathutils import Quaternion
bpy.ops.wm.read_factory_settings(use_empty=True);addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context;s=ctx.scene.lc_settings
root=a.motion_library.root(ctx);humans=[e for e in a.motion_store.catalog(root)['clips'] if e['family']=='Human' and e['duration']>=.6];walk=next(e for e in humans if e['name'].casefold()=='walk');entries=[walk,next(e for e in humans if e['id']!=walk['id'])]
first=a.skeleton.create_armature(ctx,1.75,35);second=a.skeleton.create_armature(ctx,2.1,35);objects=set(bpy.data.objects);before={o:a.skinning._digest(o,[]) for o in (first,second)}
a.motion_sources.refresh(ctx,[e['id'] for e in entries]);state=ctx.window_manager.lc_motion_library;state.speed=1.5;state.mirror=True
for obj in ctx.selected_objects:obj.select_set(False)
first.select_set(True);second.select_set(True);ctx.view_layer.objects.active=first;s.retarget_selected_characters=True;s.motion_contacts=False;s.retarget_loop='ONCE'
assert bpy.ops.local_character.retarget_sources()=={'FINISHED'} and not json.loads(s.retarget_report)
made=[action for action in bpy.data.actions if action.lc_clip_owner in (first,second)]
assert len(made)==4 and not any(action.lc_clip_loop for action in made)
for rig in (first,second):
 assert before[rig]==a.skinning._digest(rig,[])
 assert len([action for action in made if action.lc_clip_owner==rig])==2
 assert all(action.lc_clip_owner in (None,rig) for action,slot in a.motion_clips.available(rig))
a.motion_sources.refresh(ctx);state.query='Human';bpy.ops.local_character.select_source_motions(mode='ALL');assert all(item.source_selected==('human' in (item.name+' '+item.family+' '+item.source).casefold()) for item in state.entries)
state.query='no matching motion';bpy.ops.local_character.select_source_motions(mode='NONE');assert not a.motion_sources.chosen(ctx)
state.query='';a.motion_sources.refresh(ctx,[entries[0]['id']]);state.speed=2.;state.mirror=False;state.trim_start=.1;state.trim_end=.6
assert bpy.ops.local_character.retarget_sources()=={'FINISHED'} and not json.loads(s.retarget_report)
for rig in (first,second):
 action=rig.animation_data.action;assert abs((action.frame_end-action.frame_start)/(ctx.scene.render.fps/ctx.scene.render.fps_base)-.25)<1e-4
frame=ctx.scene.frame_current;loop=s.loop_action;old=a.motion_sources.motion_retarget
def fail(*args):raise ValueError('Injected preview error')
a.motion_sources.motion_retarget=fail
try:bpy.ops.local_character.preview_source_motion()
except RuntimeError:pass
finally:a.motion_sources.motion_retarget=old
assert set(bpy.data.objects)==objects and a.motion_sources._preview is None and ctx.scene.frame_current==frame and s.loop_action==loop
ctx.view_layer.objects.active=first
for obj in ctx.selected_objects:obj.select_set(False)
first.select_set(True);guide=a.motion_clips.new(ctx,first,'Conflicting loop guides');ctx.scene.render.fps=24;ctx.scene.frame_start=100
for f,angle in [(100,0),(124,.7)]:
 for bone in first.pose.bones:
  bone.rotation_mode='QUATERNION';bone.rotation_quaternion=Quaternion((0,1,0),angle if bone.name=='LeftArm' else 0)
  for prop in ('location','rotation_quaternion','scale'):bone.keyframe_insert(prop,frame=f)
folder=a.motion_jobs.prepare(ctx,first,'Loop validation',31,parent=Path(tempfile.mkdtemp()),keyframes=True,start_frame=100);request=json.loads((folder/'request.json').read_text())
try:a.animation_transfer.validate_key_loop(folder,request,False);raise AssertionError('Conflicting loop anchors accepted')
except ValueError as exc:assert 'conflict' in str(exc)
report=dict(passed=True,two_sources_two_targets=True,one_shots_preserved=True,speed_trim_mirror=True,per_character_actions=True,rest_unchanged=True,preview_error_cleans_temporary_skeleton=True,conflicting_loop_guides_rejected_before_generation=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2),encoding='utf-8');print('INDEPENDENT_RETARGET_PASS',report)
