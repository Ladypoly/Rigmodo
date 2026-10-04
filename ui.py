# SPDX-License-Identifier: GPL-3.0-or-later
"""Four quiet workflow steps; installation and engine tuning live in Preferences."""
import json,textwrap
import bpy
from bpy.types import Operator
from . import configuration,skinning,placement,motion_jobs,install_jobs,deformation_qa,landmarks

def message(layout,text,icon='NONE'):
    for i,line in enumerate(textwrap.wrap(text,width=38)):layout.label(text=line,icon=icon if i==0 else 'NONE')

def scope(context):
    try:return placement.selected(context)
    except ValueError:
        try:return motion_jobs.selected_rig(context),[]
        except ValueError:return None,[]

def details(layout,key,title):
    header,body=layout.panel(key,default_closed=True);header.label(text=title)
    return body

def choose_weight_bone(settings,context):
    mesh=context.active_object
    if mesh and mesh.type=='MESH' and settings.ui_weight_bone in mesh.vertex_groups:
        mesh.vertex_groups.active_index=mesh.vertex_groups[settings.ui_weight_bone].index

class LC_OT_preferences(Operator):
    bl_idname='local_character.preferences'
    bl_label='Extension Settings'
    bl_description='Open provider setup and technical defaults in Preferences'
    def execute(self,context):bpy.ops.preferences.addon_show(module=__package__);return {'FINISHED'}

class LC_OT_select_character(Operator):
    bl_idname='local_character.select_character'
    bl_label='Select Character Meshes'
    bl_description='Select the visible meshes belonging to the active rig'
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context)
            if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            helpers={b.custom_shape for b in rig.pose.bones if b.custom_shape}
            meshes=[o for o in context.view_layer.objects if o.type=='MESH' and o not in helpers and o.visible_get() and
                (o.parent==rig or any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers))]
            if not meshes:raise ValueError('This rig has no visible character meshes')
            from .workflow import select
            select(context,rig,meshes)
        except (ValueError,RuntimeError) as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

class LC_OT_object_mode(Operator):
    bl_idname='local_character.object_mode'
    bl_label='Back to Object Mode'
    def execute(self,context):bpy.ops.object.mode_set(mode='OBJECT');return {'FINISHED'}

class LC_OT_weight_editor(Operator):
    bl_idname='local_character.weight_editor'
    bl_label='Open Weight Editor'
    bl_description='Paint bone weights using a focused skinning panel and Blender brushes'
    def execute(self,context):
        try:
            if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            rig,meshes=skinning.selection(context);mesh=next((o for o in meshes if o==context.active_object),meshes[0])
            if not mesh.vertex_groups:raise ValueError('Skin the character before opening its weight editor')
            context.view_layer.objects.active=mesh;bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
            if not context.tool_settings.weight_paint.brush:
                bpy.ops.brush.asset_activate(asset_library_type='ESSENTIALS',relative_asset_identifier='brushes/essentials_brushes-mesh_weight.blend/Brush/Paint')
            s=context.scene.lc_settings;s.ui_step='SKIN';s.ui_weight_bone=mesh.vertex_groups.active.name if mesh.vertex_groups.active else ''
        except (ValueError,RuntimeError) as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

class LC_OT_joint_editor(Operator):
    bl_idname='local_character.edit_joints'
    bl_label='Edit Joints'
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context)
            if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            for obj in context.selected_objects:obj.select_set(False)
            rig.select_set(True);context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
        except (ValueError,RuntimeError) as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

class LC_OT_pose_editor(Operator):
    bl_idname='local_character.test_pose'
    bl_label='Test Deformation'
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context)
            if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            for obj in context.selected_objects:obj.select_set(False)
            rig.select_set(True);context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='POSE')
        except (ValueError,RuntimeError) as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

