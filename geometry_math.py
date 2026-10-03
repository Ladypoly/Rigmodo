# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent bounded intrinsic-distance and closed-volume heat binding."""
from collections import defaultdict
import heapq
import math
import numpy as np


def distances(points,heads,tails):
    out=np.empty((len(points),len(heads)),dtype=np.float32)
    for i,(head,tail) in enumerate(zip(heads,tails)):
        d=tail-head;length=float(d@d)
        t=np.clip((points-head)@d/max(length,1e-16),0,1)
        out[:,i]=np.linalg.norm(points-head-t[:,None]*d,axis=1)
    return out


def field_from_distance(value,scale):
    floor=max(scale*1e-4,1e-8)
    value=np.maximum(value,floor)
    proposal=(value.min(axis=1,keepdims=True)/value)**4
    return (proposal/np.maximum(proposal.sum(axis=1,keepdims=True),1e-12)).astype(np.float32)


def geodesic(points,edges,heads,tails):
    n=len(points);edges=np.asarray(edges,dtype=np.int64).reshape((-1,2))
    if n>150000 or len(edges)>600000:raise ValueError('Geometric binding budget is 150,000 vertices and 600,000 edges per mesh')
    adjacency=[[] for _ in range(n)]
    extent=max(float(np.ptp(points,axis=0).max()),1e-6)
    for a,b in edges:
        cost=max(float(np.linalg.norm(points[a]-points[b])),extent*1e-8)
        adjacency[a].append((int(b),cost));adjacency[b].append((int(a),cost))
    components=[];visited=np.zeros(n,dtype=bool)
    for start in range(n):
        if visited[start]:continue
        stack=[start];visited[start]=True;component=[]
        while stack:
            vertex=stack.pop();component.append(vertex)
            for neighbor,_ in adjacency[vertex]:
                if not visited[neighbor]:visited[neighbor]=True;stack.append(neighbor)
        components.append(np.asarray(component,dtype=np.int64))
    euclidean=distances(points,heads,tails);intrinsic=np.full_like(euclidean,np.inf)
    for bone in range(len(heads)):
        queue=[]
        for component in components:
            local=euclidean[component,bone];minimum=float(local.min())
            # Every disconnected shell gets its own seed and its actual offset
            # to the bone. No distance shortcut is ever added between shells.
            seeds=component[local<=minimum+extent*1e-5]
            for vertex in seeds:
                cost=float(euclidean[vertex,bone]);intrinsic[vertex,bone]=cost;heapq.heappush(queue,(cost,int(vertex)))
        while queue:
            cost,vertex=heapq.heappop(queue)
            if cost>float(intrinsic[vertex,bone])+extent*1e-6:continue
            for neighbor,step in adjacency[vertex]:
                candidate=cost+step
                if candidate<float(intrinsic[neighbor,bone])-extent*1e-7:
                    intrinsic[neighbor,bone]=candidate;heapq.heappush(queue,(candidate,neighbor))
    return field_from_distance(intrinsic,extent),dict(surface_components=len(components),geodesic_vertices=n)


def closed_mesh(points,triangles):
    extent=max(float(np.ptp(points,axis=0).max()),1e-6);epsilon=extent*1e-7
    _,inverse=np.unique(np.rint(points/epsilon).astype(np.int64),axis=0,return_inverse=True)
    faces=inverse[triangles];edges=defaultdict(list)
    for a,b,c in faces:
        if len({int(a),int(b),int(c)})!=3:return False,'degenerate welded triangle'
        for u,v in ((a,b),(b,c),(c,a)):edges[tuple(sorted((int(u),int(v))))].append((int(u),int(v)))
    if any(len(entries)!=2 for entries in edges.values()):return False,'open or nonmanifold surface'
    if any(entries[0]!=entries[1][::-1] for entries in edges.values()):return False,'inconsistent surface winding'
    # Overlapping disconnected shells are ambiguous material volumes: a shirt
    # inside a body must not silently become an odd/even cavity.
    adjacency=defaultdict(list)
    for (a,b) in edges:adjacency[a].append(b);adjacency[b].append(a)
    seen=set();bounds=[]
    welded=np.zeros((inverse.max()+1,3));welded[inverse]=points
    for start in adjacency:
        if start in seen:continue
        stack=[start];seen.add(start);component=[]
        while stack:
            v=stack.pop();component.append(v)
            for other in adjacency[v]:
                if other not in seen:seen.add(other);stack.append(other)
        scope=welded[component];lo,hi=scope.min(axis=0),scope.max(axis=0)
        for other_lo,other_hi in bounds:
            if np.all(np.minimum(hi,other_hi)-np.maximum(lo,other_lo)>epsilon):return False,'overlapping closed shells need separate volume regions'
        bounds.append((lo,hi))
    return True,''


