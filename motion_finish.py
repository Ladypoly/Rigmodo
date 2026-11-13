# SPDX-License-Identifier: GPL-3.0-or-later
"""Editable loop finishing on a new Action; preserve ground travel and source keys."""
import json
import math
from mathutils import Quaternion,Vector
from .animation import selected_action


def loop(context,rig,blend_frames=8):
    selection=selected_action(rig,context.scene)
    original=selection['action'];start=selection['frame_start'];end=selection['frame_end']
    if not original.get('lc_source_fps'):raise ValueError('Loop finishing currently supports generated Rigmodo Actions')
    if not 2<=blend_frames<end-start:raise ValueError('Loop blend must span at least two frames and be shorter than the clip')
    action=original.copy();action.name=original.name+'_Loop'
    slot=next((s for s in action.slots if s.identifier==selection['slot'].identifier),None)
    if slot is None:raise ValueError('Copied Action slot is missing')
    curves=[]
    for layer in action.layers:
        for strip in layer.strips:
            bag=strip.channelbag(slot,ensure=False)
            if bag:curves.extend(bag.fcurves)
    groups={}
    for curve in curves:
        if not curve.data_path.endswith(('rotation_quaternion','location')):continue
        name=json.loads(curve.data_path.split('[')[1].split(']')[0])
        if name.rsplit(':',1)[-1]=='Root' and not rig.data.bones[name].use_deform and not original.get('lc_in_place'):continue
        groups.setdefault(curve.data_path,{})[curve.array_index]=curve
    for path,axes in groups.items():
        if path.endswith('rotation_quaternion') and set(axes)!=set(range(4)):
            __import__('bpy').data.actions.remove(action);raise ValueError('Quaternion loop blending requires all four keyed components')
    for path,axes in groups.items():
        quaternion=path.endswith('rotation_quaternion')
        if not quaternion and not path.endswith('location'):continue
        first=Quaternion([axes[i].evaluate(start) for i in range(4)]).normalized() if quaternion else None
        if quaternion:
            next_pose=Quaternion([axes[i].evaluate(start+1) for i in range(4)]).normalized()
            if first.dot(next_pose)<0:next_pose.negate()
            velocity=(first.conjugated()@next_pose).to_exponential_map()
        else:velocity={i:curve.evaluate(start+1)-curve.evaluate(start) for i,curve in axes.items()}
        raw={frame:{i:curve.evaluate(frame) for i,curve in axes.items()} for frame in range(end-blend_frames,end+1)}
        for frame in range(end-blend_frames,end+1):
            t=(frame-(end-blend_frames))/blend_frames;t=t*t*(3-2*t)
            if quaternion:
                current=Quaternion([raw[frame][i] for i in range(4)]).normalized()
                target=first@Quaternion(velocity*(frame-end))
                if current.dot(target)<0:target.negate()
                value=current.slerp(target,t)
                if frame>=end-1:value=target
            else:
                value={i:raw[frame][i]*(1-t)+(curve.evaluate(start)+velocity[i]*(frame-end))*t for i,curve in axes.items()}
                if frame>=end-1:value={i:curve.evaluate(start)+velocity[i]*(frame-end) for i,curve in axes.items()}
            for i,curve in axes.items():
                key=curve.keyframe_points.insert(frame,value[i],options={'FAST'});key.interpolation='LINEAR'
        for curve in axes.values():curve.update()
    # Existing float keys in the blend range would override the inserted samples.
    # Evaluate the final blended trajectory first, then remove redundant interior keys.
    for axes in groups.values():
        for curve in axes.values():
            for key in list(curve.keyframe_points):
                if end-blend_frames<key.co.x<end and abs(key.co.x-round(key.co.x))>1e-5:
                    curve.keyframe_points.remove(key)
            curve.update()
    original.use_fake_user=True
    rig.animation_data.action=action;rig.animation_data.action_slot=slot
    action['lc_loop_finished']=True;action['lc_loop_blend_frames']=blend_frames;action['lc_loop_seam_velocity']='matched_one_frame'
    context.scene.frame_set(context.scene.frame_current,subframe=context.scene.frame_subframe)
    return action
