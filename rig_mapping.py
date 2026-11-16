# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit humanoid roles with conservative geometric suggestions."""
import json,re
import numpy as np
import bpy
from bpy.types import Operator
from . import motion_store,motion_jobs

CORE=('Hips','Head',*[side+part for side in ('Left','Right') for part in ('Arm','ForeArm','Hand','UpLeg','Leg','Foot')])
ROLES=('Root','Hips','Spine','Spine1','Spine2','Neck','Head',*[side+part for side in ('Left','Right') for part in ('Shoulder','Arm','ForeArm','Hand','UpLeg','Leg','Foot','ToeBase')])


def canonical(name):
    original=motion_store.canonical(name)
    clean=re.sub('[^a-z0-9]','',name.rsplit(':',1)[-1].lower())
    for prefix in ('def','jbip','bip001','bip'):
        if clean.startswith(prefix):clean=clean[len(prefix):];break
    for role in ROLES:
        if clean==role.lower() or clean=='c'+role.lower():return role
    parts={'upperarm':'Arm','lowerarm':'ForeArm','forearm':'ForeArm','hand':'Hand','upperleg':'UpLeg','thigh':'UpLeg','lowerleg':'Leg','shin':'Leg','calf':'Leg','foot':'Foot','toes':'ToeBase','toe':'ToeBase','shoulder':'Shoulder'}
    for marker,side in [('left','Left'),('right','Right'),('l','Left'),('r','Right')]:
        words=[clean[len(marker):] if clean.startswith(marker) else '',clean[:-len(marker)] if clean.endswith(marker) else '']
        for word in words:
            if word in parts:return side+parts[word]
    return {'pelvis':'Hips','chest':'Spine1','upperchest':'Spine2'}.get(clean,original)


def names(rig):
    overrides=json.loads(rig.get('lc_humanoid_roles','{}'))
    if not isinstance(overrides,dict) or any(role not in ROLES or not isinstance(name,str) or name not in rig.data.bones for role,name in overrides.items()):raise ValueError('Saved bone mapping is invalid; review Mapping')
    if len(set(overrides.values()))!=len(overrides):raise ValueError('A bone cannot fill two humanoid roles')
    assigned={name:role for role,name in overrides.items()}
    result=[]
    for bone in rig.data.bones:
        role=assigned.get(bone.name,canonical(bone.name))
        if role in overrides and overrides[role]!=bone.name:role=bone.name
        result.append(role)
    return result


def role_changed(self,context):
    if not context:return
    try:
        rig=motion_jobs.selected_rig(context);proposal=json.loads(rig.get('lc_role_suggestions','{}'))
        current={r:b.name for r,b in zip(names(rig),rig.data.bones)}
        self.mapping_bone=proposal.get(self.mapping_role,current.get(self.mapping_role,''))
    except (ValueError,AttributeError):self.mapping_bone=''


def suggestions(rig):
    bones=list(rig.data.bones);roles=names(rig);found={r:b.name for r,b in zip(roles,bones) if r in ROLES}
    # Geometry proposes roles for review; it never silently accepts left/right or facing.
    positions=np.array([b.head_local for b in bones]);low,high=positions.min(0),positions.max(0);height=max(high[2]-low[2],.01);center=(low+high)/2
    if 'Hips' not in found:
        candidates=[b for b in bones if len(b.children)>=2 and .32<(b.head_local.z-low[2])/height<.7]
        if candidates:found['Hips']=min(candidates,key=lambda b:abs((b.head_local.z-low[2])/height-.52)+abs(b.head_local.x-center[0])/height).name
    if 'Head' not in found:found['Head']=max(bones,key=lambda b:b.head_local.z-abs(b.head_local.x-center[0])*.5).name
    hips=rig.data.bones.get(found.get('Hips',''))
    if hips:
        for side,sign in [('Left',1),('Right',-1)]:
            legs=[b for b in hips.children_recursive if b.head_local.z<hips.head_local.z-height*.02 and (b.head_local.x-hips.head_local.x)*sign>height*.01]
            if legs:
                ankle=min(legs,key=lambda b:b.head_local.z);chain=list(reversed(ankle.parent_recursive))+[ankle]
                chain=[b for b in chain if b in legs and b.length>height*.06]
                if len(chain)>=2:
                    found.setdefault(side+'UpLeg',chain[0].name);found.setdefault(side+'Leg',chain[1].name)
                    found.setdefault(side+'Foot',next((b.name for b in chain[1].children if b.length>height*.01),ankle.name))
            hands=[b for b in hips.children_recursive if b.head_local.z>hips.head_local.z+height*.1 and (b.head_local.x-hips.head_local.x)*sign>height*.2]
            if hands:
                hand=max(hands,key=lambda b:(b.head_local.x-hips.head_local.x)*sign)
                chain=[b for b in reversed(hand.parent_recursive) if (b.head_local.x-hips.head_local.x)*sign>height*.07 and b.length>height*.06]
                if len(chain)>=2:
                    found.setdefault(side+'Arm',chain[0].name);found.setdefault(side+'ForeArm',chain[1].name)
                    found.setdefault(side+'Hand',next((b.name for b in chain[1].children if b.length>height*.015),hand.name))
    return found


class LC_OT_detect_roles(Operator):
    bl_idname='local_character.detect_motion_mapping';bl_label='Suggest Bone Mapping'
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);proposals=suggestions(rig);rig['lc_role_suggestions']=json.dumps(proposals);role_changed(context.scene.lc_settings,context)
            self.report({'INFO'},f'{len(proposals)} roles proposed; inspect the bone assignments before accepting')
        except (ValueError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_accept_roles(Operator):
    bl_idname='local_character.accept_motion_mapping';bl_label='Use Suggested Mapping';bl_options={'UNDO'}
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);proposal=json.loads(rig.get('lc_role_suggestions','{}'))
            if not proposal or len(set(proposal.values()))!=len(proposal):raise ValueError('Review duplicate or missing roles first')
            old=rig.get('lc_humanoid_roles','{}');rig['lc_humanoid_roles']=json.dumps(proposal)
            try:names(rig)
            except Exception:rig['lc_humanoid_roles']=old;raise
        except (ValueError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_assign_role(Operator):
    bl_idname='local_character.assign_motion_role';bl_label='Assign Bone';bl_options={'UNDO'}
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);s=context.scene.lc_settings
            if s.mapping_bone not in rig.data.bones:raise ValueError('Choose an existing character bone')
            data=json.loads(rig.get('lc_humanoid_roles','{}'));data={r:b for r,b in data.items() if b!=s.mapping_bone};data[s.mapping_role]=s.mapping_bone
            rig['lc_humanoid_roles']=json.dumps(data)
        except ValueError as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


CLASSES=(LC_OT_detect_roles,LC_OT_accept_roles,LC_OT_assign_role)
