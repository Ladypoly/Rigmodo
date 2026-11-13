import bpy,addon_utils,importlib,json,sys
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');p=a.motion_playback;c=a.motion_clips
rig=a.skeleton.create_armature(bpy.context);scene=bpy.context.scene
root=rig.pose.bones['Root'];root.keyframe_insert('location',frame=1);root.keyframe_insert('location',frame=25)
action=rig.animation_data.action;action.name='Scorpion_Attack_Arcade';action['lc_source_fps']=24
assert not action.lc_clip_loop and not p.export_loop(action,True)
assert bpy.ops.local_character.preview_motion()=={'FINISHED'}
assert scene.frame_preview_end==25 and not scene.lc_settings.loop_action
action.lc_clip_loop=True;assert p.looping(action) and p.export_loop(action,False) and scene.lc_settings.loop_action
action.lc_clip_loop=False;assert not scene.lc_settings.loop_action
del action['lc_clip_loop'];action.name='Scorpion_Death_Arcade';assert not p.looping(action)
action['lc_loop_period_frames']=24;assert not p.looping(action)
assert bpy.ops.local_character.preview_motion()=={'FINISHED'} and scene.frame_preview_end==25
del action['lc_clip_loop'];action.name='Scorpion_Walk_Fast_Arcade'
assert p.looping(action)
assert bpy.ops.local_character.preview_motion()=={'FINISHED'} and scene.frame_preview_end==24
assert scene.lc_settings.loop_action and p.export_loop(action,False)
action.lc_clip_loop=False
assert bpy.ops.local_character.preview_motion()=={'FINISHED'} and scene.frame_preview_end==25
guide=bpy.data.actions.new('Generated clip')
for prompt,expected in [('An object attacks forward.',False),('An object dies.',False),('An object falls down and lies motionless.',False),('A person walks forward.',True)]:
    if 'lc_clip_loop' in guide:del guide['lc_clip_loop']
    p.stamp(guide,prompt);assert p.looping(guide)==expected,prompt
legacy=bpy.data.actions.new('Legacy authored motion')
assert p.export_loop(legacy,True) and not p.export_loop(legacy,False)
action.lc_clip_loop=True
assert a.animation.selected_action(rig,scene)['frame_end']==25
handlers=(list(bpy.app.handlers.frame_change_post).count(p.on_frame),list(bpy.app.handlers.load_post).count(p.reset))
assert handlers==(1,1)
result=dict(passed=True,attack_and_death_default_once=True,walk_default_loop=True,explicit_override=True,
    full_endpoint_for_one_shot=True,loop_duplicate_endpoint_excluded=True,per_clip_export_loop=True,
    legacy_export_fallback_preserved=True,generated_prompt_stamped=True,handlers_registered_once=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(result,indent=2))
print('ONE_SHOT_PASS',json.dumps(result),flush=True)