def volume(points,triangles,heads,tails,resolution=48,iterations=40):
    valid,reason=closed_mesh(points,triangles)
    if not valid:raise ValueError(reason)
    if not 24<=resolution<=64:raise ValueError('Volume resolution must be 24–64')
    lo=points.min(axis=0);hi=points.max(axis=0);cell=float((hi-lo).max())/resolution
    lo=lo-cell*2;shape=np.maximum(1,np.ceil((hi-lo)/cell).astype(int)+2)
    if int(np.prod(shape))>350000:raise ValueError('Volume grid exceeds 350,000 cells')
    rays=defaultdict(list)
    # Deterministic off-edge ray centers avoid coincident shared-edge hits.
    yz_shift=np.array((.500173,.500319))
    for face in points[triangles]:
        yz=face[:,1:];a,b,c=yz;den=float(np.cross(b-a,c-a))
        if abs(den)<cell*cell*1e-10:continue
        low=np.maximum(0,np.ceil((yz.min(axis=0)-lo[1:])/cell-yz_shift).astype(int))
        high=np.minimum(shape[1:]-1,np.floor((yz.max(axis=0)-lo[1:])/cell-yz_shift).astype(int))
        if (low>high).any():continue
        y,z=np.meshgrid(np.arange(low[0],high[0]+1),np.arange(low[1],high[1]+1),indexing='ij')
        ids=np.column_stack((y.ravel(),z.ravel()));p=lo[1:]+(ids+yz_shift)*cell
        d=p-a;ab=b-a;ac=c-a
        u=(d[:,0]*ac[1]-d[:,1]*ac[0])/den;v=(ab[0]*d[:,1]-ab[1]*d[:,0])/den
        inside=(u>=-1e-10)&(v>=-1e-10)&(u+v<=1+1e-10)
        x=face[0,0]+u*(face[1,0]-face[0,0])+v*(face[2,0]-face[0,0])
        for (iy,iz),ix in zip(ids[inside],x[inside]):rays[(int(iy),int(iz))].append(float(ix))
    occupancy=np.zeros(tuple(shape),dtype=bool)
    for (iy,iz),hits in rays.items():
        hits=sorted(hits);unique=[hits[0]]
        for hit in hits[1:]:
            if hit-unique[-1]>cell*1e-7:unique.append(hit)
        if len(unique)%2:raise ValueError('Unpaired volume intersections; inspect self-intersections or near-degenerate faces')
        centers=lo[0]+(np.arange(shape[0])+.5)*cell
        for entry,exit in zip(unique[::2],unique[1::2]):occupancy[:,iy,iz]|=(centers>entry)&(centers<exit)
    cells=np.argwhere(occupancy)
    if not 8<=len(cells)<=120000:raise ValueError('Volume occupancy is empty, too thin, or exceeds 120,000 interior cells')
    grid=np.full(tuple(shape),-1,dtype=np.int32);grid[tuple(cells.T)]=np.arange(len(cells))
    centers=lo+(cells+.5)*cell;distance=distances(centers,heads,tails)
    current=field_from_distance(distance,float((hi-lo).max()));seeds=distance.min(axis=1)<=cell*.8
    if not seeds.any():raise ValueError('No resolved interior bone seeds; increase resolution or use surface distance')
    fixed=current.copy();source=[];target=[]
    for axis in range(3):
        neighbor=cells.copy();neighbor[:,axis]+=1;valid=neighbor[:,axis]<shape[axis]
        ids=np.flatnonzero(valid);other=grid[tuple(neighbor[valid].T)];valid=other>=0
        source.extend(ids[valid]);target.extend(other[valid])
    a=np.asarray(source,dtype=np.int64);b=np.asarray(target,dtype=np.int64)
    source=np.concatenate((a,b));target=np.concatenate((b,a));degree=np.bincount(target,minlength=len(cells)).astype(np.float32)
    for _ in range(iterations):
        neighbors=np.zeros_like(current)
        for start in range(0,len(source),8192):np.add.at(neighbors,target[start:start+8192],current[source[start:start+8192]])
        mean=neighbors/np.maximum(degree[:,None],1)
        active=(degree>0)&~seeds;current[active]=.95*mean[active]+.05*fixed[active]
    # Surface samples may lie just outside an interior cell. Only nearby cells
    # are eligible; unresolved thin details retain the intrinsic solution.
    base=np.floor((points-lo)/cell).astype(int);chosen=np.full(len(points),-1,dtype=np.int32);best=np.full(len(points),np.inf)
    for dx in (-1,0,1):
        for dy in (-1,0,1):
            for dz in (-1,0,1):
                candidate=base+np.array((dx,dy,dz));valid=np.all((candidate>=0)&(candidate<shape),axis=1);ids=np.flatnonzero(valid)
                matches=grid[tuple(candidate[valid].T)];found=matches>=0;ids=ids[found];matches=matches[found]
                difference=np.linalg.norm(points[ids]-centers[matches],axis=1);better=difference<best[ids]
                chosen[ids[better]]=matches[better];best[ids[better]]=difference[better]
    return current,chosen,dict(volume_cells=len(cells),voxel_size=float(cell),resolved_surface_vertices=int((chosen>=0).sum()),
                              volume_seed_cells=int(seeds.sum()),volume_heat_iterations=iterations)


