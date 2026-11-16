# SPDX-License-Identifier: GPL-3.0-or-later
"""Task-based animation UI using native Blender editors."""
import bpy
from bpy.types import Operator,Menu
from . import motion_jobs,motion_clips,motion_playback,skinning,configuration,ui,character_context


def duration_changed(self,context):
    self.motion_frames=min(900,round(self.motion_duration*30)+1);self.unimate_frames=min(60,max(15,self.motion_frames))


def creature_character(context,rig):
    from . import creatures,rig_mapping
    if creatures.is_creature(rig):return True
    try:
        if rig and set(rig_mapping.CORE)<=set(rig_mapping.names(rig)):return False
    except ValueError:return False
    return bool(rig) and context.scene.lc_settings.rig_type=='CREATURE'


def current(layout,context,rig):
    if not rig:return
    action=rig.animation_data.action if rig.animation_data else None
    box=layout.box();row=box.row(align=True);row.label(text='Animation',icon='ACTION');row.menu('LC_MT_animation_actions',text='',icon='DOWNARROW_HLT')
    row=box.row(align=True);row.operator('local_character.select_motion_clip',text='',icon='VIEWZOOM')
    if action:
        row.prop(action,'name',text='');row.operator('local_character.preview_motion',text='',icon='PLAY')
    else:row.label(text='No animation yet')


