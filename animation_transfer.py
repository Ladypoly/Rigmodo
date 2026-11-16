# SPDX-License-Identifier: GPL-3.0-or-later
"""A single application path for imported, captured, and library motion."""
import json,math,subprocess,tempfile,sys
from pathlib import Path
import bpy
import numpy as np
from bpy.types import Operator
from mathutils import Matrix
from . import motion_store,motion_retarget,motion_contacts,motion_finish,motion_jobs,motion_clips,rig_mapping,animation


def loop_diagnostics(context,rig,action):
    data=motion_store.capture(context,rig,action,rig.animation_data.action_slot);fps=context.scene.render.fps/context.scene.render.fps_base;duration=float(data['times'][-1]);step=1/fps
    rows=[motion_retarget.sample(data,t) for t in (0,step,duration-step,duration)]
    roles=rig_mapping.names(rig);root=next((i for i,r in enumerate(roles) if r=='Root'),next(i for i,p in enumerate(data['parents']) if p<0))
    delta=rows[-1][root]@rows[0][root].inverted() if not action.get('lc_in_place') else Matrix.Identity(4)
    report=dict(max_position_error_m=0.,max_rotation_error_rad=0.,max_linear_velocity_error_m_s=0.,max_angular_velocity_error_rad_s=0.)
    for first,next_pose,previous,last in zip(*rows):
        target=delta@first
        report['max_position_error_m']=max(report['max_position_error_m'],(last.translation-target.translation).length)
        report['max_rotation_error_rad']=max(report['max_rotation_error_rad'],last.to_quaternion().rotation_difference(target.to_quaternion()).angle)
        velocity=delta.to_quaternion()@(next_pose.translation-first.translation)*fps
        report['max_linear_velocity_error_m_s']=max(report['max_linear_velocity_error_m_s'],((last.translation-previous.translation)*fps-velocity).length)
        a=first.to_quaternion().rotation_difference(next_pose.to_quaternion()).to_exponential_map()*fps;b=previous.to_quaternion().rotation_difference(last.to_quaternion()).to_exponential_map()*fps
        report['max_angular_velocity_error_rad_s']=max(report['max_angular_velocity_error_rad_s'],(a-b).length)
    return report