def draw(layout,context):
    s=context.scene.lc_settings;resolved=configuration.settings(context)
    layout.use_property_split=False
    if landmarks._sessions:
        layout.label(text='Landmark Editor',icon='ORIENTATION_VIEW')
        message(layout,'Follow the prompts in the viewport. Click to place markers; drag to adjust.')
        layout.separator();layout.label(text='Enter: accept   |   Esc: cancel')
        return
    row=layout.row(align=True);row.prop(s,'ui_step',expand=True)
    rig,meshes=scope(context)
    row=layout.row(align=True)
    row.label(text=(meshes[0].name if len(meshes)==1 else f'{len(meshes)} mesh objects') if meshes else 'Select your avatar',icon='MESH_DATA')
    row.operator('local_character.preferences',text='',icon='PREFERENCES')
    if rig and not meshes:layout.operator('local_character.select_character')
    if context.mode=='PAINT_WEIGHT' and s.ui_step=='SKIN':
        mesh=context.active_object
        layout.separator();layout.label(text='Weight Editor',icon='WPAINT_HLT')
        layout.prop_search(s,'ui_weight_bone',mesh,'vertex_groups',text='Bone')
        paint=context.tool_settings.weight_paint;unified=paint.unified_paint_settings
        if paint.brush:
            layout.prop(unified if unified.use_unified_weight else paint.brush,'weight',text='Weight')
            layout.prop(unified if unified.use_unified_strength else paint.brush,'strength',text='Strength')
            layout.prop(unified if unified.use_unified_size else paint.brush,'size',text='Brush size')
        message(layout,'Paint on the surface. Use Blender’s brush toolbar for Paint and Blur.')
        layout.operator('local_character.test_pose',text='Test Deformation',icon='POSE_HLT')
        layout.operator('local_character.object_mode',text='Finish Weight Editing',icon='CHECKMARK');return
    if context.mode!='OBJECT':layout.operator('local_character.object_mode')
    available=install_jobs.inventory(resolved)
    provider={'RIG':'Joint placement','SKIN':'AI skinning','MOTION':'Generated motion'}.get(s.ui_step)
    if provider and not available[provider]:message(layout,'Local models need setup. Open Extension Settings.',icon='INFO')
    layout.separator()
    if s.ui_step=='RIG':
        layout.prop(s,'ui_rig_mode',expand=True)
        if s.ui_rig_mode=='ASSISTED':
            message(layout,'Set five landmark groups in front view. AI fills in depth and fingers.')
            layout.prop(s,'landmark_symmetry')
            layout.operator('local_character.edit_landmarks',text='Edit Landmarks' if s.landmark_data else 'Set Landmarks',icon='ORIENTATION_VIEW')
        row=layout.row();row.scale_y=1.45;row.enabled=bool(meshes) and context.mode=='OBJECT' and not skinning._jobs
        if s.ui_rig_mode=='ASSISTED':row.enabled=row.enabled and bool(s.landmark_data)
        row.operator('local_character.place_joints',text='Generate Rig',icon='ARMATURE_DATA').use_landmarks=s.ui_rig_mode=='ASSISTED'
        message(layout,s.placement_status)
        body=details(layout,'lc_rig_options','Rig options')
        if body:
            message(body,'Adjust generated joints in Edit Mode.')
            body.operator('local_character.edit_joints')
            row=body.row(align=True);row.operator('local_character.lock_joints',text='Lock').enabled=True;row.operator('local_character.lock_joints',text='Unlock').enabled=False
            body.prop(s,'fit_bounds')
            if not s.fit_bounds:body.prop(s,'height')
            body.prop(s,'arm_angle');body.prop(s,'eyes');body.operator('local_character.create_template',text='Create Manual Template')
            body.operator('local_character.add_twists',text='Add Forearm Twists');body.operator('local_character.update_twist_pose')
            body.prop(s,'optional_kind')
            if s.optional_kind=='SOCKET':body.prop(s,'optional_parent');body.prop(s,'optional_name')
            body.operator('local_character.add_optional_bone',text='Add Bone at Cursor')
    elif s.ui_step=='SKIN':
        if not rig:message(layout,'Generate a rig first, then select it with the avatar mesh.',icon='INFO')
        method=s.ui_skin_method if s.ui_skin_advanced else 'AI'
        row=layout.row();row.scale_y=1.45;row.enabled=bool(rig and meshes) and context.mode=='OBJECT' and not skinning._jobs
        if method=='AI':row.operator('local_character.build_character',text='Skin Avatar',icon='MOD_ARMATURE').auto_skin=True
        else:row.operator('local_character.refine_regions',text='Skin Avatar',icon='MOD_ARMATURE').binding_method=method
        message(layout,(s.workflow_status if s.workflow_skin_only else s.skin_status) if method=='AI' else s.region_status)
        layout.prop(s,'ui_skin_advanced')
        if s.ui_skin_advanced:
            layout.prop(s,'ui_skin_method')
            if method=='AI':layout.prop(s,'workflow_rigid',text='Rigid character parts')
            layout.operator('local_character.weight_editor',icon='WPAINT_HLT')
            layout.prop(s,'refine_method',text='Correction')
            layout.prop(s,'refine_strength');layout.prop(s,'refine_selected')
            layout.operator('local_character.refine_regions',text='Refine Weights')
            if method=='AI':message(layout,s.region_status)
            if s.region_report:
                try:
                    fallback=next((r['volume_fallback_reason'] for r in json.loads(s.region_report) if r.get('volume_fallback_reason')),None)
                    if fallback:message(layout,'Surface fallback: '+fallback,icon='INFO')
                except (ValueError,KeyError):pass
            layout.operator('local_character.check_deformation',text='Check Deformation')
            if s.deformation_report:
                try:
                    severe,warnings=deformation_qa.findings(json.loads(s.deformation_report))
                    message(layout,(severe+warnings)[0] if severe or warnings else 'No severe strain in tested poses.',icon='ERROR' if severe else 'CHECKMARK')
                except (ValueError,KeyError):pass
            body=details(layout,'lc_region_options','Selected region')
            if body:
                message(body,'Select vertices in Edit Mode; return to Object Mode.')
                body.prop(s,'region_kind',text='Behavior')
                if s.region_kind=='RIGID' and rig:body.prop_search(s,'region_bone',rig.data,'bones',text='Attach to')
                elif s.region_kind!='RIGID':body.prop(s,'region_digit',text='Finger')
                body.operator('local_character.mark_region',text='Apply Region Rule')
                row=body.row(align=True);row.operator('local_character.protect_region',text='Protect').enabled=True;row.operator('local_character.protect_region',text='Unprotect').enabled=False
                body.operator('local_character.clear_region',text='Clear Region Rules')
    elif s.ui_step=='MOTION':
        layout.prop(s,'motion_prompt',text='Motion');layout.prop(s,'motion_frames',text='Length (frames)')
        layout.prop(s,'motion_in_place')
        row=layout.row();row.scale_y=1.45;row.enabled=bool(rig and meshes) and context.mode=='OBJECT' and not skinning._jobs
        row.operator('local_character.generate_motion',text='Generate Motion',icon='ACTION')
        if rig and rig.animation_data and rig.animation_data.action:layout.operator('local_character.preview_motion',text='Preview Motion',icon='PREVIEW_RANGE')
        message(layout,s.motion_status)
        body=details(layout,'lc_motion_options','Motion options')
        if body:
            body.prop(s,'motion_contacts');body.prop(s,'motion_heading');body.prop(s,'motion_hand_curl');body.prop(s,'hand_controls')
            if s.hand_controls:
                body.prop(s,'hand_side');body.prop(s,'hand_preset');body.operator('local_character.hand_preset')
                from .skeleton import FINGERS
                for finger in FINGERS:body.prop(s,'hand_'+s.hand_side.lower()+'_'+finger.lower())
            body.prop(s,'motion_loop_blend');body.operator('local_character.finish_loop',text='Blend Loop Endpoint')
    else:
        layout.prop(s,'character_name',text='Name');layout.prop(s,'export_directory',text='Folder');layout.prop(s,'profile',text='Unity rig')
        layout.prop(s,'include_action',text='Include animation')
        if s.include_action:layout.prop(s,'loop_action',text='Loop in Unity')
        row=layout.row();row.scale_y=1.45;row.enabled=bool(rig and meshes) and context.mode=='OBJECT' and not skinning._jobs
        row.operator('local_character.export_unity',text='Export to Unity',icon='EXPORT')
        body=details(layout,'lc_export_checks','Export checks')
        if body:
            body.operator('local_character.preflight',text='Check Character')
            if s.last_report:
                try:
                    report=json.loads(s.last_report)
                    for finding in (report.get('errors',[])+report.get('warnings',[]))[:3]:message(body,finding,icon='INFO')
                    if report.get('ready'):body.label(text='Ready for export',icon='CHECKMARK')
                except ValueError:pass
            if s.last_export:message(body,'Last export: '+s.last_export)
    if s.workflow_status and skinning._jobs:message(layout,s.workflow_status)

