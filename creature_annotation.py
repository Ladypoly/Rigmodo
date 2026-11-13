# SPDX-License-Identifier: GPL-3.0-or-later
"""Conservative offline anatomy hints from names, bilateral branches and rest geometry."""
import json,re
import numpy as np
from .unimate_geometry import label

WORDS=re.compile(r'\b(head|neck|spine|chest|pelvis|hip|tail|wing|fin|leg|thigh|shin|knee|ankle|foot|paw|shoulder|arm|elbow|wrist|hand|finger|thumb|claw|jaw|mandible|ear|eye|tentacle|antenna)\b',re.I)

def clean(name):
    text=re.sub(r'(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])',' ',label(name))
    return re.sub(r'^l\s+','Left ',re.sub(r'^r\s+','Right ',text,flags=re.I),flags=re.I)

def analyze(names,parents,heads,tails):
    heads=np.asarray(heads,dtype=float);tails=np.asarray(tails,dtype=float);parents=np.asarray(parents,dtype=int)
    n=len(names)
    if heads.shape!=(n,3) or tails.shape!=(n,3) or not np.isfinite(heads).all() or not np.isfinite(tails).all():raise ValueError('Invalid creature rest geometry')
    children=[[] for _ in names]
    for j,p in enumerate(parents):
        if p>=0:children[p].append(j)
    roots=np.flatnonzero(parents<0)
    if len(roots)!=1:raise ValueError('Automatic annotation needs one skeleton tree')
    root=int(roots[0]);labels=[clean(s) if WORDS.search(clean(s)) else '' for s in names]
    named={word:[i for i,s in enumerate(labels) if re.search(r'\b'+word+r'\b',s,re.I)] for word in ('head','tail','pelvis','hip','left','right')}
    points=np.vstack([heads,tails]);extent=max(float(np.ptp(points,axis=0).max()),1e-8)
    center=np.median(heads,axis=0);xy=points[:,:2]-points[:,:2].mean(0)
    eigen,axes=np.linalg.eigh(xy.T@xy);axis=np.r_[axes[:,-1],0.]
    forward=None;confidence='review';notes=[]
    def direction(v):
        v=np.asarray(v,dtype=float).copy();v[2]=0
        return v/np.linalg.norm(v) if np.linalg.norm(v)>extent*.03 else None
    # Anatomical side names resolve heading even on vertically stacked bipeds.
    if named['left'] and named['right']:
        left=heads[named['left']].mean(0)-heads[named['right']].mean(0)
        forward=direction(np.cross(left,(0,0,1)))
    if forward is None and named['head']:
        base=named['pelvis'] or named['hip'] or named['tail'][:1] or [root]
        forward=direction(heads[named['head']].mean(0)-heads[base].mean(0))
    if forward is not None:confidence='named'
    chains=[]
    for j,p in enumerate(parents):
        if p<0 or len(children[p])!=1:
            chain=[j]
            while len(children[chain[-1]])==1:chain.append(children[chain[-1]][0])
            chains.append(chain)
    # Raised, curling central chains distinguish a scorpion tail from an upright neck.
    side=np.cross((0,0,1),axis);tail=None
    for chain in chains:
        coords=np.vstack([heads[chain],tails[chain[-1]]]);steps=np.diff(coords,axis=0)@axis
        narrow=np.max(np.abs((coords-center)@side))<extent*.09
        curled=steps.min()<-extent*.025 and steps.max()>extent*.025
        if len(chain)>=4 and narrow and curled and np.ptp(coords[:,2])>extent*.22:
            if tail is None or len(chain)>len(tail):tail=chain
    if forward is None and tail:
        base=heads[tail[0]];body_parents=[j for j in range(n) if len(children[j])>=2]
        forward=direction(np.median(heads[body_parents],axis=0)-base) if body_parents else None
        if forward is not None:confidence='geometry'
    # A long bilateral body with one higher central neck offers a second geometric cue.
    if forward is None and eigen[-1]>eigen[0]*1.35:
        high=[c for c in chains if len(c)>=2 and abs((heads[c[0]]-center)@side)<extent*.12 and tails[c[-1],2]>center[2]+extent*.18]
        if len(high)==1:
            forward=direction(tails[high[0][-1]]-center)
            if forward is not None:confidence='geometry'
    if forward is None:
        notes.append('Facing is ambiguous; choose a direction in Motion options.')
        forward=axis
    left=np.cross((0,0,1),forward);lateral=extent*.035
    paired=[]
    for p in range(n):
        candidates=[j for j in children[p] if abs((heads[j]-heads[p])@left)>lateral]
        positive=[j for j in candidates if (heads[j]-heads[p])@left>0];negative=[j for j in candidates if (heads[j]-heads[p])@left<0]
        used=set()
        for j in positive:
            choices=[k for k in negative if k not in used]
            if not choices:continue
            mirror=heads[j]-2*((heads[j]-heads[p])@left)*left
            k=min(choices,key=lambda k:np.linalg.norm(heads[k]-mirror))
            if np.linalg.norm(heads[k]-mirror)>extent*.12:continue
            used.add(k)
            def branch(start):
                c=[start]
                while len(children[c[-1]])==1:c.append(children[c[-1]][0])
                return c
            paired.append((p,branch(j),branch(k)))
    body_parents=sorted({p for p,_,_ in paired},key=lambda p:heads[p]@forward,reverse=True)
    leg_pairs=[row for row in paired if len(row[1])>=2 and len(row[2])>=2 and
               max(tails[row[1][-1],2],tails[row[2][-1],2])<np.mean([heads[row[1][0],2],heads[row[2][0],2]])-extent*.06]
    frontmost=max((heads[p]@forward for p,_,_ in paired),default=0.)
    claw_pairs=[row for row in leg_pairs if tail and heads[row[0]]@forward>=frontmost-extent*.02 and len(row[1])>=4 and len(row[2])>=4]
    leg_pairs=[row for row in leg_pairs if row not in claw_pairs]
    support_parents=sorted({p for p,_,_ in leg_pairs},key=lambda p:heads[p]@forward,reverse=True)
    def assign(j,value):
        if not labels[j]:labels[j]=value
    assign(root,'Pelvis')
    for p in body_parents:assign(p,'Spine')
    if body_parents and not WORDS.search(clean(names[body_parents[0]])):labels[body_parents[0]]='Head'
    if tail:
        for j in tail:assign(j,'Tail')
        if not WORDS.search(clean(names[tail[-1]])):labels[tail[-1]]='Tail End'
    for p,lchain,rchain in paired:
        for chain,side_name in ((lchain,'Left'),(rchain,'Right')):
            if (p,lchain,rchain) in claw_pairs:parts=['Shoulder','Elbow','Wrist']+['Claw']*max(0,len(chain)-3);prefix=side_name
            elif (p,lchain,rchain) in leg_pairs:
                rank=support_parents.index(p);count=len(support_parents)
                where='Front' if rank==0 else 'Hind' if rank==count-1 else 'Middle'
                parts=['Hip','Knee']+['Ankle']*max(0,len(chain)-3)+['Foot'];prefix=side_name+' '+where
            elif len(chain)==1:parts=['Mandible' if tail and p==body_parents[0] else 'Limb'];prefix=side_name
            else:parts=['Wing']*len(chain);prefix=side_name;notes.append('Unclassified lateral chain: review wing/arm labels.')
            for j,part in zip(chain,parts):assign(j,prefix+' '+part)
    for j in range(n):
        if not labels[j]:labels[j]='Spine' if len(children[j]) else 'Bone'
    unknown=sum(s=='Bone' or s.endswith(' Limb') for s in labels)
    if unknown:notes.append(f'{unknown} joints have generic labels; review anatomy.')
    return dict(labels=labels,forward=forward.tolist(),confidence=confidence,notes=list(dict.fromkeys(notes)),unknown=unknown)

