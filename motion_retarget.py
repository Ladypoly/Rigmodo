# SPDX-License-Identifier: GPL-3.0-or-later
"""Retarget stored motion while preserving the selected rig's hierarchy and lengths."""
import math
import bpy
import numpy as np
from mathutils import Matrix,Vector,Quaternion
from . import motion_store,animation,motion_playback


def mapping(names):
    result={}
    for i,name in enumerate(names):
        key=motion_store.canonical(str(name))
        if key in result:raise ValueError('Ambiguous skeleton names: '+key)
        result[key]=i
    return result


def body_frame(rest,index):
    up=(rest[index['Head']].translation-rest[index['Hips']].translation).normalized()
    left=rest[index['LeftArm']].translation-rest[index['RightArm']].translation
    left=(left-up*left.dot(up)).normalized();back=up.cross(left).normalized()
    return Matrix((left,back,up)).transposed()


def sample(data,seconds):
    times=data['times'];i=min(len(times)-2,max(0,int(np.searchsorted(times,seconds,side='right')-1)))
    t=max(0.,min(1.,float((seconds-times[i])/(times[i+1]-times[i]))))
    result=[]
    for lo,hi in zip(data['poses'][i],data['poses'][i+1]):
        a,b=Matrix(lo.tolist()),Matrix(hi.tolist());q=a.to_quaternion().slerp(b.to_quaternion(),t)
        m=q.to_matrix().to_4x4();m.translation=a.translation.lerp(b.translation,t);result.append(m)
    return result


