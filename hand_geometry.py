# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent conservative hand fitting from closed mesh cross-sections.

No vendor implementation, learned hand template or licensed anatomical data.
AI identifies digits. Geometry supplies candidate interior centres; ambiguous
or open sections retain the proposal. This is not anatomical ground truth.
"""
import math
import numpy as np

FINGERS=('Thumb','Index','Middle','Ring','Pinky')

def digit(name):
    return any(name==side+'Hand'+finger+str(i) for side in ('Left','Right') for finger in FINGERS for i in (1,2,3))

def unit(vector):
    length=np.linalg.norm(vector)
    return vector/max(length,1e-12)

def sections(faces,origin,normal,tolerance):
    """Closed contours and their area centroids in a slicing plane."""
    normal=unit(normal)
    distances=(faces-origin)@normal
    candidates=faces[(distances.min(axis=1)<-tolerance)&(distances.max(axis=1)>tolerance)]
    segments=[]
    for triangle in candidates:
        d=(triangle-origin)@normal;hits=[]
        for i,j in ((0,1),(1,2),(2,0)):
            if (d[i]<0)!=(d[j]<0):hits.append(triangle[i]+(triangle[j]-triangle[i])*d[i]/(d[i]-d[j]))
        if len(hits)==2 and np.linalg.norm(hits[0]-hits[1])>tolerance:segments.append(hits)
    adj={};positions={}
    for a,b in segments:
        keys=[]
        for p in (a,b):
            key=tuple(np.rint(p/tolerance).astype(np.int64));keys.append(key)
            positions.setdefault(key,[]).append(p);adj.setdefault(key,set())
        if keys[0]!=keys[1]:adj[keys[0]].add(keys[1]);adj[keys[1]].add(keys[0])
    axis=unit(np.cross(normal,np.eye(3)[np.argmin(abs(normal))]));other=np.cross(normal,axis)
    result=[];seen=set()
    for start in adj:
        if start in seen:continue
        stack=[start];component=set()
        while stack:
            key=stack.pop()
            if key in component:continue
            component.add(key);stack.extend(adj[key]-component)
        seen|=component
        if len(component)<3 or any(len(adj[k])!=2 for k in component):continue
        order=[start];previous=None;current=start
        while True:
            nxt=next(k for k in adj[current] if k!=previous)
            if nxt==start:break
            if nxt in order:break
            order.append(nxt);previous,current=current,nxt
        if len(order)!=len(component):continue
        points=np.asarray([np.mean(positions[k],axis=0) for k in order])-origin
        xy=np.stack((points@axis,points@other),axis=1);following=np.roll(xy,-1,axis=0)
        cross=xy[:,0]*following[:,1]-following[:,0]*xy[:,1];area=cross.sum()/2
        if abs(area)<=tolerance*tolerance:continue
        centroid=((xy+following)*cross[:,None]).sum(axis=0)/(6*area)
        # Area centroids outside strongly concave contours are unsafe.
        x,y=centroid;inside=False
        for p,q in zip(xy,following):
            if (p[1]>y)!=(q[1]>y) and x<(q[0]-p[0])*(y-p[1])/(q[1]-p[1])+p[0]:inside=not inside
        if not inside:continue
        result.append((origin+centroid[0]*axis+centroid[1]*other,math.sqrt(abs(area)/math.pi)))
    return result

def refine(vertices,triangles,names,heads,tails,locked=(),guides=None):
    """Return fitted heads/tails and explicit per-digit review diagnostics."""
    heads=np.asarray(heads,dtype=float).copy();tails=np.asarray(tails,dtype=float).copy()
    index={n:i for i,n in enumerate(names)};locked=set(locked);guides=guides or {}
    all_faces=np.asarray(vertices,dtype=float)[np.asarray(triangles,dtype=int)]
    size=float(np.ptp(vertices,axis=0).max());tolerance=max(size*1e-6,1e-7)
    reports=[]
    for side in ('Left','Right'):
        if side+'Hand' not in index:continue
        hand=heads[index[side+'Hand']];chains={}
        lengths=[]
        for finger in FINGERS:
            ids=[index[side+'Hand'+finger+str(i)] for i in (1,2,3)]
            points=np.vstack((heads[ids],tails[ids[-1]]));chains[finger]=(ids,points)
            lengths.append(np.linalg.norm(np.diff(points,axis=0),axis=1).sum())
        length=float(np.median(lengths));reach=max(np.linalg.norm(p-hand) for _,p in chains.values())+length*.4
        mask=(np.linalg.norm(all_faces.mean(axis=1)-hand,axis=1)<reach)
        faces=all_faces[mask];accepted=[]
        for finger,(ids,original) in chains.items():
            keys=[side+'Hand'+finger+str(i) for i in (1,2,3)]+[side+'Hand'+finger+'Tip']
            points=original.copy();support=0;ambiguous=0;fixed=set();resolved=set()
            for j,key in enumerate(keys):
                if key in guides:points[j]=guides[key];fixed.add(j)
            for j,i in enumerate(ids):
                if names[i] in locked:fixed|={j,j+1};points[j]=heads[i];points[j+1]=tails[i]
            # A fingertip guide provides a smooth initial correction of the chain.
            if 3 in fixed and keys[3] in guides:
                delta=points[3]-original[3]
                for j in (1,2):
                    if j not in fixed:points[j]+=delta*(j/3)
            # Search a common translation before moving individual pivots. Two
            # distal sections must support it, so a palm-only centroid cannot
            # pull one joint away from an otherwise coherent predicted chain.
            if not fixed:
                proposals=[]
                for j in (1,2):
                    direction=unit(original[j+1]-original[j-1])
                    for centre,radius in sections(faces,original[j],direction,tolerance):
                        delta=centre-original[j]
                        if not length*.018<radius<length*.23 or np.linalg.norm(delta)>length*.55:continue
                        shifted=original+delta;residual=0;valid_shift=True
                        for k in (1,2):
                            axis=unit(shifted[k+1]-shifted[k-1])
                            options=[p for p,r in sections(faces,shifted[k],axis,tolerance) if length*.018<r<length*.23]
                            error=min((np.linalg.norm(p-shifted[k]) for p in options),default=float('inf'))
                            if error>length*.075:valid_shift=False;break
                            residual+=error
                        if valid_shift and not any(np.linalg.norm(delta-d)<length*.12 for _,d in proposals):
                            proposals.append((np.linalg.norm(delta)+residual*2,delta))
                proposals.sort(key=lambda value:value[0])
                if proposals and (len(proposals)==1 or proposals[1][0]-proposals[0][0]>length*.055):points=original+proposals[0][1]
            for j in (0,1,2):
                if j in fixed:continue
                direction=unit(points[min(j+1,3)]-points[max(j-1,0)])
                candidates=sections(faces,points[j],direction,tolerance)
                candidates=[(p,r) for p,r in candidates if length*.018<r<length*.28 and np.linalg.norm(p-points[j])<length*.12]
                candidates.sort(key=lambda item:np.linalg.norm(item[0]-points[j]))
                if not candidates:ambiguous+=1;continue
                best,radius=candidates[0];distance=np.linalg.norm(best-points[j])
                if len(candidates)>1 and np.linalg.norm(candidates[1][0]-points[j])-distance<length*.035:
                    ambiguous+=1;continue
                points[j]=best;support+=1;resolved.add(j)
            # Follow the distal centreline toward its actual closed tip. The last
            # interior cross-section is an endpoint estimate, not a joint pivot.
            tip_supported=False
            if 3 not in fixed:
                direction=unit(points[3]-points[2]);base=points[2].copy();segment=np.linalg.norm(points[3]-base)
                samples=[]
                for distance in np.linspace(segment*.35,segment*1.65,18):
                    origin=base+direction*distance
                    options=[(p,r) for p,r in sections(faces,origin,direction,tolerance)
                        if length*.008<r<length*.23 and np.linalg.norm(p-origin)<length*.25]
                    if not options:
                        if samples:break
                        continue
                    options.sort(key=lambda item:np.linalg.norm(item[0]-origin))
                    if len(options)>1 and np.linalg.norm(options[1][0]-origin)-np.linalg.norm(options[0][0]-origin)<length*.025:break
                    samples.append((distance,options[0][0]))
                if samples and len(samples)>=3 and samples[-1][0]<segment*1.6:
                    points[3]=samples[-1][1];tip_supported=True
            before=np.linalg.norm(np.diff(original,axis=0),axis=1);after=np.linalg.norm(np.diff(points,axis=0),axis=1)
            valid=bool(np.isfinite(points).all() and np.all(after>size*1e-5) and
                np.all(after>=before*.45) and np.all(after<=before*1.7))
            if fixed:valid=bool(np.isfinite(points).all() and np.all(after>size*1e-5))
            if not fixed:
                for j in (1,2):
                    if np.dot(unit(points[j]-points[j-1]),unit(points[j+1]-points[j]))<-.35:valid=False
            # Avoid merging two identified digits onto one contour.
            collision=any(np.linalg.norm(points[2]-p[2])<length*.045 and np.linalg.norm(original[2]-o[2])>length*.09 for p,o in accepted)
            if collision and not fixed:valid=False
            if fixed and not valid:raise ValueError(side+' '+finger+' guides create a collapsed finger; adjust guides')
            # A single isolated section can be the palm or another digit.
            # Reject that entire automatic chain rather than creating a kink.
            supported=bool(fixed or {1,2}<=resolved)
            if valid and supported:
                accepted.append((points,original))
            else:points=original
            # The proposal always describes a connected three-segment chain,
            # even when no geometric correction is accepted.
            for j,i in enumerate(ids):
                if names[i] not in locked:heads[i]=points[j];tails[i]=points[j+1]
            reports.append(dict(side=side,finger=finger,section_support=support,tip_supported=tip_supported,
                accepted=bool(valid and supported),requires_review=bool(not valid or not {1,2}<=resolved),
                ambiguous_sections=ambiguous,maximum_shift_m=float(np.linalg.norm(points-original,axis=1).max()),
                reason='artist constraints; inspect articulation' if fixed else
                    ('ambiguous or insufficient distal sections' if not valid or not {1,2}<=resolved else 'two distal sections support fit; inspect articulation')))
    return heads,tails,reports
