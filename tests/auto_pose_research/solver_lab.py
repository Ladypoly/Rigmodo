# SPDX-License-Identifier: GPL-3.0-or-later
"""Offline comparison of two ORIGINAL SMALL PROTOTYPES, not production solvers.

Run in Blender background; mathutils is its bundled CPU math library.
PBD-like graph relaxation vs sequential, multi-chain FABRIK-style baseline.
Neither is an implementation/benchmark of the complete published algorithms.
"""
import importlib.util,json,math,statistics,sys,time
from pathlib import Path
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('lab_skeleton',ROOT/'skeleton.py')
skeleton=importlib.util.module_from_spec(spec);sys.modules[spec.name]=skeleton;spec.loader.exec_module(skeleton)

class Model:
    def __init__(self,height=1.75,arm_scale=1.):
        self.height=height;self.names=[];self.rest=[];self.parents={};self.edges=[];self.clusters=[]
        bones={b.name:b for b in skeleton.template(height,20)}
        core=['Hips','Spine','Spine1','Spine2','Neck','Head']
        for side in ('Left','Right'):core += [side+p for p in ('Shoulder','Arm','ForeArm','Hand','UpLeg','Leg','Foot','ToeBase')]
        for name in core:self.add(name,bones[name].head)
        for name in core:
            parent=bones[name].parent
            if parent in self.names:self.parents[name]=parent;self.edge(parent,name)
        for name in ('Head','LeftHand','RightHand','LeftToeBase','RightToeBase'):
            end=name+'_end';self.add(end,bones[name].tail);self.parents[end]=name;self.edge(name,end)
        self.add('pelvis_forward',Vector(bones['Hips'].head)+Vector((0,-.08*height,0)))
        self.add('chest_forward',Vector(bones['Spine2'].head)+Vector((0,-.08*height,0)))
        self.clusters=[['Hips','Spine','LeftUpLeg','RightUpLeg','pelvis_forward'],['Spine2','Neck','LeftShoulder','RightShoulder','chest_forward']]
        for cluster in self.clusters:
            for i,a in enumerate(cluster):
                for b in cluster[i+1:]:self.edge(a,b)
        if arm_scale!=1:
            for side in ('Left','Right'):
                base=self.rest[self.idx(side+'Arm')].copy()
                for part in ('ForeArm','Hand','Hand_end'):
                    i=self.idx(side+part);self.rest[i]=base+(self.rest[i]-base)*arm_scale
        self.edges=[(a,b,(self.rest[a]-self.rest[b]).length) for a,b,_ in self.edges]
        self.arms={s:[s+'Arm',s+'ForeArm',s+'Hand'] for s in ('Left','Right')}
        self.legs={s:[s+'UpLeg',s+'Leg',s+'Foot'] for s in ('Left','Right')}
        self.poles={s+'ForeArm':Vector((0,.8,-.3)).normalized() for s in ('Left','Right')}
        self.poles.update({s+'Leg':Vector((0,-1,0)) for s in ('Left','Right')})
    def add(self,name,point):self.names.append(name);self.rest.append(Vector(point))
    def idx(self,name):return self.names.index(name)
    def edge(self,a,b):
        i,j=self.idx(a),self.idx(b)
        if not any({x,y}=={i,j} for x,y,_ in self.edges):self.edges.append((i,j,(self.rest[i]-self.rest[j]).length))
    def path(self,name):
        result=[name]
        while result[0] in self.parents:result.insert(0,self.parents[result[0]])
        return [self.idx(n) for n in result]

def length_project(p,edges,mobility,reverse=False):
    for a,b,length in reversed(edges) if reverse else edges:
        v=p[b]-p[a];distance=v.length;total=mobility[a]+mobility[b]
        if distance<1e-12 or total==0:continue
        correction=v*((distance-length)/(distance*total))
        p[a]+=correction*mobility[a];p[b]-=correction*mobility[b]

def bend(model,p,pins):
    # Exact two-bone projection, known pole; endpoints stay fixed.
    for chain in [*model.arms.values(),*model.legs.values()]:
        a,b,c=[model.idx(n) for n in chain]
        if b in pins:continue
        l1=(model.rest[b]-model.rest[a]).length;l2=(model.rest[c]-model.rest[b]).length
        v=p[c]-p[a];d=v.length
        if d<1e-9 or d>=l1+l2-1e-7 or d<=abs(l1-l2)+1e-7:continue
        axis=v/d;along=(l1*l1-l2*l2+d*d)/(2*d);h=math.sqrt(max(0,l1*l1-along*along))
        pole=model.poles[chain[1]];pole=(pole-axis*pole.dot(axis)).normalized()
        if pole.length<1e-7:continue
        p[b]=p[a]+axis*along+pole*h

