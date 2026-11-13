import bpy,addon_utils,importlib,json,sys
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
rig=a.skeleton.create_armature(bpy.context);p=rig.pose.bones['Root'];p.keyframe_insert('location',frame=1);p.keyframe_insert('location',frame=33)
action=rig.animation_data.action;action['lc_loop_period_frames']=32
assert bpy.ops.local_character.preview_motion()=={'FINISHED'}
assert bpy.context.scene.frame_preview_start==1 and bpy.context.scene.frame_preview_end==32
assert a.animation.selected_action(rig,bpy.context.scene)['frame_end']==33
del action['lc_loop_period_frames'];bpy.ops.local_character.preview_motion();assert bpy.context.scene.frame_preview_end==33
action['lc_loop_period_frames']='invalid';bpy.ops.local_character.preview_motion();assert bpy.context.scene.frame_preview_end==33
result=dict(passed=True,authored_period_respected=True,export_duplicate_endpoint_retained=True,ordinary_actions_unchanged=True,invalid_metadata_ignored=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(result,indent=2));print('LOOP_PREVIEW_PASS',json.dumps(result),flush=True)
