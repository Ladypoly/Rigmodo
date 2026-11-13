# SPDX-License-Identifier: GPL-3.0-or-later
"""Official SOMA ONNX contract, independent of NVIDIA's viewer/physics runtime."""
# Numeric encoding and endpoint correction follow NVlabs/motionbricks (Apache-2.0).
import hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import model_storage
import numpy as np
from scipy.spatial.transform import Rotation,Slerp
import motion_data as data

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def yaw(angle):return Rotation.from_rotvec([0,angle,0]).as_matrix()

def heading(positions):
    across=positions[...,26,:]-positions[...,22,:]
    return np.arctan2(across[...,2],-across[...,0])

def encode(root,global_rot):
    positions=np.empty((8,30,3))
    for j,p in enumerate(data.PARENTS):positions[:,j]=root if p<0 else positions[:,p]+global_rot[:,p]@data.OFFSETS[j]
    angle=float(heading(positions)[3])-np.pi/2;alignment=yaw(angle);origin=root[3]*[1,0,1]
    pos=(positions-origin)@alignment;rot=alignment.T@global_rot
    roots=pos[:,0];angles=heading(pos)
    next_frame=np.array([1,2,3,3,5,6,7,7]);delta=np.arctan2(np.sin(angles[next_frame]-angles),np.cos(angles[next_frame]-angles))*30
    global_values=np.column_stack([roots,np.cos(angles),np.sin(angles)]).astype(np.float32)
    local_values=np.column_stack([delta,(roots[next_frame,0]-roots[:,0])*30,(roots[next_frame,2]-roots[:,2])*30,roots[:,1]]).astype(np.float32)
    relative=pos[:,1:]-roots[:,None]*[1,0,1]
    poses=np.concatenate([relative.reshape(8,87),rot[:,:,:,:2].transpose(0,1,3,2).reshape(8,180)],axis=1).astype(np.float32)
    mask=np.array([[1,1,1,1,1,0,0,0]],dtype=np.int32)
    return dict(global_root_values=global_values[None],local_root_values=local_values[None],local_poses=poses[None],
        has_global_root_values=mask.copy(),has_local_root_values=np.array([[1,1,1,0,0,0,0,0]],np.int32),has_local_poses=mask.copy(),
        allowed_pred_num_tokens=np.ones((1,11),np.int32)),alignment,origin

def decode(features,alignment,origin):
    if features.ndim!=2 or features.shape[1]!=366 or not np.isfinite(features).all():raise ValueError('Invalid MotionBricks output')
    raw=features[:,92:272].reshape(-1,30,6)
    x=raw[:,:,:3];z=np.cross(x,raw[:,:,3:]);nx=np.linalg.norm(x,axis=-1,keepdims=True);nz=np.linalg.norm(z,axis=-1,keepdims=True)
    if np.any(nx<1e-7) or np.any(nz<1e-7):raise ValueError('Degenerate MotionBricks rotations')
    x=x/nx;z=z/nz;global_rot=alignment@np.stack([x,np.cross(z,x),z],axis=-1)
    local=global_rot.copy()
    for j,p in enumerate(data.PARENTS):
        if p>=0:local[:,j]=global_rot[:,p].swapaxes(-1,-2)@global_rot[:,j]
    return features[:,:3]@alignment.T+origin,Rotation.from_matrix(local.reshape(-1,3,3)).as_quat().reshape(-1,30,4)

def local_rotations(global_rot):
    local=np.asarray(global_rot).copy()
    for j,p in enumerate(data.PARENTS):
        if p>=0:local[j]=global_rot[p].T@global_rot[j]
    return Rotation.from_matrix(local).as_quat()

def correct_and_retime(root,quats,start,end,length):
    first=local_rotations(np.asarray(start['global_rotations']));last=local_rotations(np.asarray(end['global_rotations']))
    weights=np.linspace(0,1,len(root));root=root+(np.asarray(start['root'])-root[0])*(1-weights[:,None])+(np.asarray(end['root'])-root[-1])*weights[:,None]
    result=np.empty((length,30,4));target=np.linspace(0,1,length)
    for j in range(30):
        r=Rotation.from_quat(quats[:,j]);d0=r[0].inv()*Rotation.from_quat(first[j]);d1=r[-1].inv()*Rotation.from_quat(last[j])
        corrected=r*Rotation.from_rotvec((1-weights[:,None])*d0.as_rotvec())*Rotation.from_rotvec(weights[:,None]*d1.as_rotvec())
        result[:,j]=Slerp(weights,corrected)(target).as_quat()
    root=np.column_stack([np.interp(target,weights,root[:,i]) for i in range(3)])
    return root,result

