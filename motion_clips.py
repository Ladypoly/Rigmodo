# SPDX-License-Identifier: GPL-3.0-or-later
"""Choose compatible bone Actions without editing other characters or NLA strips."""
import json
import math
import bpy
from bpy.props import EnumProperty, PointerProperty, StringProperty
from bpy.types import Operator
from . import animation, motion_jobs, skinning

_enum_cache={}


def slot_curves(action,slot):
    if not action.is_action_layered:return list(action.fcurves)
    if slot is None:return []
    curves=[]
    for layer in action.layers:
        for strip in layer.strips:
            bag=strip.channelbag(slot,ensure=False)
            if bag:curves.extend(bag.fcurves)
    return curves


def compatible(action,slot,rig):
    if slot and slot.target_id_type!='OBJECT':return False
    curves=slot_curves(action,slot)
    if not curves:return action.lc_clip_owner==rig
    for curve in curves:
        match=animation._BONE_PATH.fullmatch(curve.data_path)
        if not match or json.loads(match[1]) not in rig.data.bones:return False
    return True


def available(rig):
    return [(action,slot) for action in sorted(bpy.data.actions,key=lambda a:a.name.casefold())
            for slot in (list(action.slots) if action.is_action_layered else [None])
            if compatible(action,slot,rig)]


def identifier(action,slot):return f'{action.session_uid}:{slot.handle if slot else 0}'


def enum_items(self,context):
    if context is None:return []
    try:rig=motion_jobs.selected_rig(context)
    except ValueError:return []
    choices=available(rig);counts={}
    for action,slot in choices:counts[action.session_uid]=counts.get(action.session_uid,0)+1
    items=[]
    for action,slot in choices:
        key=(identifier(action,slot),action.name+(f' · {slot.name_display}' if counts[action.session_uid]>1 else ''))
        # Blender retains enum strings; stable numeric values also survive sorting changes.
        if key not in _enum_cache:_enum_cache[key]=(*key,'Use this animation on the selected rig',len(_enum_cache)+1)
        items.append(_enum_cache[key])
    return items


def editable(context):
    if context.mode not in {'OBJECT','POSE'} or skinning._jobs:return False
    try:rig=motion_jobs.selected_rig(context)
    except ValueError:return False
    return rig.library is None and rig.override_library is None


def select(context,rig,action,slot):
    if not compatible(action,slot,rig):raise ValueError('This animation does not match the selected rig bones')
    curves=slot_curves(action,slot)
    times=[p.co.x for c in curves for p in (*c.keyframe_points,*c.sampled_points)]
    start,end=(action.frame_start,action.frame_end) if action.use_frame_range else (min(times),max(times)) if times else (1,1)
    if not all(math.isfinite(v) for v in (start,end)):raise ValueError('Animation has an invalid frame range')
    previous=rig.animation_data.action if rig.animation_data else None
    if previous and previous.library is None:previous.use_fake_user=True
    if action.library is None:action.use_fake_user=True
    animation.attach_action(rig,{'action':action,'slot':slot})
    scene=context.scene;scene.use_preview_range=True;scene.frame_preview_start=math.floor(start);scene.frame_preview_end=max(math.floor(start),math.ceil(end))
    period=action.get('lc_loop_period_frames')
    if type(period) is int and period>=2:scene.frame_preview_end=min(scene.frame_preview_end,scene.frame_preview_start+period-1)
    scene.frame_set(scene.frame_preview_start)
    scene.lc_settings.motion_status=''
    context.view_layer.update()


def new(context,rig,name):
    if not name.strip():raise ValueError('Enter an animation name')
    action=bpy.data.actions.new(name.strip());action.use_fake_user=True;action.lc_clip_owner=rig
    slot=action.slots.new(id_type='OBJECT',name=rig.name)
    action.use_frame_range=True;action.frame_start=context.scene.frame_start
    action.frame_end=action.frame_start+max(1,round(context.scene.render.fps/context.scene.render.fps_base))
    select(context,rig,action,slot)
    return action


def deletable(rig,action):
    if action.library or action.override_library:raise ValueError('Linked animations cannot be deleted here')
    if not rig.animation_data or rig.animation_data.action!=action:raise ValueError('Select the animation to delete first')
    if action.users-int(action.use_fake_user)>1:
        raise ValueError('Animation is also used by another object or an NLA strip. Unlink those uses before deleting it')