def finish(context,rig,data,name,metadata=None,controls=None):
    if 'provenance' in data:
        allowed={'lc_contact_overrides','lc_capture_provenance','lc_capture_video','lc_capture_offset_seconds','lc_motion_prompt','lc_library_source','lc_library_license'}
        inherited={k:v for k,v in json.loads(str(data['provenance'][0])).items() if k in allowed};inherited.update(metadata or {});metadata=inherited
    s=context.scene.lc_settings;old=rig.animation_data
    previous=(old.action,old.action_slot,old.use_nla,old.action_blend_type,old.action_influence) if old else None
    before=[p.matrix_basis.copy() for p in rig.pose.bones];modes={p.name:p.rotation_mode for p in rig.pose.bones};frame=context.scene.frame_current;sub=context.scene.frame_subframe
    created=[]
    try:
        action=motion_retarget.apply(context,rig,data,name,in_place=s.motion_in_place,loop=False,**(controls or {}));created.append(action)
        if metadata:
            for key,value in metadata.items():
                if isinstance(value,(str,int,float,bool)):action[key]=value
        contact_data=data
        if controls:
            contact_data=dict(data,times=(data['times']-controls.get('start',0))/controls.get('speed',1))
        human=set(rig_mapping.CORE)<=set(rig_mapping.names(rig))
        if s.create_loop:
            period=round(action.frame_end-action.frame_start)
            if period<4:raise ValueError('A loop needs at least four scene frames')
            action.frame_end=action.frame_start+period
            action=motion_finish.loop(context,rig,min(s.motion_loop_blend,max(2,period//4)));created.append(action)
            action['lc_loop_period_frames']=period
        if s.motion_contacts and human:
            if s.create_loop:
                corrected,report=periodic_contacts(context,rig,action,s.ground_height,contact_data)
                raw=action;action=motion_retarget.apply(context,rig,corrected,name+' · Loop',loop=True);created.append(action)
                for key in ('lc_library_source','lc_library_license','lc_in_place','lc_motion_prompt'):
                    if key in raw:action[key]=raw[key]
                action['lc_loop_period_frames']=period;action['lc_loop_finished']=True
                action['lc_contact_report']=json.dumps(report);action.lc_contact_source=created[0]
            else:
                action=motion_contacts.correct(context,rig,action,s.ground_height,contact_data=contact_data);created.append(action)
        if metadata:
            for key,value in metadata.items():
                if isinstance(value,(str,int,float,bool)):action[key]=value
        if 'contact_probabilities' in contact_data:
            action['lc_contact_samples']=json.dumps(dict(times=contact_data['times'].tolist(),probabilities=contact_data['contact_probabilities'].tolist()))
        action['lc_clip_loop']=bool(s.create_loop);action.lc_clip_owner=rig
        action.name=name+(' · Loop' if s.create_loop else '')
        for item in created:
            if item!=action:item['lc_internal_variant']=True
        if len(created)>1 and not action.lc_contact_source:action.lc_contact_source=created[0]
        motion_clips.select(context,rig,action,action.slots[0])
        if s.create_loop:action['lc_loop_report']=json.dumps(loop_diagnostics(context,rig,action))
        s.motion_status='Animation ready'+(' · inspect flagged contacts' if json.loads(action.get('lc_contact_report','{}')).get('unreachable_frames',0) else '')
        for item in created:
            if item!=action and item!=action.lc_contact_source and item.users-int(item.use_fake_user)==0:bpy.data.actions.remove(item)
        return action
    except Exception:
        if previous:
            ad=rig.animation_data_create();ad.action,ad.action_slot,ad.use_nla,ad.action_blend_type,ad.action_influence=previous
        else:rig.animation_data_clear()
        for p,m in zip(rig.pose.bones,before):p.rotation_mode=modes[p.name];p.matrix_basis=m
        context.scene.frame_set(frame,subframe=sub)
        for action in reversed(created):
            if action.name in bpy.data.actions:bpy.data.actions.remove(action)
        raise


def periodic_contacts(context,rig,action,ground,contact_data=None):
    data=motion_store.capture(context,rig,action,rig.animation_data.action_slot);duration=float(data['times'][-1])
    if duration>60:raise ValueError('Trim looping clips to 60 seconds before contact finishing')
    roles=rig_mapping.names(rig);root=next((i for i,r in enumerate(roles) if r=='Root'),next(i for i,p in enumerate(data['parents']) if p<0))
    start=Matrix(data['poses'][0,root].tolist());end=Matrix(data['poses'][-1,root].tolist());delta=end@start.inverted()
    count=len(data['times'])-1;poses=[];times=[]
    for cycle in range(3):
        transform=delta@delta if cycle==2 else delta if cycle==1 else Matrix.Identity(4)
        for i in range(count):poses.append([transform@Matrix(m.tolist()) for m in data['poses'][i]]);times.append(cycle*duration+float(data['times'][i]))
    poses.append([delta@delta@delta@Matrix(m.tolist()) for m in data['poses'][0]]);times.append(3*duration)
    repeated=dict(data,poses=np.asarray(poses,dtype=np.float32),times=np.asarray(times,dtype=np.float32))
    if contact_data is not None and 'contact_probabilities' in contact_data:
        probabilities=np.column_stack([np.interp(data['times'],contact_data['times'],contact_data['contact_probabilities'][:,i]) for i in range(2)])
        repeated['contact_probabilities']=np.concatenate([probabilities[:-1]]*3+[probabilities[:1]])
    edits=motion_contacts.contact_overrides(action,duration)
    edits=[dict(e,start=e['start']+cycle*duration,end=e['end']+cycle*duration) for cycle in range(3) for e in edits]
    clean,report=motion_contacts.solve(context,rig,repeated,ground,bool(action.get('lc_in_place')),edits)
    inverse=delta.inverted();result=dict(data)
    result['poses']=np.array([[inverse@Matrix(m.tolist()) for m in row] for row in clean['poses'][count:2*count+1]],dtype=np.float32)
    report['periodic_three_cycle_solve']=True
    return result,report


class LC_OT_retarget_animation(Operator):
    bl_idname='local_character.retarget_animation';bl_label='Retarget Animation';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            s=context.scene.lc_settings;target=motion_jobs.selected_rig(context)
            if s.animation_file:
                from . import video_motion
                return video_motion.start(context,kind='animation')
            source=s.source_rig
            if not source or not s.source_action:raise ValueError('Choose a source armature and Action, or an animation file')
            action=s.source_action;slot=next((slot for candidate,slot in motion_clips.available(source) if candidate==action),None)
            if not slot:raise ValueError('This Action has no bone channels matching the source rig')
            data=motion_store.capture(context,source,action,slot)
            finish(context,target,data,action.name+' · Retargeted',dict(lc_library_source=action.get('lc_library_source','User animation'),lc_library_license=action.get('lc_library_license','User-provided')))
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


def record_options(context,folder):
    state=context.scene.lc_settings
    if not state.ui_motion_pipeline:return
    from . import configuration
    folder=Path(folder);request=json.loads((folder/'request.json').read_text())
    if state.create_loop:validate_key_loop(folder,request,state.motion_in_place)
    request['ui_pipeline']=dict(motion_in_place=state.motion_in_place,create_loop=state.create_loop,motion_contacts=state.motion_contacts,ground_height=state.ground_height,keep_copies=configuration.settings(context).keep_motion_copies)
    motion_store.atomic(folder/'request.json',request)
    if (folder/'request.sha256').exists():(folder/'request.sha256').write_text(motion_jobs.sha(folder/'request.json'),encoding='utf-8')


def validate_key_loop(folder,request,in_place):
    if request.get('keyframe_inputs'):
        from mathutils import Quaternion,Vector
        keys=motion_jobs.check_inputs(folder,request);period=(keys['frames']-1)*keys['scene_fps']/30
        if abs(period-round(period))>1e-4:raise ValueError('For a keyed loop, choose a duration aligned to whole scene frames')
        first,last=keys['poses'][0],keys['poses'][-1]
        if abs(first['frame']-keys['start_frame'])<1e-4 and abs(last['frame']-keys['start_frame']-period)<1e-4:
            for name,a in first['basis'].items():
                if name=='Root' and not in_place:continue
                b=last['basis'][name]
                if (Vector(a['location'])-Vector(b['location'])).length>.005 or abs(Quaternion(a['rotation']).dot(Quaternion(b['rotation'])))<.999 or (Vector(a['scale'])-Vector(b['scale'])).length>.001:raise ValueError('First and last pose keys conflict with Loop. Match the endpoint poses or create a one-shot')


def adopt_generated(context,folder,request,collection,rig,meshes,action):
    options=request.get('ui_pipeline')
    if not options or options.get('keep_copies'):return False
    source=bpy.data.objects.get(request['rig'])
    if not source:raise ValueError('The source character was removed')
    from . import motion_keyframes,character_context
    keys=motion_jobs.check_inputs(Path(folder),request) if request.get('keyframe_inputs') else None
    data=motion_store.capture(context,rig,action,rig.animation_data.action_slot)
    s=context.scene.lc_settings;old={k:getattr(s,k) for k in ('motion_in_place','create_loop','motion_contacts','ground_height')}
    try:
        for key,value in options.items():
            if key in old:setattr(s,key,value)
        accepted=finish(context,source,data,action.name,dict(lc_motion_provider=action.get('lc_motion_provider','Generated motion'),lc_motion_prompt=request.get('prompt','')))
        if keys:
            offset=keys['start_frame']-accepted.frame_start
            for curve in motion_clips.slot_curves(accepted,source.animation_data.action_slot):
                for point in curve.keyframe_points:point.co.x+=offset;point.handle_left.x+=offset;point.handle_right.x+=offset
                curve.update()
            accepted.frame_start,accepted.frame_end=accepted.frame_start+offset,accepted.frame_end+offset
            motion_keyframes.overlay(context,source,keys)
            if accepted.get('lc_clip_loop'):accepted['lc_loop_report']=json.dumps(loop_diagnostics(context,source,accepted))
            motion_clips.select(context,source,accepted,source.animation_data.action_slot)
    finally:
        for key,value in old.items():setattr(s,key,value)
    owned_data=[o.data for o in [*meshes,rig]]
    for obj in [*meshes,rig]:bpy.data.objects.remove(obj,do_unlink=True)
    for item in owned_data:
        if item.users==0:(bpy.data.meshes if isinstance(item,bpy.types.Mesh) else bpy.data.armatures).remove(item)
    if not collection.objects:bpy.data.collections.remove(collection)
    if action.users-int(action.use_fake_user)==0:bpy.data.actions.remove(action)
    character_meshes=[bpy.data.objects[m['name']] for m in request.get('meshes',[]) if m['name'] in bpy.data.objects]
    character_context.pin(context,source,character_meshes)
    s.include_action=True;s.motion_status='Animation ready on '+source.name
    return True


class LC_OT_make_loop(Operator):
    bl_idname='local_character.make_animation_loop';bl_label='Make Loop Copy';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        s=context.scene.lc_settings;old=s.create_loop
        try:
            rig=motion_jobs.selected_rig(context);action=rig.animation_data.action
            data=motion_store.capture(context,rig,action,rig.animation_data.action_slot)
            s.create_loop=True;finish(context,rig,data,action.name,dict(lc_library_source=action.get('lc_library_source','User animation'),lc_library_license=action.get('lc_library_license','User-provided')))
        except (ValueError,RuntimeError,AttributeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        finally:s.create_loop=old
        return {'FINISHED'}


CLASSES=(LC_OT_retarget_animation,LC_OT_make_loop)
