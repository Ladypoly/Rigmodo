# SPDX-License-Identifier: GPL-3.0-or-later
"""Generic skeleton text motion using the shared job owner and review-copy workflow."""
import hashlib,json,math,tempfile
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix,Vector
from . import skinning,motion_jobs,weight_copy,unimate_geometry as geometry,model_storage

def cache():return skinning.provider_cache().parent/'unimate-b78c780'
def sha(path):return motion_jobs.sha(path)

def ready(provider):
    try:
        root=Path(bpy.path.abspath(provider));record=json.loads((root/'installation.json').read_text())
        return Path(record['python']).is_file() and model_storage.lock_matches(record,Path(__file__).with_name('unimate-lock.json')) and all(model_storage.resolve(root/f['path']).is_file() for f in json.loads(Path(__file__).with_name('unimate-lock.json').read_text())['files'])
    except (OSError,ValueError,KeyError,TypeError):return False

def skeleton(context,rig,forward):
    if context.mode!='OBJECT':raise ValueError('Return to Object Mode before generating motion')
    if rig.type!='ARMATURE' or rig.library or rig.data.library or rig.parent or rig.constraints:raise ValueError('Use a local, unparented deform rig without object constraints')
    linear=np.asarray(rig.matrix_world.to_3x3(),dtype=float);scale=np.linalg.norm(linear,axis=0)
    if np.linalg.det(linear)<=0 or not np.allclose(scale,scale.mean(),rtol=1e-5) or not np.allclose(linear.T@linear,np.eye(3)*scale.mean()**2,atol=1e-5):raise ValueError('Use a uniform, positive rig scale without shear')
    ad=rig.animation_data
    if ad and (ad.drivers or (ad.use_nla and any(not t.mute for t in ad.nla_tracks))):raise ValueError('Bake drivers or mute NLA tracks before generating a standalone Action')
    if any(p.constraints for p in rig.pose.bones):raise ValueError('UniMate needs an unconstrained deform rig')
    if any(b.inherit_scale!='FULL' or not b.use_inherit_rotation or b.use_local_location is False for b in rig.data.bones):raise ValueError('UniMate needs normal bone transform inheritance')
    included={b for b in rig.data.bones if b.use_deform}
    for bone in list(included):included.update(bone.parent_recursive)
    roots=[b for b in included if not b.parent]
    if len(roots)!=1:raise ValueError('UniMate needs one connected skeleton')
    # Structural game-export roots must not become a ground-level anatomical joint.
    root=roots[0];excluded=None
    if not root.use_deform and len(root.children)==1:included.remove(root);excluded=root.name;root=root.children[0]
    bones=[]
    def visit(bone):
        if bone in included:
            bones.append(bone)
            for child in bone.children:visit(child)
    visit(root);indices={b.name:i for i,b in enumerate(bones)}
    result=dict(forward=forward,bone_names=[b.name for b in bones],parents=[indices.get(b.parent.name,-1) if b.parent else -1 for b in bones],
        heads=[(linear@np.asarray(b.head_local)).tolist() for b in bones],
        labels=[b.lc_unimate_label.strip() or geometry.label(b.name) for b in bones],structural_root=excluded)
    if forward=='AUTO':
        detected=json.loads(rig.get('lc_creature_annotation','{}'))
        if detected.get('confidence') not in {'named','geometry'}:raise ValueError('Facing is ambiguous. Choose Facing direction in Motion options, then generate again.')
        result['forward_vector']=detected['forward']
    # Virtual end tips let UniMate represent rotations on terminal bones without editing the rig.
    for bone in bones:
        if not any(c in included for c in bone.children):
            result['bone_names'].append(None);result['parents'].append(indices[bone.name])
            result['heads'].append((linear@np.asarray(bone.tail_local)).tolist());result['labels'].append((bone.lc_unimate_label.strip() or geometry.label(bone.name))+' End')
    geometry.canonicalize(result)
    if any(not isinstance(s,str) or not 1<=len(s)<=128 for s in result['labels']):raise ValueError('Joint labels must contain 1–128 characters')
    return result

def source_signature(rig):
    ad=rig.animation_data;action=ad.action if ad else None
    values=[str(action.as_pointer()) if action else None]
    if action:
        for layer in action.layers:
            for strip in layer.strips:
                if strip.type=='KEYFRAME':
                    for bag in strip.channelbags:
                        values.extend((c.data_path,c.array_index,[(list(k.co),list(k.handle_left),list(k.handle_right),k.interpolation) for k in c.keyframe_points]) for c in bag.fcurves)
    return hashlib.sha256(json.dumps(values,allow_nan=False).encode()).hexdigest()