def draw_preferences(layout,context,prefs):
    resolved=configuration.settings(context);s=context.scene.lc_settings
    layout.prop(prefs,'page',expand=True)
    if prefs.page=='SETUP':
        for name,ready in install_jobs.inventory(resolved).items():layout.label(text=name+(': ready' if ready else ': setup needed'),icon='CHECKMARK' if ready else 'ERROR')
        layout.prop(prefs,'setup_python');layout.prop(prefs,'setup_archive');layout.operator('local_character.install_providers')
        message(layout,s.setup_status)
        box=layout.box();box.label(text='Provider locations')
        for key in ('placement_python','skin_executable','skin_models','motion_provider'):box.prop(prefs,key)
    elif prefs.page=='DEFAULTS':
        box=layout.box();box.label(text='AI inference')
        for key in ('skin_device','skin_beams','motion_steps','motion_seed'):box.prop(prefs,key)
        box=layout.box();box.label(text='Geometric solvers')
        for key in ('refine_iterations','refine_seams','voxel_resolution'):box.prop(prefs,key)
        box=layout.box();box.label(text='Workflow behavior');box.prop(prefs,'workflow_hide_sources');box.prop(prefs,'workflow_allow_strain')
    else:
        message(layout,'Finished results are applied automatically. Recovery is for interrupted sessions.')
        for key,op in (('placement_job','apply_placement_job'),('skin_job','apply_skin_job'),('region_job','apply_region_job'),('motion_job','apply_motion_job')):
            if getattr(s,key):layout.operator('local_character.'+op)
        box=layout.box();box.label(text='Complete workflow')
        for key in ('workflow_reuse_joints','workflow_rebind','workflow_rigid','workflow_twists','workflow_motion','workflow_export','workflow_loop'):box.prop(s,key)
        box.operator('local_character.build_character',text='Run Complete Workflow')

CLASSES=(LC_OT_preferences,LC_OT_select_character,LC_OT_object_mode,LC_OT_weight_editor,LC_OT_joint_editor,LC_OT_pose_editor)