def apply(context,rig,data,name,start=0.,end=None,speed=1.,mirror=False,in_place=False,spacing=0.,loop=False):
    motion_store.validate(data);duration=float(data['times'][-1]);end=duration if end is None else end
    if not all(math.isfinite(v) for v in (start,end,speed,spacing)) or not 0<=start<end<=duration+.0001 or not .1<=speed<=4 or not -10<=spacing<=45:
        raise ValueError('Use a valid trim range, speed 0.1–4 and arm spacing −10°–45°')
    if rig.library or rig.override_library or rig.constraints or any(p.constraints for p in rig.pose.bones):raise ValueError('Use a local, unconstrained deform rig')
    if rig.animation_data and rig.animation_data.drivers:raise ValueError('Bake bone drivers before applying a library motion')
    context.view_layer.update()
    scales=rig.matrix_world.to_scale()
    if rig.matrix_world.determinant()<=0 or max(scales)-min(scales)>1e-5:raise ValueError('Apply mirrored or nonuniform rig scale on a working copy first')
    source_names=list(map(str,data['names']));src=mapping(source_names);dst=mapping([b.name for b in rig.data.bones])
    rest=[Matrix(m.tolist()) for m in data['rest']];target={b.name:b.matrix_local.copy() for b in rig.data.bones}
    ordered=sorted(rig.data.bones,key=lambda b:len(b.parent_recursive));lookup={str(n):i for i,n in enumerate(data['names'])}
    same=all(b.name in lookup and np.max(np.abs(np.asarray(b.matrix_local)-data['rest'][lookup[b.name]]))<1e-5 and
             (source_names[data['parents'][lookup[b.name]]] if data['parents'][lookup[b.name]]>=0 else None)==(b.parent.name if b.parent else None) for b in rig.data.bones)
    human=motion_store.humanoid(source_names) and motion_store.humanoid([b.name for b in rig.data.bones])
    if not same and not human:raise ValueError('Creature motions need the same skeleton. Humanoid motions can be retargeted across supported human rigs')
    if spacing and not human:raise ValueError('Arm spacing is a humanoid control')
    if human:
        source_basis=body_frame(rest,src);target_rest=[b.matrix_local for b in rig.data.bones];target_basis=body_frame(target_rest,dst)
        conversion=target_basis@source_basis.transposed()
        def leg_length(matrices,index):
            return sum((matrices[index['Left'+a]].translation-matrices[index['Left'+b]].translation).length for a,b in [('UpLeg','Leg'),('Leg','Foot')])
        scale=leg_length(target_rest,dst)/max(leg_length(rest,src),1e-6)
        anchor=src['Hips'];up=source_basis.col[2];left=source_basis.col[0]
    else:
        conversion=Matrix.Identity(3);scale=1.;anchor=next(i for i,p in enumerate(data['parents']) if p<0);up=Vector((0,0,1));left=None
        for i,label in enumerate(data['labels']):
            opposite=str(label).replace('Left','Right')
            if 'Left' in str(label) and opposite in data['labels']:
                j=list(data['labels']).index(opposite);left=(rest[i].translation-rest[j].translation).normalized();break
    reflection=Matrix.Identity(3)
    if mirror:
        if left is None:raise ValueError('Mirror needs identifiable left/right joints on this creature')
        reflection=Matrix((np.eye(3)-2*np.outer(left,left)).tolist())
    pairs={}
    for i,n in enumerate(source_names):
        key=motion_store.canonical(n);opposite=key.replace('Left','Right') if 'Left' in key else key.replace('Right','Left')
        other=src.get(opposite,i)
        if other==i and data['labels'][i]:
            label=str(data['labels'][i]);opposite=label.replace('Left','Right') if 'Left' in label else label.replace('Right','Left')
            if opposite in data['labels']:other=list(data['labels']).index(opposite)
        pairs[i]=other if mirror else i
    first=sample(data,start)[anchor].translation;last=sample(data,end)[anchor].translation
    travel=last-first;travel-=up*travel.dot(up)
    calibration_src={};calibration_dst={}
    if human:
        for side,sign in [('Left',1),('Right',-1)]:
            for index,matrices,calibration,basis in [(src,rest,calibration_src,source_basis),(dst,target_rest,calibration_dst,target_basis)]:
                hand=index.get(side+'Hand');hand_rotation=matrices[hand].to_3x3().col[1].rotation_difference(basis.col[0]*sign).to_matrix() if hand is not None else Matrix.Identity(3)
                for key,i in index.items():
                    if key in {side+part for part in ('Arm','ForeArm','Hand')}:
                        calibration[i]=matrices[i].to_3x3().col[1].rotation_difference(basis.col[0]*sign).to_matrix()@matrices[i].to_quaternion().to_matrix()
                    elif key.startswith(side+'Hand'):calibration[i]=hand_rotation@matrices[i].to_quaternion().to_matrix()
    old=rig.animation_data;previous=(old.action,old.action_slot,old.use_nla,old.action_blend_type,old.action_influence) if old else None
    old_modes={p.name:p.rotation_mode for p in rig.pose.bones}
    if previous:animation.remember_rotation_modes(rig,previous[0])
    old_pose=[p.matrix_basis.copy() for p in rig.pose.bones];old_frame=context.scene.frame_current;old_sub=context.scene.frame_subframe
    action=None
    try:
        action=bpy.data.actions.new(name);ad=rig.animation_data_create();ad.action=action;ad.use_nla=False;ad.action_blend_type='REPLACE';ad.action_influence=1.
        fps=context.scene.render.fps/context.scene.render.fps_base
        seconds=np.unique(np.r_[start,data['times'][(data['times']>start)&(data['times']<end)],np.linspace(start,end,max(2,math.ceil((end-start)*30)+1)),end]);previous_q={}
        samples={b.name:[] for b in ordered}
        for seconds_value in seconds:
            poses_source=sample(data,float(seconds_value));t=float((seconds_value-start)/(end-start));shift=travel*t if in_place else Vector()
            poses={}
            for bone in ordered:
                key=motion_store.canonical(bone.name);i=lookup.get(bone.name) if same else src.get(key)
                inherited=poses[bone.parent.name]@target[bone.parent.name].inverted()@target[bone.name] if bone.parent else target[bone.name].copy()
                if same and not mirror:
                    m=poses_source[i].copy();m.translation-=shift
                elif i is not None:
                    j=pairs[i];reference=calibration_src.get(j,rest[j].to_quaternion().to_matrix());delta=poses_source[j].to_quaternion().to_matrix()@reference.transposed()
                    if mirror:delta=reflection@delta@reflection
                    target_i=dst[key];target_reference=calibration_dst.get(target_i,target[bone.name].to_quaternion().to_matrix()) if human else target[bone.name].to_quaternion().to_matrix()
                    m=(conversion@delta@conversion.transposed()@target_reference).to_4x4();m.translation=inherited.translation
                    if i==anchor or (not bone.parent and not human):
                        displacement=poses_source[j].translation-rest[j].translation-shift
                        if mirror:displacement=reflection@displacement
                        m.translation=target[bone.name].translation+conversion@displacement*scale
                else:m=inherited
                poses[bone.name]=m
            if spacing:
                for side,sign in [('Left',1),('Right',-1)]:
                    arm=next((b for b in ordered if motion_store.canonical(b.name)==side+'Arm'),None)
                    if not arm:continue
                    pivot=poses[arm.name].translation
                    hips=next(b for b in ordered if motion_store.canonical(b.name)=='Hips')
                    body_delta=poses[hips.name].to_quaternion().to_matrix()@target[hips.name].to_quaternion().to_matrix().transposed()
                    turn=Matrix.Translation(pivot)@Matrix.Rotation(math.radians(-sign*spacing),4,body_delta@target_basis.col[1])@Matrix.Translation(-pivot)
                    for b in [arm,*arm.children_recursive]:poses[b.name]=turn@poses[b.name]
            for bone in ordered:
                basis=bone.convert_local_to_pose(poses[bone.name],target[bone.name],parent_matrix=poses[bone.parent.name] if bone.parent else Matrix.Identity(4),parent_matrix_local=target[bone.parent.name] if bone.parent else Matrix.Identity(4),invert=True)
                q=basis.to_quaternion().normalized();loc=basis.translation
                if not same and bone.parent and motion_store.canonical(bone.name)!='Hips':loc=Vector()
                if bone.name in previous_q and q.dot(previous_q[bone.name])<0:q.negate()
                previous_q[bone.name]=q.copy();samples[bone.name].append((1+(float(seconds_value)-start)/speed*fps,q.copy(),loc.copy()))
        for bone in ordered:
            p=rig.pose.bones[bone.name];p.rotation_mode='QUATERNION';p.matrix_basis.identity()
            for prop,size,which in [('rotation_quaternion',4,1),('location',3,2)]:
                for axis in range(size):
                    c=action.fcurve_ensure_for_datablock(rig,p.path_from_id(prop),index=axis,group_name=bone.name)
                    for row in samples[bone.name]:c.keyframe_points.insert(row[0],row[which][axis],options={'FAST'}).interpolation='LINEAR'
                    c.update()
        ad.action_slot=action.slots[0];action.use_frame_range=True;action.frame_start=1
        end_frame=1+(end-start)/speed*fps
        action.frame_end=round(end_frame) if abs(end_frame-round(end_frame))<1e-4 else end_frame
        action['lc_clip_loop']=bool(loop);action['lc_source_fps']=30;action['lc_motion_provider']='local_motion_library'
        action['lc_in_place']=bool(in_place);action['lc_library_controls']=str(dict(speed=speed,trim=[start,end],mirror=mirror,arm_spacing=spacing))
        if loop:
            seam=max(max((rows[-1][2]-rows[0][2]).length,1-abs(rows[-1][1].dot(rows[0][1]))) for rows in samples.values())
            period=(end-start)/speed*fps
            if round(period)>=2 and abs(period-round(period))<1e-5 and seam<1e-4:action['lc_loop_period_frames']=int(round(period))
        action.use_fake_user=True
        if hasattr(action,'lc_clip_owner'):action.lc_clip_owner=rig
        if previous and previous[0] and previous[0].library is None:previous[0].use_fake_user=True
        animation.remember_rotation_modes(rig,action)
        animation.attach_action(rig,{'action':action,'slot':ad.action_slot});context.scene.frame_set(1);context.view_layer.update()
        return action
    except Exception:
        if previous:
            ad.action,ad.action_slot,ad.use_nla,ad.action_blend_type,ad.action_influence=previous
        else:rig.animation_data_clear()
        for p,m in zip(rig.pose.bones,old_pose):p.rotation_mode=old_modes[p.name];p.matrix_basis=m
        context.scene.frame_set(old_frame,subframe=old_sub)
        if action:bpy.data.actions.remove(action)
        raise