def draw(layout,context,rig,creature=False):
    s=context.scene.lc_settings
    layout.row(align=True).prop(s,'animation_view',expand=True)
    if s.animation_view=='BROWSE':
        layout.label(text='Reusable motion assets',icon='ASSET_MANAGER')
        layout.operator('local_character.open_motion_assets',text='Open Motion Library',icon='ASSET_MANAGER')
        row=layout.row(align=True);row.operator('local_character.import_library_motions',text='Import Files');row.operator('local_character.import_motion_folder',text='Import Folder')
        layout.operator('local_character.save_library_motion',text='Save Current Animation',icon='ADD')
        return
    if s.animation_view=='EDIT':
        current(layout,context,rig)
        row=layout.row();row.enabled=bool(rig);row.operator('local_character.open_motion_editor',text='Open Motion Editor',icon='WINDOW')
        row=layout.row(align=True);row.enabled=bool(rig)
        row.operator('local_character.test_pose',text='Edit Pose',icon='POSE_HLT')
        if rig and rig.animation_data and rig.animation_data.action:
            report=__import__('json').loads(rig.animation_data.action.get('lc_loop_report','{}'))
            if report and (report.get('max_position_error_m',0)>.005 or report.get('max_linear_velocity_error_m_s',0)>.25):ui.message(layout,'Inspect the loop seam before export.',icon='INFO')
        if hasattr(bpy.types.Scene,'lc_settings'):
            body=ui.details(layout,'lc_animation_cleanup','Motion cleanup')
            if body:
                body.prop(s,'motion_loop_blend')
                body.operator('local_character.make_animation_loop',text='Make Loop Copy')
                if hasattr(s,'ground_height'):
                    body.prop(s,'ground_height');body.operator('local_character.ground_motion',text='Correct Foot Contacts')
        if rig and not creature:
            body=ui.details(layout,'lc_motion_mapping','Bone mapping')
            if body:
                body.operator('local_character.detect_motion_mapping');body.operator('local_character.accept_motion_mapping')
                proposal=__import__('json').loads(rig.get('lc_role_suggestions','{}'))
                if proposal:
                    review=body.column(align=True)
                    for role,bone in proposal.items():review.label(text=role+' → '+bone)
                body.prop(s,'mapping_role');body.prop_search(s,'mapping_bone',rig.data,'bones');body.operator('local_character.assign_motion_role')
                from . import rig_mapping
                try:
                    roles=rig_mapping.names(rig);missing=set(rig_mapping.CORE)-set(roles)
                    ui.message(body,'Missing: '+', '.join(sorted(missing)) if missing else 'Core humanoid roles mapped',icon='INFO')
                except ValueError as exc:ui.message(body,str(exc),icon='ERROR')
            body=ui.details(layout,'lc_contact_edit','Contact correction')
            if body:
                action=rig.animation_data.action if rig.animation_data else None
                if action:
                    report=__import__('json').loads(action.get('lc_contact_report','{}'))
                    for e in report.get('intervals',[])[:16]:body.label(text=f"{e['side']} · {e['start']:.2f}–{e['end']:.2f}s")
                    if report.get('unreachable_frames'):ui.message(body,'Some targets exceed leg reach. Review this clip.',icon='ERROR')
                body.prop(s,'contact_side');body.prop(s,'contact_mode')
                row=body.row(align=True);row.prop(s,'contact_start');row.prop(s,'contact_end')
                body.operator('local_character.mark_contact_interval')
                body.operator('local_character.clear_contact_intervals',text='Reset Contact Overrides')
                row=body.row(align=True)
                row.operator('local_character.set_sole_marker',text='Heel at Cursor').point='HEEL'
                row.operator('local_character.set_sole_marker',text='Forefoot at Cursor').point='BALL'
        if not creature:
            from . import image_pose
            body=ui.details(layout,'lc_animation_image','Pose from image')
            if body:image_pose.draw(body,context)
        return
    layout.label(text='Create from');layout.prop(s,'animation_source',text='')
    if s.animation_source=='TEXT':
        if not creature:layout.prop(s,'text_method',text='')
        layout.label(text='Motion');layout.prop(s,'motion_prompt',text='')
        if s.text_method=='COMFY' and not creature:
            layout.prop(s,'video_reference',text='Reference image')
            layout.operator('local_character.render_character_reference',text='Use Character Image',icon='RENDER_STILL')
        else:layout.prop(s,'motion_use_keyframes',text='Use timeline poses') if not creature else None
        layout.prop(s,'motion_duration',text='Length (seconds)')
        if s.text_method=='COMFY' and not creature and not configuration.settings(context).comfy_workflow:
            from .comfy_video import h3_frames
            frames=h3_frames(s.motion_duration);ui.message(layout,f'H3 profile: {frames} frames · {frames/24:.2f} seconds')
        if creature:ui.message(layout,'Creature generation supports up to 2 seconds per clip.')
    elif s.animation_source=='POSES':
        ui.message(layout,'Insert ordinary pose keys on the character. The keys define the transition timing.')
        if creature:ui.message(layout,'Pose transitions currently support humanoids.',icon='INFO')
        layout.operator('local_character.test_pose',text='Set Pose Keys',icon='POSE_HLT')
    elif s.animation_source=='VIDEO':
        layout.prop(s,'video_path',text='Video');layout.prop(s,'video_start',text='Start (seconds)');layout.prop(s,'motion_duration',text='Length (seconds)')
    else:
        layout.prop(s,'source_rig',text='Source rig');layout.prop(s,'source_action',text='Animation')
        layout.prop(s,'animation_file',text='Or import file')
    row=layout.row(align=True);row.prop(s,'create_loop',text='Loop');row.prop(s,'motion_in_place',text='In place')
    row=layout.row();row.scale_y=1.45;row.enabled=bool(rig) and not skinning._jobs and not (creature and s.animation_source in {'VIDEO','POSES'})
    row.operator('local_character.create_animation',text='Create Animation',icon='ACTION')
    if not rig:ui.message(layout,'Choose a character armature first.',icon='INFO')
    if not skinning._jobs:
        ui.message(layout,s.motion_status)
        if s.video_job:
            try:
                from pathlib import Path
                status=__import__('json').loads((Path(s.video_job)/'status.json').read_text())
                if status.get('status')=='failed':layout.operator('local_character.retry_video_motion',text='Retry Last Video Job',icon='FILE_REFRESH')
            except (OSError,ValueError):pass
    body=ui.details(layout,'lc_create_options','Advanced')
    if body:
        if s.animation_source=='VIDEO' and s.create_loop:body.prop(s,'video_cycle')
        body.prop(s,'motion_contacts',text='Automatic foot contacts')
        if hasattr(s,'ground_height'):body.prop(s,'ground_height')
        if s.animation_source=='TEXT' and s.text_method=='DIRECT' and not creature:
            body.prop(s,'motion_heading');body.prop(s,'motion_hand_curl')
            body.operator('local_character.test_pose',text='Pose Character')
        if creature and rig:
            body.prop(rig,'lc_unimate_forward');body.operator('local_character.detect_creature_joints',text='Detect Facing & Joints')
    if rig and rig.animation_data and rig.animation_data.action:
        layout.separator();current(layout,context,rig)