def mobility_for(model,active,follow):
    # Body stiffness is artistic resistance, NOT physical mass.
    path=model.path(active);distances=[100]*len(model.names);front={model.idx(active)};d=0
    adjacency=[set() for _ in model.names]
    for a,b,_ in model.edges:adjacency[a].add(b);adjacency[b].add(a)
    while front:
        for i in front:distances[i]=d
        front={j for i in front for j in adjacency[i] if distances[j]==100};d+=1
    result=[]
    for i,name in enumerate(model.names):
        limb=any(x in name for x in ('ForeArm','Hand','Leg','Foot','Toe'))
        base=1. if limb else .12+follow*.88
        result.append(base*(.35+.65*math.exp(-distances[i]/4)))
    return result

def relax(model,active,target,pin_names=(),iterations=48,order='symmetric',bends=True,target_mobility=1.):
    p=[v.copy() for v in model.rest];i=model.idx(active);target=Vector(target)
    pins={model.idx(n):model.rest[model.idx(n)].copy() for n in pin_names}
    limb=model.arms.get('Left' if active.startswith('Left') else 'Right') if 'Hand' in active else None
    pressure=0.
    if limb:
        a,b,c=[model.idx(n) for n in limb];reach=(model.rest[a]-model.rest[b]).length+(model.rest[b]-model.rest[c]).length
        pressure=max(0.,min(1.,((target-model.rest[a]).length/reach-.8)/.5))
    mobility=mobility_for(model,active,pressure)
    mobility[i]*=target_mobility
    for j in pins:mobility[j]=0.
    # Soft preferences target invocation pose; stiffness corrected for iteration budget.
    anchor=1-(1-.25)**(1/iterations)
    for it in range(iterations):
        for j in range(len(p)):
            if j not in pins and j!=i:p[j]+=(model.rest[j]-p[j])*anchor*(1-mobility[j]*.5)
        if i not in pins:p[i]+=(target-p[i])*.8
        length_project(p,model.edges,mobility,reverse=(order=='reverse'))
        if order=='symmetric':length_project(p,model.edges,mobility,reverse=True)
        if bends:bend(model,p,pins)
        for j,v in pins.items():p[j]=v.copy()
    # Finish with feasibility, not an unconditional active-target snap.
    for it in range(48):
        length_project(p,model.edges,mobility,reverse=bool(it%2))
        if bends:bend(model,p,pins)
    return p

def fabrik_chain(p,chain,target,lengths,base_fixed=True):
    if len(chain)<2:
        if chain:p[chain[0]]=Vector(target)
        return
    base=p[chain[0]].copy();target=Vector(target);total=sum(lengths)
    if base_fixed and (target-base).length>total:
        axis=(target-base).normalized();p[chain[0]]=base
        for a,b,length in zip(chain,chain[1:],lengths):p[b]=p[a]+axis*length
        return
    p[chain[-1]]=target
    for k in range(len(chain)-2,-1,-1):
        a,b=chain[k:k+2];v=(p[a]-p[b]).normalized();p[a]=p[b]+v*lengths[k]
    if base_fixed:p[chain[0]]=base
    for k in range(len(chain)-1):
        a,b=chain[k:k+2];v=(p[b]-p[a]).normalized();p[b]=p[a]+v*lengths[k]

def fabrik(model,active,target,pin_names=(),iterations=48,reverse=False):
    p=[v.copy() for v in model.rest];tasks=[(active,Vector(target))]+[(n,model.rest[model.idx(n)]) for n in pin_names]
    if reverse:tasks.reverse()
    for it in range(iterations):
        for name,goal in tasks:
            chain=model.path(name);lengths=[(model.rest[a]-model.rest[b]).length for a,b in zip(chain,chain[1:])]
            fabrik_chain(p,chain,goal,lengths,base_fixed=(name not in pin_names))
        # Seed known bend preferences, but shared junction arbitration is absent.
        bend(model,p,{model.idx(n) for n in pin_names})
    return p

def metrics(model,p,active,target,pins):
    def delta(name):return (p[model.idx(name)]-model.rest[model.idx(name)]).length/model.height
    lengths=[abs((p[a]-p[b]).length-length)/max(length,1e-9) for a,b,length in model.edges]
    return dict(target_error_h=(p[model.idx(active)]-Vector(target)).length/model.height,
        max_pin_error_h=max([(p[model.idx(n)]-model.rest[model.idx(n)]).length/model.height for n in pins] or [0.]),
        max_length_relative_error=max(lengths),pelvis_delta_h=delta('Hips'),chest_delta_h=delta('Spine2'),
        left_elbow_delta_h=delta('LeftForeArm'),left_knee_delta_h=delta('LeftLeg'),finite=all(math.isfinite(v) for q in p for v in q))

