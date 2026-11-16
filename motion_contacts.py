# SPDX-License-Identifier: GPL-3.0-or-later
"""Sole-based contact intervals and bounded two-bone correction on a new Action."""
import json,math
import numpy as np
import bpy
from bpy.types import Operator
from mathutils import Matrix,Vector
from . import motion_store,motion_retarget,motion_jobs,kinematics,rig_mapping,animation


def intervals(mask):
    result=[];start=None
    for i,active in enumerate([*map(bool,mask),False]):
        if active and start is None:start=i
        if not active and start is not None:result.append((start,i-1));start=None
    return result


def soles(context,rig,roles):
    saved=json.loads(rig.get('lc_sole_markers','{}'));result={};world=rig.matrix_world
    for side in ('Left','Right'):
        foot=rig.data.bones[roles[side+'Foot']];toe=rig.data.bones.get(roles.get(side+'ToeBase',''))
        stored=saved.get(side)
        if stored and stored.get('bone')==foot.name and np.asarray(stored.get('points')).shape==(2,3):
            points=np.asarray(stored['points'],dtype=float)
            if np.isfinite(points).all():result[side]=[Vector(p) for p in points];continue
        candidates=[];group_names={foot.name,*[b.name for b in foot.children_recursive]}
        for obj in motion_jobs.character_meshes(context,rig):
            if not any(m.type=='ARMATURE' and m.object==rig for m in obj.modifiers):continue
            indices={g.index for g in obj.vertex_groups if g.name in group_names}
            candidates.extend(obj.matrix_world@v.co for v in obj.data.vertices if sum(g.weight for g in v.groups if g.group in indices)>.4)
        rest=world@foot.matrix_local;inverse=rest.inverted()
        if len(candidates)>=6:
            points=np.array(candidates);threshold=np.quantile(points[:,2],.08);points=points[points[:,2]<=threshold+.003]
            direction=(world@(toe.tail_local if toe else foot.tail_local)-rest.translation);direction.z=0
            if direction.length<1e-6:direction=Vector((0,-1,0))
            values=points@np.array(direction.normalized());order=np.argsort(values);k=max(1,len(order)//4)
            markers=[Vector(points[order[:k]].mean(0)),Vector(points[order[-k:]].mean(0))]
        else:
            a=rest.translation.copy();b=world@(toe.tail_local if toe else foot.tail_local)
            z=min((world@foot.tail_local).z,b.z);a.z=z;b.z=z;markers=[a,b]
        result[side]=[inverse@p for p in markers]
    return result


def floor_drift(samples,probabilities,times,length,overrides):
    """Estimate slow vertical capture drift only during confident ground support."""
    if probabilities is None:return np.zeros(len(times))
    heights=np.column_stack([samples[side][:,:,2].min(1) for side in ('Left','Right')])
    lowest=heights.min(1);support=(probabilities>.75)&(heights<=lowest[:,None]+length*.035)
    for edit in overrides:
        if edit['mode']=='AIR':support[(times>=edit['start'])&(times<=edit['end']),0 if edit['side']=='Left' else 1]=False
    known=np.flatnonzero(support.any(1))
    if len(known)<3:return np.zeros(len(times))
    # Interpolate across flight rather than pulling an airborne performer to the floor.
    reference=float(np.quantile(lowest[known],.08));values=np.interp(times,times[known],lowest[known])-reference
    grid=np.arange(times[0],times[-1]+1/60,1/30);uniform=np.interp(grid,times,values)
    kernel=np.exp(-np.arange(-9,10,dtype=float)**2/18);kernel/=kernel.sum()
    smooth=np.convolve(np.pad(uniform,(9,9),mode='edge'),kernel,mode='valid')
    return np.clip(np.interp(times,grid,smooth),-length*.45,length*.45)


def solve(context,rig,data,ground=0.,in_place=False,overrides=()):
    if not math.isfinite(ground):raise ValueError('Ground height must be finite')
    role_names=rig_mapping.names(rig);roles={r:b.name for r,b in zip(role_names,rig.data.bones)}
    missing=set(['Hips',*[s+p for s in ('Left','Right') for p in ('UpLeg','Leg','Foot')]])-roles.keys()
    if missing:raise ValueError('Map hips and both leg chains before grounding: '+', '.join(sorted(missing)))
    index={str(n):i for i,n in enumerate(data['names'])};world=rig.matrix_world.copy();inverse=world.inverted();markers=soles(context,rig,roles)
    poses=[[world@Matrix(m.tolist()) for m in row] for row in data['poses']];times=data['times'].astype(float)
    samples={s:np.array([[m[index[roles[s+'Foot']]]@p for p in markers[s]] for m in poses]) for s in markers}
    lengths={s:sum((world@rig.data.bones[roles[s+p]].tail_local-world@rig.data.bones[roles[s+p]].head_local).length for p in ('UpLeg','Leg')) for s in markers}
    reference=min(float(np.quantile(v[:,:,2].min(1),.08)) for v in samples.values())
    # One constant floor alignment retains jumps; never lower each airborne frame.
    shift=ground-reference
    if abs(shift)>max(lengths.values())*.6:raise ValueError('Estimated floor is too far away; review sole markers and ground height')
    drift=floor_drift(samples,data.get('contact_probabilities'),times,max(lengths.values()),overrides)
    masks={};tracks={};count=0
    for side,points in samples.items():
        heights=points[:,:,2].min(1)-reference-drift
        center=points.mean(1);velocity=np.linalg.norm(np.gradient(center[:,:2],times,axis=0),axis=1)
        mask=(heights<lengths[side]*.045)&((velocity<lengths[side]*.55)|in_place)
        if 'contact_probabilities' in data:
            probability=data['contact_probabilities'][:,0 if side=='Left' else 1]
            mask=(heights<lengths[side]*.08)&(((probability>.6)&((velocity<lengths[side]*.8)|in_place))|(mask&(probability>.2)))
        for lo,hi in intervals(~mask):
            if lo>0 and hi+1<len(mask) and times[hi]-times[lo]<.05:mask[lo:hi+1]=True
        for lo,hi in intervals(mask):
            if times[hi]-times[lo]<.045:mask[lo:hi+1]=False
        for edit in overrides:
            if edit['side']!=side:continue
            active=(times>=edit['start'])&(times<=edit['end']);mask[active]=edit['mode']!='AIR'
        masks[side]=mask;tracks[side]=intervals(mask)
    root_indices={i for i,n in enumerate(data['names']) if str(n)==roles.get('Root') and not rig.data.bones[str(n)].use_deform}
    for f,row in enumerate(poses):
        for i,m in enumerate(row):
            if i not in root_indices:m.translation.z+=shift-drift[f]
    stats=dict(contact_frames=0,unreachable_frames=0,ground_alignment_m=shift,maximum_floor_drift_m=float(np.abs(drift).max()),contacts={s:len(v) for s,v in tracks.items()})
    anchors={};report=[]
    for f,row in enumerate(poses):
        goals={};lowering=0.
        for side in masks:
            if not masks[side][f]:anchors.pop(side,None);continue
            upper,lower,foot=(rig.data.bones[roles[side+p]] for p in ('UpLeg','Leg','Foot'))
            if lower.parent!=upper or foot.parent!=lower:raise ValueError('Foot correction needs direct upper leg, lower leg and foot chains')
            ids=[index[b.name] for b in (upper,lower,foot)];hip,knee,end=[row[i].translation.copy() for i in ids]
            points=[row[ids[2]]@p for p in markers[side]];lowest=min(points,key=lambda p:p.z)
            lo,hi=next((a,b) for a,b in tracks[side] if a<=f<=b);strength=min(1.,(f-lo+1)/3,(hi-f+1)/3)
            if side not in anchors:
                candidates=np.asarray([[pose[index[foot.name]]@p for p in markers[side]] for pose in poses[lo:hi+1]])
                point=int(np.argmin(np.var(candidates[:,:,:2],axis=0).sum(1)));chosen=points[point]
                anchors[side]=(point,Vector((chosen.x,chosen.y,ground)))
            point,anchor=anchors[side]
            edits=[e for e in overrides if e['side']==side and e['start']<=times[f]<=e['end']]
            sliding=(edits[-1]['mode']=='SLIDE') if edits else in_place
            correction=Vector((0,0,ground-lowest.z)) if sliding else anchor-points[point]
            goal=end+correction*strength
            horizontal=(Vector((hip.x,hip.y,0))-Vector((goal.x,goal.y,0))).length;length=lengths[side]
            if horizontal<length:lowering=min(lowering,goal.z+math.sqrt(max(0,(length-1e-5)**2-horizontal**2))-hip.z)
            goals[side]=(ids,goal)
        lowering=max(lowering,-max(lengths.values())*.08)
        if lowering<0:
            for i,m in enumerate(row):
                if i not in root_indices:m.translation.z+=lowering
        for side,(ids,goal) in goals.items():
            hip,knee,end=[row[i].translation.copy() for i in ids]
            pole=world.to_quaternion()@Vector((0,-1,0))
            if set(rig_mapping.CORE)<=set(roles):
                rest=[b.matrix_local for b in rig.data.bones];role_index={r:i for i,r in enumerate(role_names)}
                pole=-(world.to_quaternion()@motion_retarget.body_frame(rest,role_index).col[1])
            new_knee,new_end,clamped=kinematics.two_bone(hip,knee,end,goal,pole)
            stats['contact_frames']+=1;stats['unreachable_frames']+=int(clamped)
            for i,old,new,position in [(ids[0],knee-hip,new_knee-hip,hip),(ids[1],end-knee,new_end-new_knee,new_knee)]:
                m=(old.rotation_difference(new).to_matrix()@row[i].to_quaternion().to_matrix()).to_4x4()@Matrix.Diagonal((*row[i].to_scale(),1.));m.translation=position;row[i]=m
            old=row[ids[2]].copy();row[ids[2]].translation=new_end;delta=row[ids[2]]@old.inverted()
            for child in rig.data.bones[roles[side+'Foot']].children_recursive:row[index[child.name]]=delta@row[index[child.name]]
    output=dict(data);output['poses']=np.array([[inverse@m for m in row] for row in poses],dtype=np.float32)
    stats['intervals']=[dict(side=s,start=float(times[a]),end=float(times[b]),mode='SLIDE' if in_place else 'PLANT') for s,segments in tracks.items() for a,b in segments]
    return output,stats


def contact_overrides(action,duration):
    data=json.loads(action.get('lc_contact_overrides','[]'))
    if not isinstance(data,list) or len(data)>512:raise ValueError('Too many contact intervals')
    for e in data:
        if not isinstance(e,dict) or e.get('side') not in {'Left','Right'} or e.get('mode') not in {'PLANT','SLIDE','AIR'} or any(not isinstance(e.get(k),(int,float)) or not math.isfinite(e[k]) for k in ('start','end')) or not 0<=e['start']<e['end']<=duration+.001:
            raise ValueError('Contact intervals must fit inside this animation')
    return data


def correct(context,rig,action,ground=0.,loop=False,contact_data=None):
    source=getattr(action,'lc_contact_source',None) or action
    slot=next((s for s in source.slots if s.identifier==rig.animation_data.action_slot.identifier),source.slots[0])
    data=motion_store.capture(context,rig,source,slot)
    if contact_data is not None and 'contact_probabilities' in contact_data:
        data['contact_probabilities']=np.column_stack([np.interp(data['times'],contact_data['times'],contact_data['contact_probabilities'][:,i]) for i in range(2)])
    overrides=contact_overrides(action,float(data['times'][-1]))
    result,stats=solve(context,rig,data,ground,bool(action.get('lc_in_place')),overrides)
    new=motion_retarget.apply(context,rig,result,source.name+' · Grounded',loop=loop)
    for key in ('lc_library_source','lc_library_license','lc_in_place','lc_motion_prompt','lc_contact_overrides','lc_contact_samples','lc_capture_job','lc_capture_video','lc_capture_offset_seconds','lc_capture_provenance'):
        if key in action:new[key]=action[key]
    new['lc_contact_report']=json.dumps(stats);new['lc_ground_height']=ground;new.lc_contact_source=source
    return new


class LC_OT_ground_motion(Operator):
    bl_idname='local_character.ground_motion';bl_label='Correct Foot Contacts';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context)
            if not rig.animation_data or not rig.animation_data.action:raise ValueError('Choose an animation first')
            s=context.scene.lc_settings;action=rig.animation_data.action
            if action.get('lc_clip_loop'):
                from . import animation_transfer,motion_clips
                data,report=animation_transfer.periodic_contacts(context,rig,action,s.ground_height)
                new=motion_retarget.apply(context,rig,data,action.name+' · Contacts',loop=True)
                new['lc_contact_report']=json.dumps(report);new['lc_loop_period_frames']=action.get('lc_loop_period_frames',round(action.frame_end-action.frame_start))
                new['lc_contact_overrides']=action.get('lc_contact_overrides','[]');new.lc_contact_source=action.lc_contact_source or action
                motion_clips.select(context,rig,new,new.slots[0])
            else:
                new=correct(context,rig,action,s.ground_height)
                from . import motion_clips
                motion_clips.select(context,rig,new,new.slots[0])
        except (ValueError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_set_sole(Operator):
    bl_idname='local_character.set_sole_marker';bl_label='Set Sole at Cursor';bl_options={'REGISTER','UNDO'}
    point:bpy.props.EnumProperty(items=[('HEEL','Heel',''),('BALL','Forefoot','')])
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);side=context.scene.lc_settings.contact_side;roles={r:b.name for r,b in zip(rig_mapping.names(rig),rig.data.bones)}
            foot=rig.pose.bones[roles[side+'Foot']];points=soles(context,rig,roles)[side]
            points[0 if self.point=='HEEL' else 1]=(rig.matrix_world@foot.matrix).inverted()@context.scene.cursor.location
            data=json.loads(rig.get('lc_sole_markers','{}'));data[side]=dict(bone=foot.name,points=[list(p) for p in points]);rig['lc_sole_markers']=json.dumps(data)
        except (ValueError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_contact_interval(Operator):
    bl_idname='local_character.mark_contact_interval';bl_label='Apply Contact Interval';bl_options={'UNDO'}
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);s=context.scene.lc_settings;action=rig.animation_data.action
            if not action or s.contact_end<=s.contact_start:raise ValueError('Choose an animation and increasing interval in seconds')
            if action.library or action.override_library:raise ValueError('Make a local animation copy first')
            duration=(action.frame_end-action.frame_start)/(context.scene.render.fps/context.scene.render.fps_base)
            if s.contact_end>duration+.001:raise ValueError('The contact interval extends past the clip')
            data=contact_overrides(action,duration);data.append(dict(side=s.contact_side,start=s.contact_start,end=s.contact_end,mode=s.contact_mode));action['lc_contact_overrides']=json.dumps(data)
        except (ValueError,AttributeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_clear_contacts(Operator):
    bl_idname='local_character.clear_contact_intervals';bl_label='Reset Contact Overrides';bl_options={'UNDO'}
    def execute(self,context):
        try:
            action=motion_jobs.selected_rig(context).animation_data.action
            if action.library or action.override_library:raise ValueError('Make a local animation copy first')
            action['lc_contact_overrides']='[]'
        except (ValueError,AttributeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


CLASSES=(LC_OT_ground_motion,LC_OT_set_sole,LC_OT_contact_interval,LC_OT_clear_contacts)