class LC_OT_create_animation(Operator):
    bl_idname='local_character.create_animation';bl_label='Create Animation';bl_options={'REGISTER'}
    def execute(self,context):
        s=context.scene.lc_settings
        try:
            rig=motion_jobs.selected_rig(context)
            from . import creatures
            creature=creature_character(context,rig)
            if creature and s.animation_source=='TEXT':
                s.ui_motion_pipeline=True
                try:return bpy.ops.local_character.generate_creature_motion()
                finally:s.ui_motion_pipeline=False
            if s.animation_source=='ANIMATION':
                return bpy.ops.local_character.retarget_animation()
            if s.animation_source=='VIDEO' or s.animation_source=='TEXT' and s.text_method=='COMFY':
                return bpy.ops.local_character.video_motion()
            rig=motion_jobs.selected_rig(context)
            from . import creatures
            if creature_character(context,rig):return bpy.ops.local_character.generate_creature_motion()
            duration_changed(s,context)
            s.motion_engine='MOTIONBRICKS' if s.animation_source=='POSES' else 'KIMODO'
            s.ui_motion_pipeline=True
            try:return bpy.ops.local_character.generate_motion()
            finally:s.ui_motion_pipeline=False
        except (ValueError,RuntimeError,AttributeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_MT_animation_actions(Menu):
    bl_label='Animation'
    def draw(self,context):
        layout=self.layout
        layout.operator('local_character.new_motion_clip',text='New Empty Animation',icon='ADD')
        layout.operator('local_character.save_library_motion',text='Save to Library',icon='ASSET_MANAGER')
        layout.separator();layout.operator('local_character.delete_motion_clip',text='Delete Animation',icon='TRASH')


_editors={}

class LC_OT_motion_editor(Operator):
    bl_idname='local_character.open_motion_editor';bl_label='Open Motion Editor'
    def invoke(self,context,event):
        result=self.execute(context)
        if result=={'FINISHED'}:
            self._window=context.window.as_pointer();context.window_manager.modal_handler_add(self);return {'RUNNING_MODAL'}
        return result
    def modal(self,context,event):
        if self._window not in _editors:return {'FINISHED'}
        if event.type=='ESC' and event.value=='PRESS':
            bpy.ops.local_character.close_motion_editor();return {'FINISHED'}
        return {'PASS_THROUGH'}
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);window=context.window
            if window.as_pointer() in _editors:return {'FINISHED'}
            if not context.area or context.area.type!='VIEW_3D':raise ValueError('Open the Motion Editor from a 3D View')
            if context.mode not in {'OBJECT','POSE'} or context.mode=='POSE' and context.active_object!=rig:raise ValueError('Finish the current edit before opening the Motion Editor')
            areas=list(context.screen.areas);before=set(areas)
            snapshot=dict(window=window,workspace=context.workspace,rig=rig,scene=context.scene,handler=None,original=context.area,selected=list(context.selected_objects),active=context.view_layer.objects.active,mode=context.mode,frame=context.scene.frame_current,subframe=context.scene.frame_subframe,area=None)
            space=context.area.spaces.active;view=space.region_3d
            snapshot['view_state']=dict(show_region_ui=space.show_region_ui,show_region_toolbar=space.show_region_toolbar,location=view.view_location.copy(),rotation=view.view_rotation.copy(),distance=view.view_distance,perspective=view.view_perspective)
            bpy.ops.screen.area_split(direction='VERTICAL',factor=.58)
            area=next(a for a in context.screen.areas if a not in before);snapshot['area']=area
            _editors[window.as_pointer()]=snapshot
            source=snapshot['original'];source.spaces.active.show_region_ui=False;source.spaces.active.show_region_toolbar=False
            if context.mode=='OBJECT':
                for obj in context.selected_objects:obj.select_set(False)
                rig.select_set(True);context.view_layer.objects.active=rig
            with context.temp_override(area=source,region=next(r for r in source.regions if r.type=='WINDOW')):bpy.ops.view3d.view_selected()
            area.type='DOPESHEET_EDITOR';area.ui_type='DOPESHEET'
            action=rig.animation_data.action if rig.animation_data else None
            video=action.get('lc_capture_video',context.scene.lc_settings.video_path) if action else context.scene.lc_settings.video_path
            snapshot['video_start']=action.get('lc_capture_offset_seconds',context.scene.lc_settings.video_start) if action else context.scene.lc_settings.video_start
            snapshot['action_start']=action.frame_start if action else context.scene.frame_start
            if video and __import__('pathlib').Path(bpy.path.abspath(video)).is_file():
                area.type='CLIP_EDITOR';before_clips=set(bpy.data.movieclips);clip=bpy.data.movieclips.load(bpy.path.abspath(video),check_existing=True);area.spaces.active.clip=clip
                area.spaces.active.show_region_toolbar=False;area.spaces.active.show_region_ui=False;area.spaces.active.show_region_header=False
                snapshot['owned_clip']=clip if clip not in before_clips else None
                if sync_video not in bpy.app.handlers.frame_change_post:bpy.app.handlers.frame_change_post.append(sync_video)
            context.scene.lc_settings.animation_view='EDIT';sync_video(context.scene)
            context.workspace.status_text_set('Rigmodo Motion Editor · cyan points show heel and forefoot · Esc / Finish Editing returns to your layout')
            from . import rig_mapping,motion_contacts
            if set(rig_mapping.CORE)<=set(rig_mapping.names(rig)):
                roles={r:b.name for r,b in zip(rig_mapping.names(rig),rig.data.bones)}
                snapshot['roles']=roles;snapshot['markers']=motion_contacts.soles(context,rig,roles)
                snapshot['handler']=bpy.types.SpaceView3D.draw_handler_add(draw_markers,(snapshot,),'WINDOW','POST_VIEW')
            return {'FINISHED'}
        except (ValueError,RuntimeError) as exc:
            if context.window and context.window.as_pointer() in _editors:bpy.ops.local_character.close_motion_editor()
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_OT_close_motion_editor(Operator):
    bl_idname='local_character.close_motion_editor';bl_label='Finish Editing'
    def execute(self,context):
        state=_editors.pop(context.window.as_pointer(),None)
        if not state:return {'FINISHED'}
        state['workspace'].status_text_set(None)
        if state.get('handler'):bpy.types.SpaceView3D.draw_handler_remove(state['handler'],'WINDOW');state['handler']=None
        area=state['area'];original=state['original']
        try:
            if area in list(context.screen.areas) and original in list(context.screen.areas):
                with context.temp_override(area=original):
                    bpy.ops.screen.area_join(source_xy=(original.x+original.width//2,original.y+original.height//2),target_xy=(area.x+area.width//2,area.y+area.height//2))
        except (ReferenceError,RuntimeError):pass
        try:
            saved=state.get('view_state')
            if saved and original.type=='VIEW_3D':
                space=original.spaces.active;view=space.region_3d
                space.show_region_ui=saved['show_region_ui'];space.show_region_toolbar=saved['show_region_toolbar']
                view.view_location=saved['location'];view.view_rotation=saved['rotation'];view.view_distance=saved['distance'];view.view_perspective=saved['perspective']
        except ReferenceError:pass
        if context.scene==state['scene']:
            try:
                if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
                for obj in context.selected_objects:obj.select_set(False)
                for obj in state['selected']:
                    if obj.name in context.view_layer.objects:obj.select_set(True)
                active=state['active']
                if active and active.name in context.view_layer.objects:
                    context.view_layer.objects.active=active
                    if state['mode'] in {'POSE','EDIT_ARMATURE'}:bpy.ops.object.mode_set(mode='POSE' if state['mode']=='POSE' else 'EDIT')
                context.scene.frame_set(state['frame'],subframe=state['subframe'])
            except (ReferenceError,RuntimeError):pass
        clip=state.get('owned_clip')
        if clip and clip.users==0:bpy.data.movieclips.remove(clip)
        if not _editors and sync_video in bpy.app.handlers.frame_change_post:bpy.app.handlers.frame_change_post.remove(sync_video)
        return {'FINISHED'}


def draw_markers(state):
    try:
        context=bpy.context
        if not context.area or context.area!=state['original'] or context.scene!=state['scene']:return
        import gpu
        from gpu_extras.batch import batch_for_shader
        from . import motion_contacts
        rig=state['rig'];roles=state['roles'];saved=rig.get('lc_sole_markers','')
        if saved!=state.get('marker_key',''):
            state['markers']=motion_contacts.soles(context,rig,roles);state['marker_key']=saved
        positions=[rig.matrix_world@rig.pose.bones[roles[side+'Foot']].matrix@point for side in ('Left','Right') for point in state['markers'][side]]
        shader=gpu.shader.from_builtin('UNIFORM_COLOR');shader.bind();gpu.state.blend_set('ALPHA');gpu.state.point_size_set(9.)
        shader.uniform_float('color',(.1,.75,1.,.95));batch_for_shader(shader,'POINTS',{'pos':positions}).draw(shader)
        lines=[];ground=context.scene.lc_settings.ground_height
        for point in positions:lines.extend([point,(point.x,point.y,ground)])
        shader.uniform_float('color',(.1,.75,1.,.4));batch_for_shader(shader,'LINES',{'pos':lines}).draw(shader)
    except (ReferenceError,KeyError,ValueError):pass
    finally:
        if 'gpu' in locals():gpu.state.point_size_set(1.);gpu.state.blend_set('NONE')


def editor_header(self,context):
    if context.window and context.window.as_pointer() in _editors:
        row=self.layout.row(align=True);row.label(text='Rigmodo · Motion Editor',icon='ACTION');row.popover(panel='LC_PT_main',text='Tools')
        row.operator('local_character.close_motion_editor',text='Finish Editing',icon='CHECKMARK')
    else:self.layout.popover(panel='LC_PT_main',text='Rigmodo',icon='ARMATURE_DATA')


def sync_video(scene,*args):
    if not _editors or bpy.app.is_job_running('RENDER'):return
    fps=scene.render.fps/scene.render.fps_base
    for state in _editors.values():
        try:
            area=state['area']
            if state['scene']!=scene or area.type!='CLIP_EDITOR':continue
            clip=area.spaces.active.clip
            if clip:
                seconds=state['video_start']+(scene.frame_current_final-state['action_start'])/fps
                area.spaces.active.clip_user.frame_current=max(1,min(clip.frame_duration,round(seconds*clip.fps)+1));area.tag_redraw()
        except ReferenceError:pass


@bpy.app.handlers.persistent
def cleanup(*args):
    for key,state in list(_editors.items()):
        try:
            original=state['original'];window=state['window'];region=next(r for r in original.regions if r.type=='WINDOW')
            with bpy.context.temp_override(window=window,area=original,region=region):bpy.ops.local_character.close_motion_editor()
        except (ReferenceError,RuntimeError,StopIteration):
            if state.get('handler'):bpy.types.SpaceView3D.draw_handler_remove(state['handler'],'WINDOW')
    _editors.clear()
    if sync_video in bpy.app.handlers.frame_change_post:bpy.app.handlers.frame_change_post.remove(sync_video)


CLASSES=(LC_MT_animation_actions,LC_OT_create_animation,LC_OT_motion_editor,LC_OT_close_motion_editor)
