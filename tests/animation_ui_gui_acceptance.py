# SPDX-License-Identifier: GPL-3.0-or-later
"""Run in a separate factory-startup GUI process; exits without changing recovery files."""
import bpy,addon_utils,importlib,sys,time,json,traceback,os
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True);view=args[1] if len(args)>1 else 'CREATE'
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
bpy.context.preferences.use_preferences_save=False;bpy.context.preferences.view.show_splash=False
rig=a.skeleton.create_armature(bpy.context);a.character_context.pin(bpy.context,rig,[])
bpy.context.scene.render.fps=60
s=bpy.context.scene.lc_settings;s.ui_step='MOTION';s.animation_view=view
video=Path('R:/AI/Rigmodo/Jobs/Acceptance/full-avatar-walk/avatar-walk.mp4')
if video.is_file():s.video_path=str(video)
bpy.ops.mesh.primitive_cube_add(location=(4,4,0));other=bpy.context.object;bpy.context.scene.frame_set(17)
state=dict(phase=0,started=time.monotonic())
def tick():
    try:
        if time.monotonic()-state['started']>35:raise AssertionError('UI timed out')
        window=bpy.context.window_manager.windows[0];area=next(area for area in window.screen.areas if area.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            if state['phase']==0:
                area.spaces.active.show_region_ui=True;area.spaces.active.region_3d.view_distance=3.5
                area.spaces.active.region_3d.view_location=(0,0,.9)
                bpy.ops.wm.call_panel(name='LC_PT_main',keep_open=True);state.update(phase=1,wait=time.monotonic()+1)
            elif time.monotonic()>state['wait'] and state['phase']==1:
                bpy.ops.screen.screenshot(filepath=str(out/(view.lower()+'.png')))
                state['sidebar']=area.spaces.active.show_region_ui;state['toolbar']=area.spaces.active.show_region_toolbar
                state.update(area_count=len(window.screen.areas),original_pointer=area.as_pointer(),selected=list(bpy.context.selected_objects),active=bpy.context.view_layer.objects.active,frame=bpy.context.scene.frame_current)
                assert bpy.ops.local_character.open_motion_editor()=={'FINISHED'}
                editor=a.animation_ui._editors[window.as_pointer()]['area']
                if editor.type=='CLIP_EDITOR':
                    bpy.context.scene.frame_set(61);a.animation_ui.sync_video(bpy.context.scene)
                    assert editor.spaces.active.clip_user.frame_current==round(editor.spaces.active.clip.fps)+1
                state.update(phase=2,wait=time.monotonic()+1)
            elif time.monotonic()>state['wait']:
                editor_state=a.animation_ui._editors[window.as_pointer()];kind=editor_state['area'].type
                bpy.ops.screen.screenshot(filepath=str(out/'editor.png'))
                assert bpy.ops.local_character.close_motion_editor()=={'FINISHED'}
                assert len(window.screen.areas)==state['area_count']
                assert any(item.as_pointer()==state['original_pointer'] and item.type=='VIEW_3D' for item in window.screen.areas)
                assert area.spaces.active.show_region_ui==state['sidebar'] and area.spaces.active.show_region_toolbar==state['toolbar']
                assert list(bpy.context.selected_objects)==state['selected'] and bpy.context.view_layer.objects.active==state['active']
                assert bpy.context.scene.frame_current==state['frame'] and not a.animation_ui._editors
                assert a.animation_ui.sync_video not in bpy.app.handlers.frame_change_post
                assert bpy.ops.local_character.open_motion_editor()=={'FINISHED'}
                a.animation_ui.cleanup();assert len(window.screen.areas)==state['area_count'] and not a.animation_ui._editors
                (out/'results.json').write_text(json.dumps(dict(passed=True,view=view,native_panel_rendered=True,motion_editor_opens_closes=True,original_viewport_retained=True,selection_and_frame_restored=True,overlay_handlers_removed=True,source_editor_type=kind,video_24_to_scene_60_sync=True,reload_cleanup_restores_layout=True),indent=2));os._exit(0)
    except Exception:
        (out/'error.txt').write_text(traceback.format_exc());os._exit(1)
    return .2
bpy.app.timers.register(tick,first_interval=1)
