# SPDX-License-Identifier: GPL-3.0-or-later
"""UniMate rest-frame normalization and 12-feature FK recovery (no Blender/ML)."""
# Adapted from UniMate-B3D motion.py (MIT, copyright 2026 Linzhan Mou); see NOTICE.
import re
import numpy as np

AXES={'Y':(0,1,0),'-Y':(0,-1,0),'X':(1,0,0),'-X':(-1,0,0)}

def label(name):
    name=name.split(':')[-1]
    name=re.sub(r'^(DEF|ORG|MCH)[-_]','',name,flags=re.I)
    name=re.sub(r'([a-z])([A-Z])',r'\1 \2',name)
    name=re.sub(r'[._-]L$', ' left',name,flags=re.I)
    name=re.sub(r'[._-]R$', ' right',name,flags=re.I)
    return re.sub(r'[_.-]+',' ',name).strip()

def canonicalize(skeleton):
    parents=np.asarray(skeleton['parents'],dtype=np.int64);heads=np.asarray(skeleton['heads'],dtype=float)
    n=len(parents)
    if heads.shape!=(n,3) or not 5<=n<=71 or not np.isfinite(heads).all():raise ValueError('UniMate needs 5–71 finite joints, including end tips')
    if parents[0]!=-1 or any(p<0 or p>=j for j,p in enumerate(parents[1:],1)):raise ValueError('UniMate needs one parent-first tree')
    if len(skeleton['bone_names'])!=n or len(skeleton['labels'])!=n:raise ValueError('Incomplete skeleton labels')
    forward=np.asarray(skeleton['forward_vector'] if 'forward_vector' in skeleton else AXES[skeleton['forward']],dtype=float)
    if forward.shape!=(3,) or not np.isfinite(forward).all() or abs(forward[2])>1e-6 or np.linalg.norm(forward)<1e-6:raise ValueError('Invalid detected facing direction')
    forward=forward/np.linalg.norm(forward)
    basis=np.stack([np.cross((0,0,1),forward),(0,0,1),forward]);pos=heads@basis.T
    origin=np.array([pos[0,0],pos[:,1].min(),pos[0,2]])
    neighbors=[[] for _ in parents]
    for j,p in enumerate(parents[1:],1):
        length=float(np.linalg.norm(pos[j]-pos[p]));neighbors[j].append((p,length));neighbors[p].append((j,length))
    def farthest(start):
        distance={start:0.};queue=[start]
        for j in queue:
            for child,length in neighbors[j]:
                if child not in distance:distance[child]=distance[j]+length;queue.append(child)
        end=max(distance,key=distance.get);return end,distance[end]
    diameter=farthest(farthest(0)[0])[1]
    if diameter<1e-8:raise ValueError('Skeleton has no measurable length')
    scale=2/diameter;pos=(pos-origin)*scale;offsets=pos.copy();offsets[1:]-=pos[parents[1:]]
    return dict(parents=parents,positions=pos,offsets=offsets,basis=basis,origin=origin,scale=scale)

def decode(features,canonical):
    data=np.asarray(features,dtype=float);parents=canonical['parents'];frames=len(data);n=len(parents)
    if data.shape!=(frames,n,12) or not 2<=frames<=60 or not np.isfinite(data).all():raise ValueError('Invalid UniMate features')
    x=data[:,:,3:6];y=data[:,:,6:9];z=np.cross(x,y)
    nx=np.linalg.norm(x,axis=-1,keepdims=True);nz=np.linalg.norm(z,axis=-1,keepdims=True)
    if np.any(nx<1e-8) or np.any(nz<1e-8):raise ValueError('Degenerate generated rotations')
    x=x/nx;z=z/nz;hml=np.stack([x,np.cross(z,x),z],axis=-1)
    local=np.tile(np.eye(3),(frames,n,1,1))
    # UniMate stores parent rotations in child slots, including the first child of root.
    for j,p in enumerate(parents[1:],1):local[:,p]=hml[:,j]
    velocity=np.zeros((frames,3));velocity[1:,0]=data[:-1,0,9];velocity[1:,2]=data[:-1,0,11]
    root=np.cumsum(np.einsum('tji,tj->ti',hml[:,0],velocity),axis=0);root[:,1]=data[:,0,1]
    positions=np.zeros((frames,n,3));rotations=np.zeros((frames,n,3,3))
    for j,p in enumerate(parents):
        if p<0:rotations[:,j]=local[:,j];positions[:,j]=root
        else:
            rotations[:,j]=rotations[:,p]@local[:,j]
            positions[:,j]=positions[:,p]+np.einsum('tij,j->ti',rotations[:,p],canonical['offsets'][j])
    basis=canonical['basis']
    return (positions/canonical['scale']+canonical['origin'])@basis,basis.T@rotations@basis
