import bpy,addon_utils,importlib,sys,json
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
rig=a.skeleton.create_armature(bpy.context);scene=bpy.context.scene
for p in rig.pose.bones:p.rotation_mode='XYZ'
hips=rig.pose.bones['Hips'];hips.rotation_mode='ZXY';hips.rotation_euler=(.1,.2,.3);hips.keyframe_insert('rotation_euler',frame=1)
hips.rotation_euler=(.3,-.2,.6);hips.keyframe_insert('rotation_euler',frame=19)
original=rig.animation_data.action;original.name='Existing ZXY animation';slot=rig.animation_data.action_slot
scene.frame_set(7);bpy.context.view_layer.update();before=hips.matrix.copy();modes={p.name:p.rotation_mode for p in rig.pose.bones}
a.motion_library.refresh(bpy.context);state=bpy.context.window_manager.lc_motion_library;state.target=rig
state.index=next(i for i,e in enumerate(state.entries) if e.family=='Human' and e.name=='Walk')
a.motion_library.build(bpy.context,True);assert hips.rotation_mode=='QUATERNION'
a.motion_library.restore_preview(bpy.context)
assert rig.animation_data.action==original and scene.frame_current==7
assert {p.name:p.rotation_mode for p in rig.pose.bones}==modes
assert max(abs(hips.matrix[i][j]-before[i][j]) for i in range(4) for j in range(4))<1e-6
applied=a.motion_library.build(bpy.context)
assert hips.rotation_mode=='QUATERNION'
a.motion_clips.select(bpy.context,rig,original,slot);scene.frame_set(7);bpy.context.view_layer.update()
assert hips.rotation_mode=='ZXY' and max(abs(hips.matrix[i][j]-before[i][j]) for i in range(4) for j in range(4))<1e-6
a.motion_clips.select(bpy.context,rig,applied,applied.slots[0]);assert hips.rotation_mode=='QUATERNION'
original['lc_rotation_modes']='{"Hips": []}'
a.animation.attach_action(rig,{'action':original,'slot':slot})
report=dict(passed=True,malformed_mode_metadata_ignored=True,euler_preview_restored=True,original_rotation_order_retained=True,clip_switch_restores_rotation_modes=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('ROTATION_MODE_PASS',json.dumps(report))