def annotate(rig):
    """Refresh automatic hints while preserving independently authored per-bone labels."""
    if rig.library or rig.data.library:raise ValueError('Make the rig local before annotating its joints')
    bones=list(rig.data.bones);indices={b.name:i for i,b in enumerate(bones)};linear=np.asarray(rig.matrix_world.to_3x3())
    try:old=json.loads(rig.get('lc_creature_annotation','{}')).get('automatic_labels',{})
    except (ValueError,TypeError):old={}
    names=[b.lc_unimate_label if b.lc_unimate_label and b.lc_unimate_label!=old.get(b.name) else b.name for b in bones]
    result=analyze(names,[indices[b.parent.name] if b.parent else -1 for b in bones],
        [linear@np.asarray(b.head_local) for b in bones],[linear@np.asarray(b.tail_local) for b in bones])
    try:old=json.loads(rig.get('lc_creature_annotation','{}')).get('automatic_labels',{})
    except (ValueError,TypeError):old={}
    automatic={}
    for bone,value in zip(bones,result['labels']):
        current=bone.lc_unimate_label.strip()
        if current and current!=old.get(bone.name):continue
        bone.lc_unimate_label=value;automatic[bone.name]=value
    result['automatic_labels']=automatic
    rig['lc_creature_annotation']=json.dumps(result,allow_nan=False)
    return result
