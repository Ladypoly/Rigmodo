import bpy,addon_utils,importlib,json,sys,math
import numpy as np
from pathlib import Path
from mathutils import Matrix
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
target=a.skeleton.create_armature(bpy.context,height=1.4,arm_angle=35);s=bpy.context.scene.lc_settings
a.character_context.pin(bpy.context,target,[]);s.motion_contacts=True;s.create_loop=True;s.motion_in_place=True
catalog=a.motion_store.catalog(Path('R:/AI/MotionLibrary/Rigmodo'));entry=next(e for e in catalog['clips'] if e['family']=='Human' and e['name']=='Walk')
data=a.motion_store.read(Path('R:/AI/MotionLibrary/Rigmodo'),entry['id']);objects=set(bpy.data.objects);rest={b.name:b.matrix_local.copy() for b in target.data.bones}
action=a.animation_transfer.finish(bpy.context,target,data,'Pipeline walk')
assert action.lc_clip_loop and 'lc_loop_period_frames' in action
assert action.lc_contact_source and json.loads(action['lc_contact_report'])['periodic_three_cycle_solve']
assert set(bpy.data.objects)==objects and all(b.matrix_local==rest[b.name] for b in target.data.bones)
captured=a.motion_store.capture(bpy.context,target,action,target.animation_data.action_slot)
root=list(captured['names']).index('Root');delta=Matrix(captured['poses'][-1,root].tolist())@Matrix(captured['poses'][0,root].tolist()).inverted()
seam=max((Matrix(last.tolist()).translation-(delta@Matrix(first.tolist())).translation).length for first,last in zip(captured['poses'][0],captured['poses'][-1]))
assert seam<.015,seam
# Retarget a separate scene Action through the new Create workflow while an unrelated object is active.
source=a.skeleton.create_armature(bpy.context);bone=source.pose.bones['Hips'];bone.keyframe_insert('rotation_quaternion',frame=1);bone.rotation_quaternion.rotate(__import__('mathutils').Quaternion((0,0,1),.2));bone.keyframe_insert('rotation_quaternion',frame=31)
original=source.animation_data.action;s.source_rig=source;s.source_action=original;s.create_loop=False;s.motion_contacts=False;s.animation_source='ANIMATION'
bpy.ops.mesh.primitive_cube_add()
assert bpy.ops.local_character.create_animation()=={'FINISHED'}
assert target.animation_data.action!=action and source.animation_data.action==original and not target.animation_data.action.lc_clip_loop
report=dict(passed=True,retarget_ground_loop_pipeline=True,periodic_contacts=True,loop_position_seam_m=seam,source_action_create_workflow=True,pinned_target_used=True,source_rig_and_action_preserved=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('ANIMATION_PIPELINE_PASS',report)
