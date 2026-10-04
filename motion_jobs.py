# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned local Kimodo inference, owned process cancellation and stale rig checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import bpy
import numpy as np
from . import skinning, skeleton, motion_data

PIN = '5679ff19ba0a522c0b0516e9a9d402fe1af2c027'
FILES = {
    'models/kimodo-soma-rp-v1.1-f32.gguf': '3bf1229f4c1eff1d28f5196a854113da2df9a11a5e21c60694630903bf948ee4',
    'Llama-3-Kimodo-Q8_0.gguf': 'b26d0e74b115b33a7f2df5aca04426548365e99217cd590986f8abc4172e4c5c',
    'tokenizer.gguf': '81614aca62a98846c02b72cc2e5378e5bdce8b4d507b88f96eb1faa90dae607e',
}
_verified = {}


def cache(): return skinning.provider_cache().parent / 'kimodo-5679ff1'


def sha(path):
    with Path(path).open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()


def selected_rig(context):
    rigs = {o for o in context.selected_objects if o.type == 'ARMATURE'}
    rigs.update(m.object for o in context.selected_objects if o.type == 'MESH'
                for m in o.modifiers if m.type == 'ARMATURE' and m.object)
    if len(rigs) != 1: raise ValueError('Select one accepted humanoid rig or its bound meshes')
    return next(iter(rigs))


def validate_rig(context, rig):
    if context.mode != 'OBJECT': raise ValueError('Return to Object Mode before generating motion')
    if rig.type != 'ARMATURE' or rig.constraints or any(b.constraints for b in rig.pose.bones):
        raise ValueError('Motion needs an unconstrained accepted deform rig')
    if rig.parent or rig.matrix_world.determinant() <= 0: raise ValueError('Use an unparented, positive-scale accepted rig')
    scales = rig.matrix_world.to_scale()
    if max(scales)-min(scales) > 1e-5: raise ValueError('Apply nonuniform rig scale on a working copy')
    mapping = {skeleton.canonical_name(b.name): b for b in rig.data.bones}
    skeleton.resolve_mapping(rig.data.bones)
    if not skeleton.REQUIRED <= mapping.keys(): raise ValueError('Accepted humanoid joints are missing')
    if 'Root' not in mapping or mapping['Hips'].parent != mapping['Root']:
        raise ValueError('Use an accepted unweighted Root directly above Hips for generated motion')
    if mapping['Root'].name!='Root':raise ValueError('Generated motion uses an unweighted structural bone named Root without a prefix')
    if mapping['Root'].parent or mapping['Root'].use_deform: raise ValueError('Root must be a single unweighted root')
    if any(b.inherit_scale != 'FULL' or not b.use_inherit_rotation for b in rig.data.bones):
        raise ValueError('Generated motion requires normal bone rotation and scale inheritance')
    return mapping