def cases(model):
    r=lambda n:model.rest[model.idx(n)].copy();h=model.height
    feet=['LeftFoot','RightFoot']
    return [('small_hand','LeftHand',r('LeftHand')+Vector((-.04,-.035,0))*h,feet),
        ('far_hand','LeftHand',r('LeftHand')+Vector((.15,-.12,0))*h,feet),
        ('extreme_arm','LeftHand',r('LeftHand')+Vector((1.4,0,0))*h,feet),
        ('pelvis_down','Hips',r('Hips')+Vector((0,0,-.10))*h,feet),
        ('pelvis_sideways','Hips',r('Hips')+Vector((.12,0,0))*h,feet),
        ('one_foot','Hips',r('Hips')+Vector((.12,0,-.10))*h,['LeftFoot']),
        ('pinned_hand','Hips',r('Hips')+Vector((0,0,-.08))*h,['LeftHand']),
        ('multiple_pins','Hips',r('Hips')+Vector((0,0,-.06))*h,feet+['RightHand']),
        ('extreme_leg','LeftFoot',r('LeftFoot')+Vector((.9,0,-.6))*h,['Hips','RightFoot']),
        ('elbow_bending','LeftHand',r('LeftHand')+Vector((-.18,-.12,0))*h,feet),
        ('knee_bending','Hips',r('Hips')+Vector((0,0,-.13))*h,feet),
        ('target_is_pinned','LeftHand',r('LeftHand')+Vector((.2,0,0))*h,feet+['LeftHand'])]

def main():
    out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
    model=Model();rows=[]
    for label,active,target,pins in cases(model):
        for algorithm,fn in [('relax',relax),('fabrik_style',fabrik)]:
            timings=[]
            for sample in range(12):
                start=time.perf_counter();p=fn(model,active,target,pins);timings.append((time.perf_counter()-start)*1000)
            row=dict(case=label,algorithm=algorithm,median_solve_ms=statistics.median(timings),p95_solve_ms=float(np.percentile(timings,95)),
                **metrics(model,p,active,target,pins));rows.append(row)
    variants=[]
    for height,arm_scale in ((.875,1),(3.5,1),(1.75,.65),(1.75,1.4)):
        m=Model(height,arm_scale)
        for label,active,target,pins in cases(m)[:2]:variants.append(dict(height=height,arm_scale=arm_scale,case=label,**metrics(m,relax(m,active,target,pins),active,target,pins)))
    order=[]
    for name,fn,kwargs in [('forward',relax,dict(order='forward')),('reverse',relax,dict(order='reverse')),('symmetric',relax,{}),
        ('fabrik_tasks_forward',fabrik,{}),('fabrik_tasks_reverse',fabrik,dict(reverse=True))]:
        label,active,target,pins=cases(model)[7];p=fn(model,active,target,pins,**kwargs);order.append(dict(order=name,**metrics(model,p,active,target,pins)))
    iteration=[]
    for n in (8,16,32,48,96):
        _,active,target,pins=cases(model)[1];start=time.perf_counter();p=relax(model,active,target,pins,iterations=n)
        iteration.append(dict(iterations=n,solve_ms=(time.perf_counter()-start)*1000,**metrics(model,p,active,target,pins)))
    assert all(row['finite'] for row in rows+variants+order+iteration)
    assert all(row['max_pin_error_h']==0 for row in rows if row['algorithm']=='relax')
    weights=[]
    for factor in (.02,.2,1.):
        for label,active,target,pins in cases(model)[1:3]:
            p=relax(model,active,target,pins,target_mobility=factor)
            weights.append(dict(case=label,target_mobility=factor,**metrics(model,p,active,target,pins)))
    report=dict(scope='original research prototypes; no learned model, gravity, dynamics, collisions or general anatomical limits',
        solver_joints=len(model.names),constraints=len(model.edges),fixed_polishing_sweeps=48,
        rows=rows,proportions=variants,ordering=order,iterations=iteration,target_weights=weights)
    (out/'solver-results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('SOLVER_LAB_COMPLETE',json.dumps(dict(joints=len(model.names),rows=len(rows),out=str(out))),flush=True)

if __name__=='__main__':main()
