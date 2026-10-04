# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry-only original-MIA landmark inference, outside Blender's Python.

The verified MIT upstream model stays in the provider cache. Training/dataset,
Blender, ARP, UI and pose modules are not imported by this adapter.
"""
import argparse
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import types
import zipfile

import numpy as np
import torch

MODEL_HASHES = {'joints.pth': '595587abb2ef9977bc9e49f8221c326da473de8ff1cd8785eb55ac63acde2b8e',
                'joints_coarse.pth': '389e18f92a65e7925c1a940dfff22cc85e9ac4ead17ab4a65fd4ef5d6088b96b'}
SOURCE_HASHES = {'model.py':'c8b920a35e2fcee9efcb6efeae89ed555dbd4a7ff763479f612aea214c2625da',
    'models_ae.py':'e8df87c61498de5501ada30b70406c81b89e2c3c00fa9a65aee846887ceb22da',
    'util/dataset_mixamo.py':'aec35104acff5c93ab197bc4426715f909900c7251642f745395e10ac445e917'}


def fps(points, batch=None, ratio=.5, random_start=True):
    """Independent farthest-point sampling; CPU NumPy avoids a CUDA extension."""
    array = points.detach().cpu().numpy()
    batches = np.zeros(len(array),dtype=np.int64) if batch is None else batch.detach().cpu().numpy()
    result=[]
    for value in np.unique(batches):
        indices=np.flatnonzero(batches==value); cloud=array[indices]
        count=min(len(cloud),int(np.ceil(len(cloud)*ratio)))
        nearest=np.full(len(cloud),np.inf)
        next_index=int(torch.randint(len(cloud),(1,)).item()) if random_start else 0
        for _ in range(count):
            result.append(indices[next_index]); delta=cloud-cloud[next_index]
            nearest=np.minimum(nearest,np.einsum('ij,ij->i',delta,delta));next_index=int(nearest.argmax())
    return torch.tensor(result,dtype=torch.long,device=points.device)


def upstream_module(name, code):
    module=types.ModuleType(name);sys.modules[name]=module;exec(compile(code,name,'exec'),module.__dict__)
    return module


def load_implementation(source, hashes, parents):
    texts={}
    for name, expected in hashes.items():
        raw=(source/name).read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('MIA source changed after job preparation')
        texts[name]=raw.decode('utf-8')
    support=types.ModuleType('lc_mia_support');sys.modules[support.__name__]=support
    support.fps=fps
    support.find_ckpt=lambda path,**_:path
    # DropPath is inactive in eval; fail if an upstream change tries training.
    class DropPath(torch.nn.Module):
        def __init__(self,*args,**kwargs):super().__init__()
        def forward(self,x):
            if self.training:raise RuntimeError('MIA adapter is inference-only')
            return x
    support.DropPath=DropPath
    dataset=texts['util/dataset_mixamo.py'];tree=ast.parse(dataset)
    names=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='MIXAMO_JOINTS' for t in n.targets)))
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Joint')
    joint_code='from dataclasses import dataclass\nfrom functools import cached_property\nfrom typing import Self,Iterator\n@dataclass(frozen=True)\n'+ast.get_source_segment(dataset,node)
    exec(compile(joint_code,'MIA MIT Joint class','exec'),support.__dict__)
    nodes={name:support.Joint(name,i,None,[],names) for i,name in enumerate(names)}
    for name,node in nodes.items():
        parent=parents[name.rsplit(':',1)[-1]]
        if parent and parent!='Root':
            object.__setattr__(node,'parent',nodes['mixamorig:'+parent]);node.parent.children.append(node)
    root=nodes['mixamorig:Hips']
    ae=texts['models_ae.py'].replace('from torch_cluster import fps','from lc_mia_support import fps').replace('from timm.layers import DropPath','from lc_mia_support import DropPath')
    upstream_module('lc_mia_ae',ae)
    code=texts['model.py'].replace('from torch_cluster import fps','from lc_mia_support import fps').replace('from models_ae import','from lc_mia_ae import').replace('from util.dataset_mixamo import Joint','from lc_mia_support import Joint').replace('from util.utils import find_ckpt','from lc_mia_support import find_ckpt')
    model=upstream_module('lc_mia_model',code)
    return model.PCAE,root,[name.rsplit(':',1)[-1] for name in names]


def sample_surface(vertices, triangles, count, rng):
    faces=vertices[triangles];areas=np.linalg.norm(np.cross(faces[:,1]-faces[:,0],faces[:,2]-faces[:,0]),axis=1)
    if not np.isfinite(areas).all() or areas.sum()<=0:raise ValueError('Invalid placement surface')
    indices=rng.choice(len(faces),size=count,p=areas/areas.sum());chosen=faces[indices]
    uv=rng.random((count,2));uv[uv.sum(axis=1)>1]=1-uv[uv.sum(axis=1)>1]
    return chosen[:,0]+uv[:,:1]*(chosen[:,1]-chosen[:,0])+uv[:,1:]*(chosen[:,2]-chosen[:,0])


def sample_box_surface(vertices,triangles,center,extent,count,rng):
    """Area-weighted sampling of triangles clipped to the same hand box as upstream."""
    lo=center-extent/2;hi=center+extent/2;faces=vertices[triangles]
    candidates=faces[(faces.max(axis=1)>=lo).all(axis=1)&(faces.min(axis=1)<=hi).all(axis=1)]
    pieces=[]
    for triangle in candidates:
        polygon=list(triangle)
        for axis,bound,sign in [(a,lo[a],1) for a in range(3)]+[(a,hi[a],-1) for a in range(3)]:
            clipped=[]
            for i,current in enumerate(polygon):
                previous=polygon[i-1];d0=sign*(previous[axis]-bound);d1=sign*(current[axis]-bound)
                if (d0>=0)!=(d1>=0):clipped.append(previous+(current-previous)*(d0/(d0-d1)))
                if d1>=0:clipped.append(current)
            polygon=clipped
            if len(polygon)<3:break
        for i in range(1,len(polygon)-1):pieces.append((polygon[0],polygon[i],polygon[i+1]))
    if not pieces:return sample_surface(vertices,triangles,count,rng)
    clipped=np.asarray(pieces).reshape(-1,3)
    return sample_surface(clipped,np.arange(len(clipped)).reshape(-1,3),count,rng)


def load_model(PCAE, cache, name, **options):
    path=cache/'models'/name
    with path.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=MODEL_HASHES[name]:raise ValueError('Original MIA checkpoint hash mismatch')
    # Known inert training arguments are allowed; arbitrary checkpoint classes
    # or unsafe pickle deserialization are never enabled.
    with torch.serialization.safe_globals([argparse.Namespace]):
        checkpoint=torch.load(path,map_location='cpu',weights_only=True)
    model=PCAE(N=32768,input_normal=False,deterministic=True,output_dim=52,
        predict_bw=False,predict_joints=True,predict_joints_tail=True,**options)
    model.load_state_dict(model.adapt_ckpt(checkpoint['model']),strict=True)
    return model.cuda().eval()


def guided_decoder(model,names,request,center,scale,hips,rotation,fine_scale):
    """Owned inference adapter: constrain each accepted parent before children.

    Unchanged pretrained parameters; upstream source is never edited. Front
    guides preserve predicted depth. Exact artist locks constrain both ends.
    """
    front=request.get('front_guides',{});locks=request.get('joint_constraints',{});guides=request.get('finger_guides',{})
    if not front and not locks and not guides:return
    head=model.joints_head
    def forward(self,feat,out_gt=None):
        batch,count,_=feat.shape
        out=torch.zeros((batch,count,self.out_dim),dtype=feat.dtype,device=feat.device)
        rot=torch.as_tensor(rotation,dtype=feat.dtype,device=feat.device)
        hip=torch.as_tensor(hips,dtype=feat.dtype,device=feat.device)
        ctr=torch.as_tensor(center,dtype=feat.dtype,device=feat.device)
        for mask in self.tree_levels_mask:
            if not bool(mask.any()):continue
            predicted=self._forward(feat,out)
            out[mask.expand(batch,-1)]=predicted[mask.expand(batch,-1)]
            for i,name in enumerate(names):
                if not bool(mask[0,i] if mask.ndim==2 else mask[i]):continue
                tip=name[:-1]+('Tip' if name.endswith('3') else str(int(name[-1])+1)) if 'Hand' in name and name[-1:] in '123' else None
                if name not in front and name not in locks and name not in guides and tip not in guides:continue
                world=((out[:,i].reshape(batch,2,3)/fine_scale)@rot+hip)/scale+ctr
                if name in locks:
                    world[:]=torch.as_tensor([locks[name]['head'],locks[name]['tail']],dtype=feat.dtype,device=feat.device)
                elif name in front:
                    point=torch.as_tensor(front[name],dtype=feat.dtype,device=feat.device)
                    delta=point[:2]-world[:,0,:2];world[:,:,:2]+=delta[:,None,:]
                if name not in locks:
                    if name in guides:world[:,0]=torch.as_tensor(guides[name],dtype=feat.dtype,device=feat.device)
                    if tip in guides:world[:,1]=torch.as_tensor(guides[tip],dtype=feat.dtype,device=feat.device)
                out[:,i]=(((world-ctr)*scale-hip)@rot.T*fine_scale).reshape(batch,6)
        return out
    head.forward=types.MethodType(forward,head)


def run(folder):
    folder=Path(folder).resolve();request=json.loads((folder/'request.json').read_text())
    if request['provider']!='mia_original_landmarks' or request['schema_version']!=1:raise ValueError('Unknown placement protocol')
    if request['source_hashes']!=SOURCE_HASHES:raise ValueError('Unpinned MIA source request')
    path=folder/'input.npz'
    with zipfile.ZipFile(path) as archive:
        if sum(e.file_size for e in archive.infolist())>128*1024**2:raise ValueError('Placement input exceeds its array memory budget')
    if hashlib.sha256(path.read_bytes()).hexdigest()!=request['input_sha256']:raise ValueError('Placement input changed')
    with np.load(path,allow_pickle=False) as arrays:vertices=arrays['vertices'];triangles=arrays['triangles']
    if vertices.ndim!=2 or vertices.shape[1]!=3 or not len(vertices) or not np.isfinite(vertices).all() or triangles.ndim!=2 or triangles.shape[1]!=3 or not len(triangles) or triangles.dtype.kind not in 'iu' or triangles.min()<0 or triangles.max()>=len(vertices):raise ValueError('Invalid placement geometry')
    cache=Path(request['provider_cache']);PCAE,tree,names=load_implementation(cache/'source',request['source_hashes'],request['parents'])
    torch.manual_seed(request['seed']);rng=np.random.default_rng(request['seed']);torch.set_num_threads(8)
    if not torch.cuda.is_available():raise ValueError('Original MIA placement needs a CUDA GPU')
    torch.cuda.reset_peak_memory_stats();started=time.monotonic()
    points=sample_surface(vertices,triangles,32768,rng).astype(np.float32)
    center=(points.min(axis=0)+points.max(axis=0))*.5;scale=2/float(np.ptp(points,axis=0).max())
    points=(points-center)*scale
    with torch.inference_mode():
        model=load_model(PCAE,cache,'joints_coarse.pth')
        coarse=model(torch.from_numpy(points[None]).cuda()).joints[0].cpu().numpy()
        del model;torch.cuda.empty_cache()
        hips=coarse[names.index('Hips'),:3]
        right=coarse[names.index('RightUpLeg'),:3]-hips;left=coarse[names.index('LeftUpLeg'),:3]-hips
        z=np.cross(right,left);z/=max(np.linalg.norm(z),1e-12)
        x=left-right;x-=z*(x@z);x/=max(np.linalg.norm(x),1e-12)
        y=np.cross(z,x);rotation=np.stack((x,y,z))
        if not np.isfinite(rotation).all() or abs(np.linalg.det(rotation)-1)>1e-3:raise ValueError('Ambiguous predicted hips frame; use markers')
        # Geometry-only hand oversampling, preserving the upstream 50/50 split.
        canonical=(vertices-center)*scale;canonical=(canonical-hips)@rotation.T
        whole=sample_surface(canonical,triangles,16384,rng)
        centers=(coarse[[names.index('LeftHand'),names.index('RightHand')],3:]-hips)@rotation.T
        for i,side in enumerate(('Left','Right')):
            name=side+'Hand';constraint=request.get('joint_constraints',{}).get(name)
            if constraint:
                palm=(np.asarray(constraint['head'])+np.asarray(constraint['tail']))/2
                centers[i]=((palm-center)*scale-hips)@rotation.T
            elif name in request.get('front_guides',{}):
                wrist=coarse[names.index(name),:3]/scale+center
                palm=coarse[names.index(name),3:]/scale+center
                delta=np.asarray(request['front_guides'][name])[:2]-wrist[:2];palm[:2]+=delta
                centers[i]=((palm-center)*scale-hips)@rotation.T
        radius=.15*float(canonical.max()-canonical.min())
        hands=[sample_box_surface(canonical,triangles,hand,radius,8192,rng) for hand in centers]
        points=np.concatenate([whole,*hands]).astype(np.float32)
        # Upstream performs a second isotropic normalization around the hips,
        # without recentering, after hand resampling. Retain its inverse in
        # the output mapping; the fine model was trained in this unit box.
        fine_scale=1/float(np.abs(points).max())
        points*=fine_scale
        model=load_model(PCAE,cache,'joints.pth',hierarchical_ratio=.5,kinematic_tree=tree,joints_attn_causal=True)
        guided_decoder(model,names,request,center,scale,hips,rotation,fine_scale)
        predicted=model(torch.from_numpy(points[None]).cuda()).joints[0].cpu().numpy()
        predicted=(predicted.reshape((52,2,3))/fine_scale)@rotation+hips
        predicted=predicted/scale+center
        if not np.isfinite(predicted).all():raise ValueError('Nonfinite joint proposal')
        result=dict(schema_version=1,provider=request['provider'],names=names,heads=predicted[:,0].tolist(),tails=predicted[:,1].tolist(),
            coordinate_space='world_meters_gltf_y_up',seed=request['seed'],elapsed_seconds=time.monotonic()-started,
            torch_version=torch.__version__,cuda_version=torch.version.cuda,device=torch.cuda.get_device_name(),
            peak_allocated_vram_bytes=torch.cuda.max_memory_allocated(),peak_reserved_vram_bytes=torch.cuda.max_memory_reserved(),
            fps_backend='independent_numpy_farthest_point',reference_equivalence='not_yet_measured')
        result['normalization']='centered_coarse_then_hips_origin_fine_unit_box'
        result['hand_sampling']='area_weighted_exact_triangle_box_clipping'
        result['guided_parent_prediction']=bool(request.get('front_guides') or request.get('joint_constraints') or request.get('finger_guides'))
        if request.get('hand_fit',False):
            fit_started=time.monotonic()
            spec=importlib.util.spec_from_file_location('lc_hand_geometry',Path(__file__).with_name('hand_geometry.py'))
            geometry=importlib.util.module_from_spec(spec);spec.loader.exec_module(geometry)
            fitted_heads,fitted_tails,report=geometry.refine(vertices,triangles,names,predicted[:,0],predicted[:,1],
                request.get('locked_digits',[]),request.get('finger_guides',{}))
            result['neural_heads']=result['heads'];result['neural_tails']=result['tails']
            result['heads']=fitted_heads.tolist();result['tails']=fitted_tails.tolist();result['hand_report']=report
            result['geometry_seconds']=time.monotonic()-fit_started
        result['elapsed_seconds']=time.monotonic()-started
    (folder/'output.json').write_text(json.dumps(result,indent=2,allow_nan=False));print('LOCAL_CHARACTER_MIA_PROPOSED',result['elapsed_seconds'],flush=True)


if __name__=='__main__':run(sys.argv[1])