def prepare(context, rig, prompt, frames=90, steps=100, seed=101, in_place=False, parent=None, keyframes=False, start_frame=1):
    validate_rig(context, rig)
    helpers={b.custom_shape for b in rig.pose.bones if b.custom_shape}
    meshes=[o for o in context.selected_objects if o.type=='MESH' and o not in helpers and any(
        m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    for mesh in meshes:
        if mesh.parent_type!='OBJECT' or mesh.constraints or any(m.type=='ARMATURE' and m.object!=rig for m in mesh.modifiers):
            raise ValueError('Motion review meshes need ordinary parenting and one accepted armature')
    if not prompt.strip() or len(prompt.encode('utf-8')) > 4096: raise ValueError('Enter a motion description of at most 4096 UTF-8 bytes')
    if not 15 <= frames <= 900 or not 10 <= steps <= 200 or not 0 <= seed < 2**31:
        raise ValueError('Unsupported motion length, sampling steps or seed')
    from . import motion_keyframes
    keys=motion_keyframes.prepare(context,rig,frames,start_frame,in_place) if keyframes else None
    directory = Path(parent) if parent else cache().parent.parent / 'jobs'
    directory.mkdir(parents=True,exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='motion-',dir=directory)).resolve()
    (folder/'prompt.txt').write_text(prompt.strip(),encoding='utf-8')
    request = dict(schema_version=1,provider='kimodo.cpp',provider_revision=PIN,
        job_id=str(uuid.uuid4()),rig=rig.name,rig_pointer=str(rig.as_pointer()),
        source_digest=skinning._digest(rig, meshes),scene_unit_scale=context.scene.unit_settings.scale_length,
        meshes=[dict(name=o.name,pointer=str(o.as_pointer())) for o in meshes],
        frames=int(frames),steps=int(steps),seed=int(seed),in_place=bool(in_place),fps=30,
        prompt_sha256=sha(folder/'prompt.txt'), skeleton='soma30', models=FILES)
    if keys:
        inputs=motion_keyframes.write(folder,keys,frames)
        (folder/'keyframes.json').write_text(json.dumps(keys,indent=2,allow_nan=False))
        inputs['keyframes.json']=sha(folder/'keyframes.json');request['keyframe_inputs']=inputs
    (folder/'request.json').write_text(json.dumps(request,indent=2,allow_nan=False))
    (folder/'request.sha256').write_text(sha(folder/'request.json'))
    skinning._state(folder,'prepared')
    return folder


def finish(folder):
    request = json.loads((folder/'request.json').read_text())
    keys=check_inputs(folder,request)
    root, rotations = motion_data.load(folder,request['frames'])
    result = dict(schema_version=1,hashes={name:sha(folder/name) for name in ('root_positions.f32','local_rotations_xyzw.f32')},
                  request_sha256=sha(folder/'request.json'),diagnostics=motion_data.diagnostics(root, rotations))
    if keys:
        positions,global_rotations=motion_data.forward(root,rotations);errors=[]
        for p in keys['poses']:
            target=np.empty((30,3));rot=np.asarray(p['global_rotations'])
            for j,parent in enumerate(motion_data.PARENTS):target[j]=p['root'] if parent<0 else target[parent]+rot[parent]@motion_data.OFFSETS[j]
            distance=np.linalg.norm(positions[p['index']]-target,axis=-1)
            errors.append(dict(frame=p['frame'],model_index=p['index'],mean_joint_error_m=float(distance.mean()),max_joint_error_m=float(distance.max())))
        result['diagnostics']['keyposes']=dict(native_sampler='conditioned_DDIM',anchors=errors,exact_artist_anchors=True,
            unsupported_fingers='interpolated_artist_channels',settling_frames=4)
    (folder/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))


def check_inputs(folder,request):
    """Bind every job to its captured prompt, pose snapshots and feature mask."""
    seal=folder/'request.sha256'
    if seal.exists() and seal.read_text()!=sha(folder/'request.json'):raise ValueError('Motion request changed after preparation')
    if sha(folder/'prompt.txt')!=request['prompt_sha256']:raise ValueError('Motion prompt changed after preparation')
    inputs=request.get('keyframe_inputs')
    if not inputs:return None
    if not seal.is_file() or set(inputs)!={'keyframes.json','observed.f32','observed_mask.f32'}:raise ValueError('Incomplete key pose request')
    for name,expected in inputs.items():
        if sha(folder/name)!=expected:raise ValueError('Key pose input changed: '+name)
    keys=json.loads((folder/'keyframes.json').read_text())
    if keys['frames']!=request['frames']:raise ValueError('Key pose duration changed')
    return keys