def prepare(context,rig,prompt,frames,seed,in_place,forward,guidance,provider,parent=None):
    context.view_layer.update()
    from . import creature_annotation
    creature_annotation.annotate(rig)
    spec=skeleton(context,rig,forward);meshes=motion_jobs.character_meshes(context,rig)
    for mesh in meshes:
        if mesh.parent_type!='OBJECT' or mesh.constraints or any(m.type=='ARMATURE' and m.object!=rig for m in mesh.modifiers):raise ValueError('Motion review meshes need ordinary parenting and one armature')
    if not prompt.strip() or len(prompt.encode('utf-8'))>4096:raise ValueError('Enter a motion description of at most 4096 UTF-8 bytes')
    if not 15<=frames<=60 or not 0<=seed<2**31 or not math.isfinite(guidance) or not 1<guidance<=10:raise ValueError('Unsupported UniMate duration, seed or guidance')
    directory=Path(parent) if parent else cache().parent.parent/'jobs';directory.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='unimate-',dir=directory)).resolve()
    request=dict(schema_version=1,provider='unimate',provider_cache=str(Path(provider).resolve()),
        job_id=__import__('uuid').uuid4().hex,rig=rig.name,rig_pointer=str(rig.as_pointer()),scene_pointer=str(context.scene.as_pointer()),
        meshes=[dict(name=m.name,pointer=str(m.as_pointer())) for m in meshes],source_digest=skinning._digest(rig,meshes),
        action_signature=source_signature(rig),skeleton=spec,frames=int(frames),seed=int(seed),guidance=float(guidance),
        in_place=bool(in_place),prompt=prompt.strip(),fps=30,scene_fps=context.scene.render.fps/context.scene.render.fps_base,
        unit_scale=context.scene.unit_settings.scale_length,start_frame=context.scene.frame_start)
    (folder/'request.json').write_text(json.dumps(request,indent=2,allow_nan=False));(folder/'request.sha256').write_text(sha(folder/'request.json'))
    skinning._state(folder,'prepared');return folder

def start(folder):
    from . import image_pose
    folder=Path(folder).resolve();request=json.loads((folder/'request.json').read_text());provider=Path(request['provider_cache'])
    if skinning._jobs:raise ValueError('Wait for the current local job or cancel it')
    if skinning.poll(folder)['status']!='prepared' or not ready(str(provider)):raise ValueError('Install Creature Motion in Extension Settings → Setup')
    python=json.loads((provider/'installation.json').read_text())['python']
    image_pose.launch(folder,[python,'-I',str(Path(__file__).with_name('unimate_worker.py')),str(folder)],'Generating creature motion · UniMate')
    skinning._jobs[str(folder)]['finish']=lambda p:output(p)

def output(folder):
    folder=Path(folder);request=json.loads((folder/'request.json').read_text());report=json.loads((folder/'result.json').read_text())
    if sha(folder/'request.json')!=(folder/'request.sha256').read_text() or report.get('request_sha256')!=sha(folder/'request.json'):raise ValueError('UniMate request changed')
    if report.get('provider')!='unimate' or report.get('schema_version')!=1 or report.get('fps')!=30 or report.get('frames')!=request['frames']:raise ValueError('Wrong UniMate output protocol')
    path=folder/'motion.npz'
    if path.stat().st_size>4*1024*1024 or sha(path)!=report['output_sha256']:raise ValueError('UniMate result changed or oversized')
    with np.load(path,allow_pickle=False) as data:positions=data['positions'];rotations=data['rotations']
    f=request['frames'];n=len(request['skeleton']['parents'])
    if positions.shape!=(f,n,3) or rotations.shape!=(f,n,3,3) or not np.isfinite(positions).all() or not np.isfinite(rotations).all():raise ValueError('Invalid UniMate motion dimensions or numbers')
    if not np.allclose(rotations.swapaxes(-1,-2)@rotations,np.eye(3),atol=1e-4) or not np.allclose(np.linalg.det(rotations),1,atol=1e-4):raise ValueError('Invalid generated rotation matrices')
    heads=np.asarray(request['skeleton']['heads']);extent=max(np.ptp(heads,axis=0).max(),1e-6)
    if np.max(np.abs(positions-heads[None]))>extent*100:raise ValueError('Generated motion is outside a usable range')
    return request,report,positions,rotations

