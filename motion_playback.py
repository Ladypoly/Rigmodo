# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-Action loop intent and one-shot viewport playback."""
import re
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty
from . import animation

_watched={}
_pending={}
_once={'attack','attacks','attacking','death','dead','die','dies','dying'}
_repeat={'walk','walks','walking','run','runs','running','idle','idling','crawl','crawls','crawling'}


def words(action):return set(re.findall('[a-z]+',(action.name+' '+str(action.get('lc_motion_prompt',''))).lower()))


def looping(action):
    explicit=action.get('lc_clip_loop')
    if type(explicit) is bool:return explicit
    if words(action)&_once:return False
    period=action.get('lc_loop_period_frames')
    return (type(period) is int and period>=2) or bool(action.get('lc_loop_finished')) or bool(words(action)&_repeat)


def set_looping(action,value):
    action['lc_clip_loop']=bool(value)
    for scene in bpy.data.scenes:
        if any(o.type=='ARMATURE' and o.animation_data and o.animation_data.action==action for o in scene.objects):
            scene.lc_settings.loop_action=bool(value)


def stamp(action,prompt):
    action['lc_motion_prompt']=prompt
    action['lc_clip_loop']=looping(action)


def export_loop(action,fallback=False):
    period=action.get('lc_loop_period_frames')
    if 'lc_clip_loop' in action or words(action)&_once or action.get('lc_loop_finished') or (type(period) is int and period>=2):
        return looping(action)
    return bool(fallback)


def range_for(scene,selection):
    if selection['action'].library is None and 'lc_clip_loop' not in selection['action']:
        selection['action']['lc_clip_loop']=looping(selection['action'])
    scene.use_preview_range=True;scene.frame_preview_start=selection['frame_start'];scene.frame_preview_end=selection['frame_end']
    period=selection['action'].get('lc_loop_period_frames')
    if looping(selection['action']) and type(period) is int and period>=2:
        scene.frame_preview_end=min(scene.frame_preview_end,scene.frame_preview_start+period-1)
    scene.lc_settings.loop_action=looping(selection['action'])


def stop(context):
    if context.window:
        key=context.window.as_pointer();_watched.pop(key,None);_pending.pop(key,None)
    if context.screen and context.screen.is_animation_playing:bpy.ops.screen.animation_cancel(restore_frame=False)


def preview(context,rig,selection):
    stop(context);range_for(context.scene,selection);context.scene.frame_set(selection['frame_start'])
    if not bpy.app.background and context.screen:bpy.ops.screen.animation_play()


def active_rig(window):
    obj=window.view_layer.objects.active
    return obj if obj and obj.type=='ARMATURE' else obj.find_armature() if obj and obj.type=='MESH' else None


def finish_pending():
    pending=list(_pending.items());_pending.clear()
    for key,(window,scene,rig,action,end) in pending:
        try:
            if window.scene!=scene or active_rig(window)!=rig or not rig.animation_data or rig.animation_data.action!=action or looping(action):continue
            if window.screen.is_animation_playing:
                with bpy.context.temp_override(window=window):bpy.ops.screen.animation_cancel(restore_frame=False)
                scene.frame_set(end)
            _watched.pop(key,None)
        except (ReferenceError,RuntimeError):_watched.pop(key,None)
    return None


@persistent
def on_frame(scene,*_):
    if bpy.app.background:return
    for window in bpy.context.window_manager.windows:
        key=window.as_pointer()
        if window.scene!=scene or not window.screen.is_animation_playing:
            _watched.pop(key,None);continue
        rig=active_rig(window);action=rig.animation_data.action if rig and rig.animation_data else None
        managed=action and (any(k in action for k in ('lc_clip_loop','lc_source_fps','lc_motion_provider','lc_loop_period_frames','lc_loop_finished')) or getattr(action,'lc_clip_owner',None))
        if not managed or looping(action):_watched.pop(key,None);continue
        slot=rig.animation_data.action_slot
        signature=(scene.as_pointer(),rig.as_pointer(),action.session_uid,slot.handle if slot else 0)
        if key not in _watched or _watched[key][0]!=signature:
            try:selection=animation.selected_action(rig,scene)
            except ValueError:continue
            range_for(scene,selection);_watched[key]=(signature,selection['frame_end'])
        end=_watched[key][1]
        if scene.frame_current>=end:
            _pending[key]=(window,scene,rig,action,end)
            # Cancel outside dependency-graph evaluation, then hold the exact last frame.
            if not bpy.app.timers.is_registered(finish_pending):bpy.app.timers.register(finish_pending,first_interval=0.)


@persistent
def reset(_=None):
    _watched.clear();_pending.clear()
    if bpy.app.timers.is_registered(finish_pending):bpy.app.timers.unregister(finish_pending)


def register():
    bpy.types.Action.lc_clip_loop=BoolProperty(name='Loop',description='Repeat this clip; disable for attacks, deaths and other one-shot animations',get=looping,set=set_looping)
    bpy.app.handlers.frame_change_post.append(on_frame);bpy.app.handlers.load_post.append(reset)


def unregister():
    reset()
    if on_frame in bpy.app.handlers.frame_change_post:bpy.app.handlers.frame_change_post.remove(on_frame)
    if reset in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(reset)
    del bpy.types.Action.lc_clip_loop
