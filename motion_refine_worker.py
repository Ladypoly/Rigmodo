# SPDX-License-Identifier: GPL-3.0-or-later
"""Refine a snapshot in isolated Blender; never loads the artist's scene."""
import sys,json,time,importlib,traceback
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix,Quaternion,Vector
for stream in (sys.stdout,sys.stderr):
    if hasattr(stream,'reconfigure'):stream.reconfigure(encoding='utf-8',errors='backslashreplace')


def main(folder):
    root=Path(__file__).parent;sys.path.insert(0,str(root.parent));a=importlib.import_module(root.name);a.register();ctx=bpy.context
    progress=importlib.import_module(root.name+'.capture_progress');report=progress.Progress(folder);request=json.loads((folder/'request.json').read_text())
    if a.motion_jobs.sha(folder/'original.npz')!=request['input_sha256'] or a.motion_jobs.sha(folder/'source-rest.npz')!=request['source_rest_sha256']:raise ValueError('Refinement snapshot changed')
    original=a.motion_store.read_file(folder/'original.npz');rig=a.motion_assets.source_rig(ctx,a.motion_store.read_file(folder/'source-rest.npz'));rig.matrix_world=Matrix(request['source_world']);ctx.scene.unit_settings.scale_length=request['unit_scale'];ctx.scene.render.fps=30
    for key,value in request['source_properties'].items():rig[key]=value
    source=a.motion_retarget.apply(ctx,rig,original,'Original snapshot');source_slot=rig.animation_data.action_slot
    frames=request['frames'];segments=min(31,max(1,int((frames-1)/(request['spacing']*30))));indices=np.rint(np.linspace(0,frames-1,segments+1)).astype(int)
    if np.min(np.diff(indices))<15 or np.max(np.diff(indices))>60:raise ValueError('Cannot fit guide keys at 0.5–2 second intervals')
    samples=[];report('Sampling source guide poses')
    for index in indices:
        frame=1+float(index);ctx.scene.frame_set(int(frame),subframe=frame-int(frame));ctx.view_layer.update();samples.append((frame,{b.name:(b.location.copy(),b.rotation_quaternion.copy(),b.scale.copy()) for b in rig.pose.bones}))
    guide=a.motion_clips.new(ctx,rig,'Refinement guides')
    for frame,bones in samples:
        for name,(loc,q,scale) in bones.items():
            b=rig.pose.bones[name];b.rotation_mode='QUATERNION';b.location=loc;b.rotation_quaternion=q;b.scale=scale
            for prop in ('location','rotation_quaternion','scale'):b.keyframe_insert(prop,frame=frame)
    guide.frame_start=1;guide.frame_end=frames;ctx.scene.frame_set(1)
    model=a.motionbricks.prepare(ctx,rig,request['seed'],False,request['provider'],parent=folder);a.motionbricks.start(model)
    while True:
        state=a.skinning.poll(model)
        if state['status']!='running':break
        detail=progress.read(model);phase=detail.pop('phase','MotionBricks · Generating transitions');progress.write(folder,dict(detail,phase=phase));time.sleep(.25)
    if state['status']!='complete':raise ValueError(state.get('error','MotionBricks refinement failed'))
    native=json.loads((model/'request.json').read_text());keys=a.motion_jobs.check_inputs(model,native);positions,rotations=a.motion_data.load(model,native['frames'])
    generated=a.motion_apply.bake(ctx,rig,positions,rotations,False,label='Generated transitions',contacts=False,heading=True,start_frame=1,root_origin=(0,0,0));a.motion_keyframes.overlay(ctx,rig,keys)
    body_names={name for name in rig.pose.bones.keys() if a.skeleton.canonical_name(name) in a.motion_data.MAPPING}
    report('Smoothing generated body transitions')
    a.motion_finish.stabilize_capture(ctx,rig,generated,seconds=.1,bones=body_names)
    report('Preserving source travel, planted legs and fingers')
    original_curves={(c.data_path,c.array_index):c for c in a.motion_clips.slot_curves(source,source_slot)};slot=rig.animation_data.action_slot;curves={(c.data_path,c.array_index):c for c in a.motion_clips.slot_curves(generated,slot)}
    values={};weight=request['strength']
    for name in rig.pose.bones.keys():
        canonical=a.skeleton.canonical_name(name);body=canonical in a.motion_data.MAPPING and canonical!='Hips';prefix=rig.pose.bones[name].path_from_id();rows=[]
        for index in range(frames):
            frame=1+index
            def channels(source,prop,count):return [source[(prefix+'.'+prop,j)].evaluate(frame) for j in range(count)]
            q0=Quaternion(channels(original_curves,'rotation_quaternion',4)).normalized();q1=Quaternion(channels(curves,'rotation_quaternion',4)).normalized()
            blend=weight if body else 0.
            for side in ('Left','Right'):
                if canonical not in {side+part for part in ('UpLeg','Leg','Foot','ToeBase')}:continue
                contacts=[e for e in request['contacts'] if e['side']==side and e['start']-1e-6<=index/30<=e['end']+1e-6]
                if contacts and contacts[-1]['mode']!='AIR':
                    e=contacts[-1];blend*=1-a.motion_contacts.contact_weight(index,round(e['start']*30),round(e['end']*30),frames)
            q=q0.slerp(q1,blend);loc=Vector(channels(original_curves,'location',3))
            rows.append((frame,q,loc))
        values[name]=rows
    for name,rows in values.items():
        prefix=rig.pose.bones[name].path_from_id()
        for prop,size,value in (('rotation_quaternion',4,1),('location',3,2)):
            for axis in range(size):
                curve=curves[(prefix+'.'+prop,axis)];curve.keyframe_points.clear()
                for row in rows:curve.keyframe_points.insert(row[0],row[value][axis],options={'FAST'}).interpolation='LINEAR'
                curve.update()
    data=a.motion_store.capture(ctx,rig,generated,slot)
    if 'contact_probabilities' in original:data['contact_probabilities']=np.column_stack([np.interp(data['times'],original['times'],original['contact_probabilities'][:,i]) for i in range(2)])
    if 'provenance' in original:data['provenance']=original['provenance']
    a.motion_store.validate(data);np.savez_compressed(folder/'output.npz',**data)
    a.motion_store.atomic(folder/'results.json',dict(provider='MotionBricks',strength=weight,frames=frames,guide_frames=indices.tolist(),source_fingers_preserved=True,temporal_filter_seconds=.1,source_trajectory_preserved=True,source_support_preserved=True,physics_simulation=False));a.motion_store.atomic(folder/'status.json',dict(schema_version=1,status='complete'))


if __name__=='__main__':
    folder=Path(sys.argv[sys.argv.index('--')+1])
    try:main(folder)
    except Exception as exc:
        traceback.print_exc();(folder/'status.json').write_text(json.dumps(dict(schema_version=1,status='failed',error=str(exc))));sys.exit(1)
