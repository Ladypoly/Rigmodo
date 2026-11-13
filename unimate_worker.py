# SPDX-License-Identifier: GPL-3.0-or-later
"""One owned, offline UniMate process; no dataset, Blender or remote LLM."""
# Conditioning adapted from UniMate-B3D backend/worker.py (MIT); see NOTICE.
import hashlib,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import model_storage


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def run(folder):
    started=time.perf_counter();folder=Path(folder).resolve()
    request=json.loads((folder/'request.json').read_text());provider=Path(request['provider_cache'])
    lock=json.loads(Path(__file__).with_name('unimate-lock.json').read_text())
    record=json.loads((provider/'installation.json').read_text())
    if sha(folder/'request.json')!=(folder/'request.sha256').read_text():raise ValueError('Motion request changed')
    if record['source_revision']!=lock['source_revision'] or not model_storage.lock_matches(record,Path(__file__).with_name('unimate-lock.json')):raise ValueError('Reinstall the pinned UniMate provider')
    for name,expected in record['source_hashes'].items():
        if sha(provider/name)!=expected:raise ValueError('UniMate source changed: '+name)
    for entry in lock['files']:
        if sha(model_storage.resolve(provider/entry['path']))!=entry['sha256']:raise ValueError('UniMate model changed: '+entry['path'])
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    sys.path.insert(0,str(Path(__file__).parent));sys.path.insert(0,str(provider/'source'))
    import numpy as np
    import torch
    from transformers import T5Tokenizer,T5EncoderModel
    from unimate.configs.schema import MainConfig
    from unimate.models.factory import create_model,create_transport
    from unimate.models.flow.transport import Sampler
    from unimate.inference.generate import generate_samples
    from unimate.training.ema import EMAModel
    from unimate.dataset.mixture.collate import mixture_batch_collate
    from unimate.dataset.transforms import build_parent_features
    from unimate.utils.topology_utils import compute_edge_indexs,compute_joint_depths,compute_edge_relations_and_distances,compute_laplacian_eigenvectors
    from unimate_geometry import canonicalize,decode
    torch.set_num_threads(min(8,os.cpu_count() or 1))
    if not torch.cuda.is_available():raise ValueError('UniMate requires the installed NVIDIA CUDA runtime')
    device=torch.device('cuda');torch.manual_seed(request['seed']);np.random.seed(request['seed'])
    torch.cuda.reset_peak_memory_stats()
    exp=model_storage.resolve(provider/'weights/unimate_uniml3d_f60_v3');config=MainConfig.from_json(exp/'config.json')
    if config.dataset.feature_len!=12 or config.dataset.topology_condition_type!='tpos' or config.training.diff_model!='flow':raise ValueError('Unsupported UniMate model protocol')
    skeleton=request['skeleton'];canonical=canonicalize(skeleton);parents=canonical['parents'];n=len(parents)
    if n>config.dataset.max_joints or not 15<=request['frames']<=config.dataset.max_motion_length:raise ValueError('Motion exceeds checkpoint joint/frame limit')
    # This tiny pickle comes only from the checksum-verified, pinned official release.
    stats=np.load(exp/'dataset_stats.npy',allow_pickle=True).item()
    selected=stats['objaverse']
    if config.dataset.use_dataset_stats or any(not np.array_equal(v[k],selected[k]) for v in stats.values() for k in ('mean_root','std_root','mean_local','std_local')):raise ValueError('Expected shared global normalization statistics')
    stats=selected
    mean=np.tile(stats['mean_local'],(n,1)).astype(np.float32);std=np.tile(stats['std_local'],(n,1)).astype(np.float32)
    mean[0],std[0]=stats['mean_root'],stats['std_root']
    if mean.shape!=(n,12) or not np.isfinite(mean).all() or not np.isfinite(std).all() or np.any(std<=0):raise ValueError('Invalid normalization statistics')
    tpose=np.zeros((n,12),np.float32);tpose[:,:3]=canonical['positions'];tpose[:,3:9]=[1,0,0,0,1,0];tpose=(tpose-mean)/std
    print('Encoding prompt and joint labels locally',flush=True)
    tokenizer=T5Tokenizer.from_pretrained(model_storage.resolve(provider/'text_encoder'),local_files_only=True)
    encoder=T5EncoderModel.from_pretrained(model_storage.resolve(provider/'text_encoder'),local_files_only=True).to(device).eval()
    with torch.inference_mode():
        tokens=tokenizer([request['prompt'],*skeleton['labels']],padding=True,return_tensors='pt').to(device)
        hidden=encoder(**tokens).last_hidden_state.float();mask=tokens['attention_mask'].bool()
        embeddings=[h[m].cpu().numpy() for h,m in zip(hidden,mask)]
    del encoder,tokens,hidden;torch.cuda.empty_cache()
    relations,distances=compute_edge_relations_and_distances(parents,max_path_len=5)
    spectral,_=compute_laplacian_eigenvectors(parents,max_freqs=config.model.max_freqs)
    length=config.dataset.max_motion_length
    batch=dict(motion=np.zeros((length,n,12),np.float32),motion_length=length,max_motion_length=length,
        max_joints=config.dataset.max_joints,start_idx=0,parents=parents,edge_indexs=compute_edge_indexs(parents),
        tpos_first_frame=tpose,offsets=canonical['offsets'],joint_graph_dist=distances,joint_relations=relations,
        joint_depths=compute_joint_depths(parents),spectral_feats=spectral,
        joint_names_emb=np.stack([e.mean(0) for e in embeddings[1:]]),mean=mean,std=std,
        caption=request['prompt'],caption_emb=embeddings[0].mean(0),caption_tokens=embeddings[0],
        object_type='rigmodo',**build_parent_features(tpose,parents))
    motion,cond=mixture_batch_collate([batch])
    cond={k:(v.to(device) if torch.is_tensor(v) else [i.to(device) if torch.is_tensor(i) else i for i in v] if isinstance(v,list) else v) for k,v in cond.items()}
    print('Loading UniMate EMA weights',flush=True)
    model=create_model(config.dataset,config.model)
    state=torch.load(exp/'checkpoints/checkpoint_step_150000.pt',map_location='cpu',weights_only=True)
    model.load_state_dict(state['model_state_dict'],strict=True)
    if config.training.use_ema:
        ema=EMAModel(model.parameters(),decay=config.training.ema_decay,use_ema_warmup=True)
        ema.load_state_dict(state['ema_state_dict']);ema.copy_to(model.parameters());del ema
    del state;model.to(device).eval()
    print('Generating text-conditioned motion',flush=True)
    transport=create_transport(training_config=config.training)
    with torch.inference_mode():
        samples=generate_samples(model,cond,motion.shape,'flow',transport,Sampler(transport),device=device,cfg_scale=request['guidance'])
    features=samples[0,:n].permute(2,0,1).cpu().numpy()[:request['frames']]*std[None]+mean[None]
    positions,rotations=decode(features,canonical)
    if request['in_place']:
        delta=positions[:,0]-positions[0,0];delta[:,2]=0;positions-=delta[:,None]
    np.savez(folder/'motion.npz',positions=positions.astype(np.float32),rotations=rotations.astype(np.float32))
    result=dict(schema_version=1,provider='unimate',request_sha256=sha(folder/'request.json'),output_sha256=sha(folder/'motion.npz'),
        frames=len(features),joints=n,fps=30,elapsed_seconds=time.perf_counter()-started,peak_gpu_bytes=torch.cuda.max_memory_allocated(),
        gpu=torch.cuda.get_device_name(),prompt=request['prompt'])
    (folder/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    print('UNIMATE_MOTION_READY',json.dumps(result),flush=True)

if __name__=='__main__':run(sys.argv[1])
