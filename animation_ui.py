# SPDX-License-Identifier: GPL-3.0-or-later
"""A quiet Blender sidebar with explicit source and retargeting stages."""
import json
import bpy
from bpy.types import Operator,Menu
from . import configuration,ui,motion_sources,motion_library,motion_clips,motion_jobs,rig_mapping


def duration_changed(self,context):
    self.motion_frames=min(900,round(self.motion_duration*30)+1);self.unimate_frames=min(60,max(15,self.motion_frames))


def creature_character(context,rig):
    from . import creatures
    if creatures.is_creature(rig):return True
    try:
        if rig and set(rig_mapping.CORE)<=set(rig_mapping.names(rig)):return False
    except ValueError:return False
    return bool(rig) and context.scene.lc_settings.rig_type=='CREATURE'


def current(layout,context,rig):
    if not rig:return
    action=rig.animation_data.action if rig.animation_data else None
    row=layout.row(align=True);row.label(text='Current animation',icon='ACTION');row.menu('LC_MT_animation_actions',text='',icon='DOWNARROW_HLT')
    row=layout.row(align=True);row.operator('local_character.select_motion_clip',text='',icon='VIEWZOOM')
    if action:row.prop(action,'name',text='');row.operator('local_character.preview_motion',text='',icon='PLAY')
    else:row.label(text='No animation applied')


def sources(layout,context):
    state=context.window_manager.lc_motion_library
    row=layout.row(align=True);row.prop(state,'query',text='',icon='VIEWZOOM');row.operator('local_character.refresh_motion_library',text='',icon='FILE_REFRESH')
    layout.operator('local_character.open_motion_assets',text='Load from library…',icon='ASSET_MANAGER')
    if not state.entries:
        ui.message(layout,'Create a motion or load one from a file or the Asset Browser.');return
    layout.template_list('LC_UL_source_motions','rigmodo_working_sources',state,'entries',state,'index',rows=min(5,max(2,len(state.entries))))
    row=layout.row(align=True);row.operator('local_character.select_source_motions',text='Select all').mode='ALL';row.operator('local_character.select_source_motions',text='Clear').mode='NONE';row.operator('local_character.unload_source_motions',text='',icon='X')
    row=layout.row(align=True);row.operator('local_character.preview_source_motion',text='Preview source',icon='PLAY');row.operator('local_character.stop_source_preview',text='',icon='PAUSE')


def pose_source(layout,context,creature=False):
    s=context.scene.lc_settings
    layout.prop(s,'pose_source_rig',text='Creature rig' if creature else 'Pose rig')
    row=layout.row(align=True);row.operator('local_character.use_pose_source',text='Use selected')
    if not creature:row.operator('local_character.create_pose_source',text='New pose rig',icon='ADD')
    if s.pose_source_rig:
        if context.mode=='POSE':layout.operator('local_character.object_mode',text='Finish pose editing',icon='CHECKMARK')
        else:layout.operator('local_character.edit_source_poses',text='Edit pose keys',icon='POSE_HLT')
    if not creature:ui.message(layout,'Key poses on the timeline. MotionBricks needs two or more keys.')


