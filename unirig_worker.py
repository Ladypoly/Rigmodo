# SPDX-License-Identifier: GPL-3.0-or-later
"""Standalone CUDA skeleton inference; no Blender or ComfyUI imports."""
import copy,hashlib,json,os,sys,time
from pathlib import Path

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def run(folder):
    started=time.monotonic();folder=Path(folder).resolve()
    request=json.loads((folder/'request.json').read_text());provider=Path(request['provider_cache'])
    installation=json.loads((provider/'installation.json').read_text())
    lock=json.loads(Path(__file__).with_name('unirig-lock.json').read_text())
    if installation['source_revision']!=lock['source_revision']:raise ValueError('Install the pinned UniRig provider')
    checkpoint=Path(installation['checkpoint'])
    if checkpoint.stat().st_size!=lock['model_bytes'] or sha(checkpoint)!=lock['model_sha256']:raise ValueError('UniRig checkpoint changed')
    for path,expected in installation['source_hashes'].items():
        if sha(provider/path)!=expected:raise ValueError('UniRig source changed: '+path)
    if sha(folder/'input.npz')!=request['input_sha256']:raise ValueError('Creature input changed')
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    sys.path[:0]=[str(provider/'python'),str(provider)]
    import numpy as np
    import torch
    from transformers import OPTForCausalLM
    from safetensors.torch import load_file
    from unirig_model.configs import AR_MODEL_CONFIG,TOKENIZER_CONFIG
    from unirig_model.tokenizer_spec import TokenizerConfig
    from unirig_model.tokenizer_part import TokenizerPart
    from unirig_model.unirig_ar import UniRigAR
    if not torch.cuda.is_available():raise ValueError('UniRig requires an NVIDIA CUDA GPU')
    torch.set_num_threads(4);torch.manual_seed(request['seed']);torch.cuda.reset_peak_memory_stats()
    tokenizer=TokenizerPart(config=TokenizerConfig.parse(TOKENIZER_CONFIG))
    config=copy.deepcopy(AR_MODEL_CONFIG);config.pop('__target__')
    with torch.device('meta'):
        model=UniRigAR(**config,tokenizer=tokenizer,dtype=torch.float32,device='meta',operations=torch.nn)
    weights={k.removeprefix('model.'):v for k,v in load_file(str(checkpoint)).items()}
    embedding='transformer.model.decoder.embed_tokens.weight';head='transformer.lm_head.weight'
    if head not in weights and embedding in weights:weights[head]=weights[embedding]
    model.load_state_dict(weights,strict=True,assign=True);model.transformer.tie_weights()
    if any(p.is_meta for p in model.parameters()) or any(b.is_meta for b in model.buffers()):raise ValueError('Incomplete UniRig model initialization')
    model=model.eval().to('cuda');del weights
    with np.load(folder/'input.npz',allow_pickle=False) as data:
        vertices=np.asarray(data['vertices'],dtype=np.float32);faces=np.asarray(data['triangles'],dtype=np.int64)
    # UniRig was trained in Blender Z-up; the shared MIA transport is glTF Y-up.
    vertices=vertices[:,[0,2,1]]*np.array([1,-1,1],dtype=np.float32)
    center=(vertices.min(0)+vertices.max(0))*.5;scale=float(np.ptp(vertices,axis=0).max()*.5)
    if not np.isfinite(vertices).all() or scale<=1e-6:raise ValueError('Invalid creature geometry')
    vertices=(vertices-center)/scale
    triangle=vertices[faces];cross=np.cross(triangle[:,1]-triangle[:,0],triangle[:,2]-triangle[:,0])
    areas=np.linalg.norm(cross,axis=1)
    if not np.isfinite(areas).all() or areas.sum()<=1e-9:raise ValueError('Creature surface has no area')
    # Match UniRig's released mixed 65,536-point inference distribution.
    rng=np.random.RandomState(request['seed']);vertex_count=min(8192,len(vertices));count=65536-vertex_count
    vertex_ids=rng.permutation(len(vertices))[:vertex_count]
    vertex_normals=np.zeros_like(vertices)
    for axis in range(3):np.add.at(vertex_normals,faces[:,axis],cross)
    vertex_normals/=np.maximum(np.linalg.norm(vertex_normals,axis=1,keepdims=True),1e-12)
    weights=areas.astype(np.float64)**2;indices=rng.choice(len(faces),count,p=weights/weights.sum())
    r=np.sqrt(rng.random(count));s=rng.random(count)
    points=triangle[indices,0]*(1-r[:,None])+triangle[indices,1]*(r*(1-s))[:,None]+triangle[indices,2]*(r*s)[:,None]
    normals=cross[indices]/np.maximum(areas[indices,None],1e-12)
    points=np.concatenate((vertices[vertex_ids],points));normals=np.concatenate((vertex_normals[vertex_ids],normals))
    print('Generating creature skeleton on '+torch.cuda.get_device_name(),flush=True)
    with torch.inference_mode():
        result=model.generate(vertices=torch.from_numpy(points.astype(np.float32)).to('cuda'),
            normals=torch.from_numpy(normals.astype(np.float32)).to('cuda'),cls='articulationxl',
            max_new_tokens=2048,num_beams=15,do_sample=True,top_k=5,top_p=.95,repetition_penalty=3.,temperature=1.5)
    joints=np.asarray(result.joints,dtype=np.float64)*scale+center
    joints=joints[:,[0,2,1]]*np.array([1,1,-1])
    tails=None
    if result.tails is not None:
        tails=np.asarray(result.tails,dtype=np.float64)*scale+center
        tails=(tails[:,[0,2,1]]*np.array([1,1,-1])).tolist()
    output=dict(schema_version=1,provider='unirig',coordinate_space='world_meters_gltf_y_up',
        heads=joints.tolist(),tails=tails,parents=[-1 if p is None else int(p) for p in result.parents],
        request_sha256=sha(folder/'request.json'),elapsed_seconds=time.monotonic()-started,
        device=torch.cuda.get_device_name(),peak_gpu_bytes=torch.cuda.max_memory_allocated(),samples=65536,beams=15,
        model_coordinate_space='blender_z_up')
    (folder/'output.json').write_text(json.dumps(output,allow_nan=False,indent=2))
    print('CREATURE_SKELETON_READY',len(joints),output['elapsed_seconds'],output['peak_gpu_bytes'],flush=True)

if __name__=='__main__':run(sys.argv[1])