def delete(context,rig,action):
    deletable(rig,action)
    choices=[(a,s) for a,s in available(rig) if a!=action]
    rig.animation_data.action=None
    for bone in rig.pose.bones:bone.matrix_basis.identity()
    if choices:select(context,rig,*choices[0])
    bpy.data.actions.remove(action)
    context.scene.lc_settings.motion_status=''
    context.view_layer.update()


class LC_OT_select_motion_clip(Operator):
    bl_idname='local_character.select_motion_clip';bl_label='Choose Animation';bl_options={'REGISTER','UNDO'}
    bl_description='Search animations whose bone channels match the selected rig'
    bl_property='clip'
    clip:EnumProperty(name='Animation',items=enum_items)
    @classmethod
    def poll(cls,context):return editable(context)
    def invoke(self,context,event):
        if not enum_items(self,context):self.report({'INFO'},'No compatible animations yet');return {'CANCELLED'}
        context.window_manager.invoke_search_popup(self);return {'FINISHED'}
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context)
            match=next(((a,s) for a,s in available(rig) if identifier(a,s)==self.clip),None)
            if match is None:raise ValueError('Animation changed; choose it again')
            select(context,rig,*match)
        except (ValueError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_new_motion_clip(Operator):
    bl_idname='local_character.new_motion_clip';bl_label='New Empty Animation';bl_options={'REGISTER','UNDO'}
    bl_description='Create a named empty Action in rest pose for keyframing; Generate Motion creates a new AI animation'
    name:StringProperty(name='Name',default='New Animation',maxlen=120)
    @classmethod
    def poll(cls,context):return editable(context)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=320)
    def draw(self,context):self.layout.prop(self,'name')
    def execute(self,context):
        try:new(context,motion_jobs.selected_rig(context),self.name)
        except (ValueError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_delete_motion_clip(Operator):
    bl_idname='local_character.delete_motion_clip';bl_label='Delete Animation';bl_options={'REGISTER','UNDO'}
    bl_description='Delete this Action after confirmation; shared and NLA animations are protected'
    clip_name:StringProperty(options={'HIDDEN','SKIP_SAVE'})
    @classmethod
    def poll(cls,context):
        if not editable(context):return False
        rig=motion_jobs.selected_rig(context);return bool(rig.animation_data and rig.animation_data.action)
    def invoke(self,context,event):
        rig=motion_jobs.selected_rig(context);action=rig.animation_data.action
        try:deletable(rig,action)
        except ValueError as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.clip_name=action.name
        return context.window_manager.invoke_confirm(self,event,title='Delete animation?',message=f'Delete "{action.name}"? The rig and meshes are kept.',confirm_text='Delete')
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);action=rig.animation_data.action
            if self.clip_name and action.name!=self.clip_name:raise ValueError('Active animation changed; delete again')
            name=action.name;delete(context,rig,action)
        except (ValueError,RuntimeError,KeyError,AttributeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},f'Deleted animation: {name}');return {'FINISHED'}


def draw(layout,context,rig):
    if not rig:return
    action=rig.animation_data.action if rig.animation_data else None
    box=layout.box();box.label(text='Animations',icon='ACTION')
    row=box.row(align=True)
    row.operator('local_character.select_motion_clip',text='',icon='DOWNARROW_HLT')
    if action:
        name=row.row(align=True);name.enabled=action.library is None;name.prop(action,'name',text='')
    else:row.label(text='Choose animation')
    row.operator('local_character.new_motion_clip',text='',icon='ADD')
    row.operator('local_character.delete_motion_clip',text='',icon='TRASH')
    if action:
        if not any(c.keyframe_points or c.sampled_points for c in slot_curves(action,rig.animation_data.action_slot)):
            box.label(text='Empty clip · add pose keyframes',icon='INFO')


CLASSES=(LC_OT_select_motion_clip,LC_OT_new_motion_clip,LC_OT_delete_motion_clip)

def register():bpy.types.Action.lc_clip_owner=PointerProperty(type=bpy.types.Object)
def unregister():del bpy.types.Action.lc_clip_owner