def bake(context,rig,request,positions,rotations):
    action=bpy.data.actions.new('UniMate · '+request['prompt'][:48]);rig.animation_data_create();rig.animation_data.action=action
    linear=rig.matrix_world.to_3x3();inverse=linear.inverted();world_rotation=linear.normalized()
    times=request['start_frame']+np.arange(len(positions))*request['scene_fps']/30
    previous={};names=request['skeleton']['bone_names'];root_name=next(n for n in names if n)
    for p in rig.pose.bones:p.matrix_basis.identity();p.rotation_mode='QUATERNION'
    quats={n:[] for n in names if n};locations=[]
    for frame in range(len(positions)):
        poses={p.name:p.bone.matrix_local.copy() for p in rig.pose.bones}
        for j,name in enumerate(names):
            if name is None:continue
            bone=rig.data.bones[name]
            delta=world_rotation.transposed()@Matrix(rotations[frame,j].tolist())@world_rotation
            target=delta.to_4x4()@bone.matrix_local;target.translation=inverse@Vector(positions[frame,j])
            poses[name]=target
            basis=bone.convert_local_to_pose(target,bone.matrix_local,
                parent_matrix=poses[bone.parent.name] if bone.parent else Matrix.Identity(4),
                parent_matrix_local=bone.parent.matrix_local if bone.parent else Matrix.Identity(4),invert=True)
            q=basis.to_quaternion().normalized()
            if name in previous and q.dot(previous[name])<0:q.negate()
            previous[name]=q.copy();quats[name].append(tuple(q))
            if name==root_name:locations.append(tuple(basis.translation))
    interpolation=bpy.types.Keyframe.bl_rna.properties['interpolation'].enum_items['LINEAR'].value
    for name,values in quats.items():
        pose=rig.pose.bones[name];channels=[('rotation_quaternion',np.asarray(values))]
        if name==root_name:channels.append(('location',np.asarray(locations)))
        for prop,data in channels:
            for index in range(data.shape[1]):
                curve=action.fcurve_ensure_for_datablock(rig,pose.path_from_id(prop),index=index,group_name=name)
                points=curve.keyframe_points;points.add(len(times));points.foreach_set('co',np.column_stack([times,data[:,index]]).astype(np.float32).ravel())
                points.foreach_set('interpolation',np.full(len(times),interpolation,dtype=np.int32));curve.update()
    action['lc_source_fps']=30;action['lc_in_place']=request['in_place'];action['lc_motion_provider']='unimate'
    from .motion_playback import stamp
    stamp(action,request['prompt'])
    return action

def apply(context,folder):
    folder=Path(folder).resolve()
    if context.mode!='OBJECT' or skinning.poll(folder)['status']!='complete':raise ValueError('UniMate motion is not ready')
    request,report,positions,rotations=output(folder);original=bpy.data.objects.get(request['rig'])
    if not original or str(original.as_pointer())!=request['rig_pointer'] or str(context.scene.as_pointer())!=request['scene_pointer']:raise ValueError('Return to the original creature scene')
    meshes=[bpy.data.objects.get(m['name']) for m in request['meshes']]
    if any(not m or str(m.as_pointer())!=entry['pointer'] or m.name not in context.scene.objects for m,entry in zip(meshes,request['meshes'])):raise ValueError('Creature mesh scope changed')
    if skeleton(context,original,request['skeleton']['forward'])!=request['skeleton'] or skinning._digest(original,meshes)!=request['source_digest'] or source_signature(original)!=request['action_signature']:raise ValueError('Creature joints, labels, weights or Action changed; generate again')
    if context.scene.unit_settings.scale_length!=request['unit_scale'] or context.scene.render.fps/context.scene.render.fps_base!=request['scene_fps']:raise ValueError('Scene units or frame rate changed; generate again')
    if any(o.get('lc_motion_job')==request['job_id'] for o in context.scene.objects):raise ValueError('Motion already applied')
    collection,rig,copies=weight_copy.clone(context,original,meshes,'UniMate');action=None
    try:
        rig.animation_data_clear();action=bake(context,rig,request,positions,rotations)
        rig['lc_motion_job']=request['job_id'];rig['lc_motion_provider']='unimate';rig['lc_rig_type']='CREATURE';rig['lc_motion_prompt']=request['prompt'];rig['lc_motion_diagnostics']=json.dumps(report)
        skinning._state(folder,'applied',collection=collection.name)
    except Exception:
        action=action or (rig.animation_data.action if rig.animation_data else None)
        for obj in [rig,*copies]:
            data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if not data.users:(bpy.data.armatures if isinstance(data,bpy.types.Armature) else bpy.data.meshes).remove(data)
        if action and not action.users:bpy.data.actions.remove(action)
        bpy.data.collections.remove(collection);raise
    context.scene.frame_set(context.scene.frame_current,subframe=context.scene.frame_subframe)
    return collection,rig,copies,action,report