def start(folder, provider=None):
    if skinning._jobs: raise ValueError('Wait for the current local job or cancel it')
    folder=Path(folder).resolve(); provider=Path(provider or cache()).resolve()
    request=json.loads((folder/'request.json').read_text())
    if request['provider_revision']!=PIN or request['models']!=FILES or skinning.poll(folder)['status']!='prepared':
        raise ValueError('Prepare a new motion job using the pinned provider')
    keys=check_inputs(folder,request)
    manifest=json.loads((provider/'build-manifest.json').read_text())
    if manifest['source_revision']!=PIN: raise ValueError('Kimodo binary uses a different source revision')
    from .provider_verify import native_files
    native=native_files(provider/'bin',manifest['binaries'],'kimodo-5679ff1')
    if keys and not (provider/'bin/kmd-keyframes.exe').is_file():raise ValueError('Install the updated local provider for key pose generation')
    # The binary build is recorded independently of the editable source checkout.
    files=[dict(path=str(provider/'weights'/name),sha256=value) for name,value in FILES.items()]
    files.extend(native)
    pending=[]
    for entry in files:
        path=Path(entry['path']);stamp=(str(path),path.stat().st_size,path.stat().st_mtime_ns)
        if _verified.get(stamp)!=entry['sha256']:pending.append(entry)
    if not pending:return _launch(folder,provider)
    # The large Q8 text model must never be hashed synchronously in the UI.
    from .regional_jobs import python_executable
    (folder/'verify.json').write_text(json.dumps(dict(files=pending)))
    log=(folder/'worker.log').open('wb');python=python_executable()
    try:
        process=subprocess.Popen([str(python),'-I',str(Path(__file__).with_name('provider_verify.py')),str(folder)],
            cwd=python.parent,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except Exception:log.close();raise
    skinning._jobs[str(folder)]=dict(process=process,log=log,started=time.monotonic(),phase='Verifying local model files',
        advance=lambda completed:_verified_launch(completed,provider))
    try:skinning._state(folder,'running',pid=process.pid)
    except OSError:skinning.cancel(folder);raise
    return process.pid


def _verified_launch(folder,provider):
    from .provider_verify import accept
    accept(folder,_verified)
    _launch(folder,provider)


def _launch(folder,provider):
    request=json.loads((folder/'request.json').read_text());keys=check_inputs(folder,request)
    executable=provider/'bin'/('kmd-keyframes.exe' if keys else 'kmd-generate.exe')
    environment=os.environ.copy()
    for key in list(environment):
        if key.startswith(('KIMODO_','GGML_VK_')): environment.pop(key)
    environment.update(KIMODO_BACKEND='vulkan',KIMODO_TEXT_LAYER_CHUNK='8',KIMODO_PROFILE='1',
        GGML_VK_DISABLE_COOPMAT='1',GGML_VK_DISABLE_COOPMAT2='1',GGML_VK_DISABLE_F16='1')
    log=(folder/'worker.log').open('ab')
    command=[str(executable),str(provider/'weights/models/kimodo-soma-rp-v1.1-f32.gguf'),
        str(provider/'weights/Llama-3-Kimodo-Q8_0.gguf'),str(folder/'prompt.txt'),
        str(request['frames']),str(request['steps']),str(request['seed'])]
    if keys:command.extend([str(folder/'observed.f32'),str(folder/'observed_mask.f32'),str(keys['first_heading'])])
    command.append(str(folder))
    try:
        process=subprocess.Popen(command,cwd=executable.parent,env=environment,stdout=log,stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except Exception: log.close(); raise
    skinning._jobs[str(folder)]=dict(process=process,log=log,started=time.monotonic(),finish=finish,phase='Generating between key poses' if keys else 'Generating motion')
    try: skinning._state(folder,'running',pid=process.pid)
    except OSError: skinning.cancel(folder); raise
    return process.pid


def validated(context, folder):
    folder=Path(folder).resolve()
    if skinning.poll(folder)['status'] not in {'complete','applied'}: raise ValueError('Motion worker has not completed')
    request=json.loads((folder/'request.json').read_text()); result=json.loads((folder/'result.json').read_text())
    if request['provider']!='kimodo.cpp' or request['provider_revision']!=PIN: raise ValueError('Not a supported motion job')
    keys=check_inputs(folder,request)
    if result.get('request_sha256') and result['request_sha256']!=sha(folder/'request.json'):raise ValueError('Motion request no longer matches its result')
    for name,expected in result['hashes'].items():
        if name not in ('root_positions.f32','local_rotations_xyzw.f32') or sha(folder/name)!=expected:
            raise ValueError('Motion result changed')
    if set(result['hashes'])!={'root_positions.f32','local_rotations_xyzw.f32'}: raise ValueError('Incomplete motion result')
    rig=bpy.data.objects.get(request['rig'])
    if not rig or str(rig.as_pointer())!=request['rig_pointer'] or rig.name not in context.scene.objects:
        raise ValueError('Return to the original accepted rig scene')
    validate_rig(context,rig)
    if keys:
        from . import motion_keyframes
        if hashlib.sha256(rig.get(motion_keyframes.PROPERTY,'').encode()).hexdigest()!=keys['source_sha256']:
            raise ValueError('Captured key poses changed during inference; prepare a new job')
        if abs(context.scene.render.fps/context.scene.render.fps_base-keys['scene_fps'])>1e-6:raise ValueError('Scene frame rate changed during inference')
    meshes=[bpy.data.objects.get(entry['name']) for entry in request.get('meshes',[])]
    if any(not o or str(o.as_pointer())!=entry['pointer'] or o.name not in context.scene.objects for o,entry in zip(meshes,request.get('meshes',[]))):
        raise ValueError('Motion source mesh scope no longer matches')
    if context.scene.unit_settings.scale_length!=request['scene_unit_scale'] or skinning._digest(rig,meshes)!=request['source_digest']:
        raise ValueError('Accepted joints, geometry or weights changed during inference; prepare a new motion job')
    if any(o.get('lc_motion_job')==request['job_id'] for o in context.scene.objects): raise ValueError('Motion job already applied')
    root,rotations=motion_data.load(folder,request['frames'])
    return request,result,rig,root,rotations