def draw(layout,context,rig=None,creature=False):
    s=context.scene.lc_settings;layout.use_property_split=False
    layout.row(align=True).prop(s,'animation_view',expand=True)
    body=layout.column();body.enabled=not motion_sources.busy()
    if s.animation_view=='BROWSE':
        row=body.row(align=True);row.operator('local_character.import_library_motions',text='Import files');row.operator('local_character.import_motion_folder',text='Import folder')
        sources(body,context)
        body.operator('local_character.save_library_motion',text='Save character animation',icon='ADD')
    elif s.animation_view=='EDIT':
        body.label(text='Source motions',icon='ACTION');sources(body,context)
        body.separator();body.label(text='Target',icon='ARMATURE_DATA')
        body.prop(s,'retarget_selected_characters',text='Use all selected characters')
        if not s.retarget_selected_characters:
            body.prop(s,'character',text='Character');body.operator('local_character.use_character_selection',text='Use selected character')
        body.prop(s,'retarget_loop',text='Playback');body.prop(s,'retarget_in_place',text='In place')
        row=body.row();row.scale_y=1.3;row.operator('local_character.retarget_sources',text='Retarget motions',icon='ACTION')
        try:target=motion_sources.targets(context)[0]
        except ValueError:target=None
        if target:body.separator();current(body,context,target)
        adjustments=ui.details(body,'lc_motion_adjustments','Motion adjustments')
        if adjustments:
            controls=context.window_manager.lc_motion_library
            adjustments.prop(s,'stabilize_video')
            if target:adjustments.operator('local_character.refine_motion',text='Refine current clip with MotionBricks…')
            adjustments.prop(controls,'speed');adjustments.prop(controls,'mirror');adjustments.prop(controls,'spacing')
            if len(motion_sources.chosen(context))==1:
                row=adjustments.row(align=True);row.prop(controls,'trim_start');row.prop(controls,'trim_end')
        options=ui.details(body,'lc_retarget_options','Retarget options')
        if options:
            options.prop(s,'motion_contacts',text='Automatic foot placement');options.prop(s,'ground_height');options.prop(s,'show_contact_indicators')
            if target:
                options.operator('local_character.detect_motion_mapping',text='Suggest bone mapping');options.operator('local_character.accept_motion_mapping',text='Accept reviewed mapping')
                proposals=json.loads(target.get('lc_role_suggestions','{}'))
                for role,bone in proposals.items():options.label(text=role+' → '+bone)
                options.prop(s,'mapping_role');options.prop_search(s,'mapping_bone',target.data,'bones');options.operator('local_character.assign_motion_role')
                row=options.row(align=True);row.operator('local_character.ground_motion',text='Correct contacts');row.operator('local_character.make_animation_loop',text='Make loop copy')
                options.prop(s,'contact_side');options.prop(s,'contact_mode')
                row=options.row(align=True);row.prop(s,'contact_start');row.prop(s,'contact_end');options.operator('local_character.mark_contact_interval')
                options.operator('local_character.clear_contact_intervals')
                row=options.row(align=True);row.operator('local_character.set_sole_marker',text='Heel at cursor').point='HEEL';row.operator('local_character.set_sole_marker',text='Forefoot at cursor').point='BALL'
            if s.retarget_report:
                for error in json.loads(s.retarget_report)[:3]:ui.message(options,error['character']+' · '+error['error'],icon='ERROR')
        options=ui.details(body,'lc_scene_animation_source','Scene animation / image pose')
        if options:
            options.prop(s,'source_rig');options.prop(s,'source_action');options.operator('local_character.retarget_animation',text='Retarget scene Action')
            from . import image_pose
            image_pose.draw(options,context)
    else:
        tabs=body.grid_flow(row_major=True,columns=2,even_columns=True,even_rows=True,align=True)
        for key,name in [('KIMODO','Kimodo'),('MOTIONBRICKS','MotionBricks'),('VIDEO','Video to Motion'),('UNIMATE','UniMate')]:
            tabs.operator('local_character.motion_system_tab',text=name,depress=s.motion_system==key).system=key
        body.separator()
        if s.motion_system=='KIMODO':
            body.label(text='Text → reusable humanoid motion')
            body.prop(s,'motion_prompt',text='Motion');body.prop(s,'motion_duration',text='Seconds')
            body.prop(s,'motion_use_keyframes',text='Use pose keys')
            if s.motion_use_keyframes:pose_source(body,context)
        elif s.motion_system=='MOTIONBRICKS':
            body.label(text='Pose keys → reusable motion');pose_source(body,context)
        elif s.motion_system=='UNIMATE':
            body.label(text='Text → creature motion');pose_source(body,context,True)
            body.prop(s,'motion_prompt',text='Motion');body.prop(s,'motion_duration',text='Seconds')
            ui.message(body,'Creature generation supports up to 2 seconds per clip.')
        else:
            body.prop(configuration.settings(context).prefs or s,'capture_backend',text='Engine')
            body.prop(s,'video_input',expand=True)
            if s.video_input=='FILES':
                body.prop(s,'video_path',text='Video');body.operator('local_character.capture_video_batch',text='Batch capture videos…',icon='FILEBROWSER')
                body.prop(s,'capture_whole_video',text='Capture whole video')
                if not s.capture_whole_video:body.prop(s,'video_start',text='Start (s)');body.prop(s,'motion_duration',text='Length (s)')
                ui.message(body,'No avatar needed. Videos become reusable library motions.')
            else:
                body.prop(s,'motion_prompt',text='Motion');body.prop(s,'video_reference',text='Reference');body.prop(s,'motion_duration',text='Seconds')
                row=body.row();row.enabled=bool(context.active_object and context.active_object.type=='ARMATURE');row.operator('local_character.render_character_reference',text='Use selected character image')
        body.prop(s,'source_name',text='Name')
        row=body.row(align=True);row.prop(s,'source_loop',text='Loop');row.prop(s,'source_in_place',text='In place')
        row=body.row();row.scale_y=1.3;row.enabled=context.mode=='OBJECT' or s.motion_system=='VIDEO' or s.motion_system=='KIMODO' and not s.motion_use_keyframes;row.operator('local_character.create_motion_source',text='Capture to library' if s.motion_system=='VIDEO' and s.video_input=='FILES' else 'Generate to library',icon='ACTION')
        ui.message(body,'Save once. Retarget to characters when needed.')
        options=ui.details(body,'lc_motion_creation_options','Advanced')
        if options:
            if s.motion_system=='VIDEO' and s.source_loop and s.video_input=='FILES':options.prop(s,'video_cycle')
            if s.motion_system=='UNIMATE' and s.pose_source_rig:options.prop(s.pose_source_rig,'lc_unimate_forward');options.prop(s,'unimate_guidance')
            if context.mode=='POSE' and s.pose_source_rig and context.active_object==s.pose_source_rig:
                from . import auto_pose,image_pose
                auto_pose.draw(options,context);image_pose.draw(options,context)
    if s.motion_status:ui.message(layout,s.motion_status)


class LC_MT_animation_actions(Menu):
    bl_label='Animation'
    def draw(self,context):
        self.layout.operator('local_character.new_motion_clip',text='New empty animation',icon='ADD')
        self.layout.operator('local_character.save_library_motion',text='Save to library',icon='ASSET_MANAGER')
        self.layout.separator();self.layout.operator('local_character.delete_motion_clip',text='Delete animation',icon='TRASH')


class LC_OT_create_animation(Operator):
    bl_idname='local_character.create_animation';bl_label='Create Motion'
    def execute(self,context):return bpy.ops.local_character.create_motion_source()


CLASSES=(LC_MT_animation_actions,LC_OT_create_animation)
