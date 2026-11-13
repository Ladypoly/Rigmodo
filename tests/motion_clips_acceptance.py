import bpy,addon_utils,importlib,json,sys,tempfile
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character')
a=importlib.import_module('bl_ext.user_default.local_character');c=a.motion_clips
assert c.enum_items(None,None)==[]
rig=a.skeleton.create_armature(bpy.context);scene=bpy.context.scene;scene.render.fps=24
bone=rig.pose.bones['Root'];bone.keyframe_insert('location',frame=1);bone.location.x=.1;bone.keyframe_insert('location',frame=33)
first=rig.animation_data.action;first.name='Walk';first['lc_loop_period_frames']=32
first_slot=rig.animation_data.action_slot
objects=set(bpy.data.objects);original_data=rig.data.as_pointer()
assert any(ac==first and slot==first_slot for ac,slot in c.available(rig))
enum_before={i[0]:i[3] for i in c.enum_items(None,bpy.context)}
assert bpy.ops.local_character.new_motion_clip(name='Attack')=={'FINISHED'}
empty=rig.animation_data.action;empty_slot=rig.animation_data.action_slot
assert empty.name=='Attack' and empty.lc_clip_owner==rig and empty.use_fake_user and first.use_fake_user
assert not c.slot_curves(empty,empty_slot) and all(tuple(p.location)==(0,0,0) for p in rig.pose.bones)
assert bpy.ops.local_character.select_motion_clip(clip=c.identifier(first,first_slot))=={'FINISHED'}
assert scene.frame_preview_start==1 and scene.frame_preview_end==32 and rig.animation_data.action==first
assert any(ac==empty for ac,slot in c.available(rig))
other=bpy.data.objects.new('Other Rig',rig.data.copy());scene.collection.objects.link(other)
bpy.context.view_layer.update()
assert not any(ac==empty for ac,slot in c.available(other))
shared=other.animation_data_create();shared.action=first;shared.action_slot=first_slot
try:c.delete(bpy.context,rig,first);raise AssertionError('Shared Action was deleted')
except ValueError:pass
assert rig.animation_data.action==first and shared.action==first
shared.action=None
track=rig.animation_data.nla_tracks.new();track.strips.new('Protected NLA',1,first)
try:c.delete(bpy.context,rig,first);raise AssertionError('NLA Action was deleted')
except ValueError:pass
rig.animation_data.nla_tracks.remove(track)
# A different slot may animate foreign bones; only the matching slot is offered.
multi=bpy.data.actions.new('Multi-slot');multi.use_fake_user=True
for obj,bone_name in [(rig,'Root'),(other,'ForeignBone')]:
    if bone_name=='ForeignBone':other.data.bones['Root'].name=bone_name
    slot=multi.slots.new(id_type='OBJECT',name=obj.name);ad=obj.animation_data_create();ad.action=multi;ad.action_slot=slot
    curve=multi.fcurve_ensure_for_datablock(obj,obj.pose.bones[bone_name].path_from_id('location'),index=0)
    curve.keyframe_points.insert(1,0.);curve.keyframe_points.insert(10,.1)
matches=[slot for ac,slot in c.available(rig) if ac==multi];assert len(matches)==1
assert matches[0].identifier==multi.slots[0].identifier
slot=multi.slots.new(id_type='OBJECT',name='Second matching slot')
rig.animation_data.action_slot=slot
curve=multi.fcurve_ensure_for_datablock(rig,rig.pose.bones['Root'].path_from_id('location'),index=2)
curve.keyframe_points.insert(1,0.);curve.keyframe_points.insert(10,.1)
labels=[item[1] for item in c.enum_items(None,bpy.context) if item[0].startswith(str(multi.session_uid)+':')]
assert len(labels)==2 and len(set(labels))==2
other.animation_data.action=None
c.select(bpy.context,rig,first,first_slot)
# Stable enum values survive renaming/reordering other clips.
empty.name='ZZZ renamed';enum_after={i[0]:i[3] for i in c.enum_items(None,bpy.context)}
assert enum_before[c.identifier(first,first_slot)]==enum_after[c.identifier(first,first_slot)]
assert bpy.ops.local_character.new_motion_clip(name='Temporary')=={'FINISHED'}
temporary=rig.animation_data.action.name
assert bpy.ops.local_character.delete_motion_clip()=={'FINISHED'}
assert temporary not in bpy.data.actions and rig.animation_data.action is not None
assert set(bpy.data.objects)==objects|{other} and rig.data.as_pointer()==original_data
before=len(bpy.data.actions)
try:c.new(bpy.context,rig,'   ');raise AssertionError('Blank name was accepted')
except ValueError:pass
assert len(bpy.data.actions)==before
rig_name=rig.name;empty_name=empty.name
folder=Path(tempfile.mkdtemp(prefix='rigmodo-motion-clips-'))
bpy.ops.wm.save_as_mainfile(filepath=str(folder/'clip-library.blend'),copy=True)
bpy.ops.wm.open_mainfile(filepath=str(folder/'clip-library.blend'))
loaded_rig=bpy.data.objects[rig_name];loaded_empty=bpy.data.actions[empty_name]
assert loaded_empty.use_fake_user and loaded_empty.lc_clip_owner==loaded_rig
assert any(ac==loaded_empty for ac,slot in c.available(loaded_rig))
# Registration cleanup and re-enable must retain the saved owner reference.
a.unregister();a.register()
assert loaded_empty.lc_clip_owner==loaded_rig
result=dict(passed=True,existing_clips_discovered=True,select_and_loop_range=True,new_empty_clip=True,
    old_clips_retained=True,empty_clips_scoped_to_owner=True,shared_delete_protected=True,nla_delete_protected=True,
    compatible_slot_selected=True,enum_stable_on_reordering=True,delete_only_action=True,invalid_name_rejected=True,
    empty_clip_survives_save_reload=True,registration_cycle_passed=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(result,indent=2))
print('MOTION_CLIPS_PASS',json.dumps(result),flush=True)