def run(folder):
    folder=Path(folder);request=json.loads((folder/'request.json').read_text());provider=Path(request['provider_cache']);lock_path=Path(__file__).with_name('motionbricks-lock.json');lock=json.loads(lock_path.read_text())
    if sha(folder/'request.json')!=(folder/'request.sha256').read_text():raise ValueError('MotionBricks request changed')
    record=json.loads((provider/'installation.json').read_text())
    if not model_storage.lock_matches(record,lock_path):raise ValueError('Reinstall the pinned MotionBricks provider')
    for f in lock['files']:
        if sha(model_storage.resolve(provider/f['path']))!=f['sha256']:raise ValueError('MotionBricks provider file changed: '+f['path'])
    if json.loads(model_storage.resolve(provider/'soma_n1.json').read_text())['joint_names']!=data.NAMES:raise ValueError('Wrong SOMA joint order')
    for f,h in request['keyframe_inputs'].items():
        if sha(folder/f)!=h:raise ValueError('Motion keyframes changed')
    keys=json.loads((folder/'keyframes.json').read_text());poses=sorted(keys['poses'],key=lambda p:p['index'])
    if len(poses)<2 or poses[0]['index']!=0:raise ValueError('MotionBricks needs at least two pose keys, starting at the first sample')
    gaps=[b['index']-a['index'] for a,b in zip(poses,poses[1:])]
    if any(not 15<=g<=60 for g in gaps):raise ValueError('Space adjacent pose keys 0.5–2 seconds apart; add intermediate poses for longer moves')
    import torch
    import onnxruntime as ort
    ort.preload_dlls();ort.set_seed(request['seed']);started=time.perf_counter()
    options=ort.SessionOptions();options.intra_op_num_threads=4;options.log_severity_level=3
    session=ort.InferenceSession(str(model_storage.resolve(provider/'mmm_v6_soma_fp32.onnx')),sess_options=options,providers=['CUDAExecutionProvider','CPUExecutionProvider'])
    if session.get_providers()[0]!='CUDAExecutionProvider':raise ValueError('MotionBricks CUDA provider unavailable; reinstall Setup')
    roots=[];rotations=[];native=[]
    for index,(start,end) in enumerate(zip(poses,poses[1:])):
        if index==0:
            context_root=np.repeat(np.asarray(start['root'])[None],4,axis=0);context_global=np.repeat(np.asarray(start['global_rotations'])[None],4,axis=0)
        else:
            context_root=roots[-1][-4:];_,context_global=data.forward(context_root,rotations[-1][-4:])
        target_root=np.repeat(np.asarray(end['root'])[None],4,axis=0);target_global=np.repeat(np.asarray(end['global_rotations'])[None],4,axis=0)
        inputs,alignment,origin=encode(np.concatenate([context_root,target_root]),np.concatenate([context_global,target_global]))
        print(f'Generating key-pose transition {index+1}/{len(poses)-1}',flush=True)
        output=dict(zip([v.name for v in session.get_outputs()],session.run(None,inputs)));tokens=int(output['pred_num_tokens'][0])
        if not 6<=tokens<=16:raise ValueError('Invalid MotionBricks duration')
        features=output['pred_global_motions'][0,3:4*tokens-3]
        root,q=decode(features,alignment,origin)
        root,q=correct_and_retime(root,q,start,end,end['index']-start['index']+1)
        roots.append(root);rotations.append(q);native.append(len(features))
    root=np.concatenate([v if i==0 else v[1:] for i,v in enumerate(roots)])
    q=np.concatenate([v if i==0 else v[1:] for i,v in enumerate(rotations)])
    # Keep the requested final partial sample if artist keys lie between 30 fps samples.
    if len(root)<request['frames']:
        count=request['frames']-len(root);root=np.concatenate([root,np.repeat(root[-1:],count,axis=0)]);q=np.concatenate([q,np.repeat(q[-1:],count,axis=0)])
    if root.shape!=(request['frames'],3) or q.shape!=(request['frames'],30,4):raise ValueError('Unexpected MotionBricks sample count')
    root.astype('<f4').tofile(folder/'root_positions.f32');q.astype('<f4').tofile(folder/'local_rotations_xyzw.f32')
    report=dict(provider='motionbricks',elapsed_seconds=time.perf_counter()-started,transitions=len(roots),native_frames=native,backend=session.get_providers()[0],gpu=torch.cuda.get_device_name())
    (folder/'motionbricks-result.json').write_text(json.dumps(report,indent=2));print('MOTIONBRICKS_MOTION_READY',json.dumps(report),flush=True)

if __name__=='__main__':run(sys.argv[1])
