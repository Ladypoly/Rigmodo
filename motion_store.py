# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable, data-only motion clips and inexpensive skeleton thumbnails."""
import hashlib,json,math,os,re,tempfile,time
from contextlib import contextmanager
from pathlib import Path
import bpy
import numpy as np

DEFAULT_ROOT='R:/AI/MotionLibrary/Rigmodo'


@contextmanager
def locked(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with (root/'.catalog.lock').open('a+b') as stream:
        stream.seek(0,2)
        if stream.tell()==0:stream.write(b'\0');stream.flush()
        started=time.monotonic()
        while True:
            try:
                stream.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()-started>15:raise ValueError('Motion library is busy; retry shortly')
                time.sleep(.05)
        try:yield
        finally:
            stream.seek(0)
            if os.name=='nt':msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(data,f,indent=2,allow_nan=False)
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def catalog(root):
    path=Path(root)/'catalog.json'
    if not path.exists():return {'schema':1,'clips':[]}
    if path.stat().st_size>32*1024*1024:raise ValueError('Motion library catalog is too large')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema')!=1 or not isinstance(data.get('clips'),list):raise ValueError('Unsupported motion library catalog')
    return data


def clip_dir(root,key):
    if not re.fullmatch('[a-f0-9]{32}',key):raise ValueError('Invalid motion library clip identifier')
    path=(Path(root)/'clips'/key).resolve()
    if not path.is_relative_to(Path(root).resolve()):raise ValueError('Motion path leaves the library folder')
    return path


def canonical(name):
    name=name.rsplit(':',1)[-1]
    alias={'pelvis':'Hips','hips':'Hips','root':'Root','spine_01':'Spine','spine_02':'Spine1','spine_03':'Spine2','neck_01':'Neck','head':'Head'}
    if name in alias:return alias[name]
    match=re.fullmatch(r'(clavicle|upperarm|lowerarm|hand|thigh|calf|foot|ball)_([lr])',name)
    if match:
        return ('Left' if match[2]=='l' else 'Right')+dict(clavicle='Shoulder',upperarm='Arm',lowerarm='ForeArm',hand='Hand',thigh='UpLeg',calf='Leg',foot='Foot',ball='ToeBase')[match[1]]
    match=re.fullmatch(r'(thumb|index|middle|ring|pinky)_0([123])_([lr])',name)
    if match:return ('Left' if match[3]=='l' else 'Right')+'Hand'+match[1].title()+match[2]
    return name


def humanoid(names):
    required={'Hips','Head','LeftArm','RightArm','LeftUpLeg','RightUpLeg','LeftFoot','RightFoot'}
    return required<=set(map(canonical,names))


def curves_for(action,slot):
    curves=[]
    for layer in action.layers:
        for strip in layer.strips:
            bag=strip.channelbag(slot,ensure=False)
            if bag:curves.extend(bag.fcurves)
    return curves


def bounds(action,slot):
    times=[float(p.co.x) for c in curves_for(action,slot) for p in (*c.keyframe_points,*c.sampled_points)]
    if not times:raise ValueError('This animation has no keyframes')
    lo,hi=(float(action.frame_start),float(action.frame_end)) if action.use_frame_range else (min(times),max(times))
    if not all(math.isfinite(x) for x in (lo,hi)) or hi<=lo:raise ValueError('Animation must span at least two distinct frames')
    return lo,hi


def sample_times(values):
    values=np.unique(np.round(np.asarray(values,dtype=np.float64),6))
    # Float32 capture times and the bake grid can differ by microseconds.
    kept=[float(values[0])]
    for value in values[1:]:
        if value-kept[-1]>1e-5:kept.append(float(value))
    if len(kept)==1:kept.append(float(values[-1]))
    else:kept[-1]=float(values[-1])
    return np.asarray(kept,dtype=np.float32)


def capture(context,rig,action,slot):
    if any(p.constraints for p in rig.pose.bones) or rig.constraints:raise ValueError('Bake control-rig constraints before saving to the library')
    lo,hi=bounds(action,slot);fps=context.scene.render.fps/context.scene.render.fps_base
    duration=(hi-lo)/fps
    if duration>180 or len(rig.data.bones)>512:raise ValueError('Library clips are limited to 180 seconds and 512 bones')
    names=[b.name for b in rig.data.bones];parents=[names.index(b.parent.name) if b.parent else -1 for b in rig.data.bones]
    old=rig.animation_data;previous=(old.action,old.action_slot,old.use_nla,old.action_blend_type,old.action_influence) if old else None
    frame=context.scene.frame_current;sub=context.scene.frame_subframe;pose=[p.matrix_basis.copy() for p in rig.pose.bones];modes={p.name:p.rotation_mode for p in rig.pose.bones}
    reference=rig.matrix_world.copy();samples=max(2,math.ceil(duration*30)+1);values=[]
    keys=[float(p.co.x) for c in curves_for(action,slot) for p in (*c.keyframe_points,*c.sampled_points) if lo<=p.co.x<=hi]
    times=sample_times((np.r_[np.linspace(lo,hi,samples),keys]-lo)/fps)
    times[0]=0.;times[-1]=duration;frames=lo+times.astype(np.float64)*fps
    if len(frames)>30000 or len(frames)*len(names)*64>200*1024*1024:raise ValueError('Motion is too dense; trim or simplify it before saving')
    try:
        from . import animation
        animation.attach_action(rig,{'action':action,'slot':slot});ad=rig.animation_data
        for p,matrix in zip(rig.pose.bones,pose):p.matrix_basis=matrix
        context.scene.frame_set(math.floor(lo),subframe=lo%1);context.view_layer.update();reference=rig.matrix_world.copy()
        for f in frames:
            context.scene.frame_set(math.floor(f),subframe=f%1);context.view_layer.update()
            evaluated=rig.evaluated_get(context.evaluated_depsgraph_get());object_delta=reference.inverted()@evaluated.matrix_world
            values.append([np.asarray(object_delta@p.matrix,dtype=np.float32) for p in evaluated.pose.bones])
        data=dict(names=np.asarray(names),parents=np.asarray(parents,dtype=np.int32),rest=np.asarray([b.matrix_local for b in rig.data.bones],dtype=np.float32),
                  poses=np.asarray(values,dtype=np.float32),times=times,
                  labels=np.asarray([getattr(b,'lc_unimate_label',b.get('lc_unimate_label','')) for b in rig.data.bones]))
        from . import rig_mapping
        roles=rig_mapping.names(rig)
        if roles!=[rig_mapping.canonical(n) for n in names]:data['roles']=np.asarray(roles)
        samples=action.get('lc_contact_samples')
        if samples:
            values=json.loads(samples)
            data['contact_probabilities']=np.column_stack([np.interp(data['times'],values['times'],np.asarray(values['probabilities'])[:,i]) for i in range(2)]).astype(np.float32)
        metadata={key:action[key] for key in ('lc_contact_overrides','lc_capture_provenance','lc_capture_video','lc_capture_offset_seconds','lc_motion_prompt','lc_library_source','lc_library_license') if key in action}
        if metadata:data['provenance']=np.asarray([json.dumps(metadata)])
        validate(data);return data
    finally:
        if previous:
            ad.action,ad.action_slot,ad.use_nla,ad.action_blend_type,ad.action_influence=previous
        else:rig.animation_data_clear()
        for p,matrix in zip(rig.pose.bones,pose):p.rotation_mode=modes[p.name];p.matrix_basis=matrix
        context.scene.frame_set(frame,subframe=sub);context.view_layer.update()


def validate(data):
    names=data['names'];n=len(names);poses=data['poses'];f=len(data['times'])
    if 'roles' in data and (data['roles'].shape!=(n,) or data['roles'].dtype.kind not in 'US'):raise ValueError('Invalid humanoid role array')
    if 'provenance' in data:
        if data['provenance'].shape!=(1,) or data['provenance'].dtype.kind not in 'US' or data['provenance'].nbytes>256*1024:raise ValueError('Invalid motion provenance')
        metadata=json.loads(str(data['provenance'][0]))
        if not isinstance(metadata,dict) or any(not isinstance(v,(str,int,float,bool)) for v in metadata.values()):raise ValueError('Motion provenance must contain simple values')
    if 'source_times' in data and (data['source_times'].shape!=(f,) or not np.isfinite(data['source_times']).all() or not np.all(np.diff(data['source_times'])>0)):raise ValueError('Invalid source timestamps')
    if 'contact_probabilities' in data:
        probabilities=data['contact_probabilities']
        if probabilities.shape!=(f,2) or not np.isfinite(probabilities).all() or (probabilities<0).any() or (probabilities>1).any():raise ValueError('Invalid foot-contact probabilities')
    if not 1<=n<=512 or len(set(map(str,names)))!=n or not 2<=f<=30000:raise ValueError('Invalid motion dimensions')
    if data['rest'].shape!=(n,4,4) or poses.shape!=(f,n,4,4) or data['parents'].shape!=(n,):raise ValueError('Invalid skeleton or pose array shape')
    if not all(data[k].dtype.kind in 'fiu' and np.isfinite(data[k]).all() for k in ('rest','poses','times')):raise ValueError('Motion contains invalid numeric values')
    if data['times'][0]!=0 or not np.all(np.diff(data['times'])>0) or data['times'][-1]>180:raise ValueError('Invalid motion sample times')
    if data['labels'].shape!=(n,) or data['parents'].dtype.kind not in 'iu' or not np.all((data['parents']>=-1)&(data['parents']<n)):raise ValueError('Invalid skeleton parent or labels')
    for i,parent in enumerate(data['parents']):
        visited={i};p=int(parent)
        while p>=0:
            if p in visited:raise ValueError('Cyclic skeleton hierarchy')
            visited.add(p);p=int(data['parents'][p])


def read(root,key):return read_file(clip_dir(root,key)/'motion.npz')


def read_file(path):
    path=Path(path)
    if path.stat().st_size>100*1024*1024:raise ValueError('Motion payload is too large')
    import zipfile
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist())>220*1024*1024:raise ValueError('Expanded motion payload is too large')
        for item in z.infolist():
            with z.open(item) as stream:
                version=np.lib.format.read_magic(stream)
                reader=np.lib.format.read_array_header_1_0 if version==(1,0) else np.lib.format.read_array_header_2_0
                shape,_,dtype=reader(stream)
                if dtype.hasobject or math.prod(shape)*dtype.itemsize>200*1024*1024:raise ValueError('Unsafe motion array header')
    with np.load(path,allow_pickle=False) as archive:
        data={k:archive[k] for k in ('names','parents','rest','poses','times','labels')}
        if 'roles' in archive:data['roles']=archive['roles']
        if 'contact_probabilities' in archive:data['contact_probabilities']=archive['contact_probabilities']
        if 'source_times' in archive:data['source_times']=archive['source_times']
        if 'provenance' in archive:data['provenance']=archive['provenance']
    validate(data);return data