def solve(field,iterations,strength):
    try:from .weight_math import constrained_weights,surface_diffusion
    except ImportError:from weight_math import constrained_weights,surface_diffusion
    points=np.asarray(field['points'],dtype=np.float64);heads=np.asarray(field['heads'],dtype=np.float64);tails=np.asarray(field['tails'],dtype=np.float64)
    if points.shape!=(len(field['original']),3) or heads.shape!=(field['original'].shape[1],3) or tails.shape!=heads.shape or not all(np.isfinite(a).all() for a in (points,heads,tails)):
        raise ValueError('Invalid geometric correspondence')
    proposal,report=geodesic(points,field['edges'],heads,tails)
    method=int(field['geometry_method']);report['geometry_method']='GEODESIC'
    if method==2:
        try:
            values,indices,details=volume(points,np.asarray(field['triangles'],dtype=np.int64),heads,tails,int(field['voxel_resolution']),max(20,iterations))
            # Close digits always use intrinsic surface distance, even when the
            # body passes closed-volume checks at this resolution.
            use=(indices>=0)&~np.asarray(field['digit_surface'],dtype=bool)
            proposal[use]=values[indices[use]];report.update(details,geometry_method='VOXEL_WITH_SURFACE_DETAILS',surface_detail_vertices=int((~use).sum()))
        except ValueError as exc:report['volume_fallback_reason']=str(exc)
    proposal,_=surface_diffusion(proposal,field['edges'],field['conductance'],np.ones(len(points),dtype=bool),
        np.zeros(len(heads),dtype=bool),np.zeros(len(points),dtype=bool),field['allowed'],min(iterations,40),.25,field['seam_groups'])
    original=field['original'];bound=original.sum(axis=1)>0
    proposal[bound]=(1-strength)*original[bound]+strength*proposal[bound]
    protected=field['protected']|~field['editable']
    result=constrained_weights(proposal,original,field['locked'],protected,field['allowed'])
    report.update(editable_vertices=int((~protected).sum()),seam_constraint_conflicts=0,iterations=iterations,
                  maximum_weight_change=float(np.max(np.abs(result-original))))
    return result,report