def thumbnail(data,path):
    width,height=384,224;pixels=np.empty((height,width,4),dtype=np.float32);pixels[:]=(.055,.065,.082,1)
    rest=data['rest'][:,:3,3];poses=data['poses']
    points=np.concatenate([poses[i,:,:3,3]-(poses[i,0,:3,3]-rest[0]) for i in (0,len(poses)//2,len(poses)-1)])
    # Common three-quarter view keeps silhouettes readable for humans and creatures.
    project=np.array([[.78,-.62,0],[.28,.35,.90]],dtype=np.float32)
    projected=points@project.T;lo=projected.min(0);hi=projected.max(0);span=max(float((hi-lo).max()),.01)
    for column,index in enumerate((0,len(poses)//2,len(poses)-1)):
        points=poses[index,:,:3,3].copy();points-=points[0]-rest[0]
        xy=points@project.T;xy=(xy-(lo+hi)*.5)*(105/span)+np.array([64+128*column,107])
        for j,parent in enumerate(data['parents']):
            if parent<0:continue
            start,end=xy[parent],xy[j];count=max(2,int(np.linalg.norm(end-start)*2))
            segment=np.linspace(start,end,count).round().astype(int)
            for x,y in segment:
                if 1<=x<width-1 and 1<=y<height-1:pixels[y-1:y+2,x-1:x+2]=(.31,.67,.88,1)
    image=bpy.data.images.new('Rigmodo motion thumbnail',width=width,height=height,alpha=True)
    try:image.pixels.foreach_set(pixels.ravel());image.filepath_raw=str(path);image.file_format='PNG';image.save()
    finally:bpy.data.images.remove(image)


def write(root,data,name,source='Own animation',license='User-provided',family='',loop=False,tags=''):
    validate(data)
    digest=hashlib.sha256()
    for k in ('names','parents','rest','poses','times','labels'):digest.update(data[k].tobytes())
    if 'roles' in data:digest.update(data['roles'].tobytes())
    if 'contact_probabilities' in data:digest.update(data['contact_probabilities'].tobytes())
    if 'provenance' in data:
        overrides=json.loads(str(data['provenance'][0])).get('lc_contact_overrides')
        if overrides:digest.update(overrides.encode('utf-8'))
    key=digest.hexdigest()[:32]
    with locked(root):return _write(root,key,data,name,source,license,family,loop,tags)


def _write(root,key,data,name,source,license,family,loop,tags):
    folder=clip_dir(root,key);folder.mkdir(parents=True,exist_ok=True)
    existing=catalog(root)
    if any(c['id']==key for c in existing['clips']):return key,False
    temporary=folder/'motion.pending.npz';np.savez_compressed(temporary,**data);os.replace(temporary,folder/'motion.npz')
    thumbnail(data,folder/'preview.png')
    record=dict(id=key,name=name,source=source,license=license,family=family or ('Human' if humanoid(data.get('roles',data['names'])) else 'Creature'),
                tags=tags,duration=float(data['times'][-1]),bones=len(data['names']),loop=bool(loop),favorite=False)
    atomic(folder/'clip.json',record);existing['clips'].append(record);atomic(Path(root)/'catalog.json',existing)
    return key,True
