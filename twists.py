# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional two-helper forearm module with explicit editable baking."""
import json
import math
import bpy
import numpy as np
from mathutils import Matrix,Quaternion
from . import skeleton,regions,weight_copy,animation


def reduced(rotation,fraction=.5):
    q=rotation.normalized();length=math.hypot(q.w,q.y)
    twist=Quaternion((q.w/length,0,q.y/length,0)) if length>1e-8 else Quaternion()
    if twist.w<0:twist.negate()
    swing=q@twist.conjugated()
    return swing@Quaternion().slerp(twist,fraction)


def modules(rig):
    result=json.loads(rig.get('lc_twists','[]'))
    for module in result:
        source,helper=(rig.data.bones.get(module[key]) for key in ('source','helper'))
        if not source or not helper or helper.parent!=source.parent or max(abs(v) for row in (helper.matrix_local-source.matrix_local) for v in row)>1e-4:
            raise ValueError('Twist rest geometry changed; rebuild the optional module on the core')
    return result


def update_pose(rig):
    for module in modules(rig):
        source=rig.pose.bones[module['source']];helper=rig.pose.bones[module['helper']]
        basis=source.matrix_basis.copy();rotation=reduced(basis.to_quaternion(),module['fraction'])
        helper.rotation_mode='QUATERNION';helper.matrix_basis=Matrix.LocRotScale(basis.translation,rotation,basis.to_scale())


def update_matrices(rig,poses):
    for module in modules(rig):
        source,helper=(rig.data.bones[module[key]] for key in ('source','helper'))
        parent=poses[source.parent.name]
        basis=source.convert_local_to_pose(poses[source.name],source.matrix_local,parent_matrix=parent,
            parent_matrix_local=source.parent.matrix_local,invert=True)
        basis=Matrix.LocRotScale(basis.translation,reduced(basis.to_quaternion(),module['fraction']),basis.to_scale())
        poses[helper.name]=helper.convert_local_to_pose(basis,helper.matrix_local,parent_matrix=parent,parent_matrix_local=helper.parent.matrix_local)


def bake_action(context,rig,selection):
    if not modules(rig):return None
    if selection['frame_end']-selection['frame_start']>3600:raise ValueError('Twist baking exceeds 3,600 frames')
    original_frame=context.scene.frame_current;original_subframe=context.scene.frame_subframe
    action=selection['action'].copy();action.name=selection['action'].name+'_Twists'
    rig.animation_data.action=action
    if selection['slot'] is not None:
        rig.animation_data.action_slot=next(slot for slot in action.slots if slot.identifier==selection['slot'].identifier)
    previous={}
    try:
        for frame in range(selection['frame_start'],selection['frame_end']+1):
            context.scene.frame_set(frame);update_pose(rig)
            for module in modules(rig):
                pose=rig.pose.bones[module['helper']];q=pose.rotation_quaternion.copy()
                if pose.name in previous and q.dot(previous[pose.name])<0:q.negate()
                pose.rotation_quaternion=q;previous[pose.name]=q.copy()
                pose.keyframe_insert('rotation_quaternion',frame=frame,group=pose.name)
                pose.keyframe_insert('location',frame=frame,group=pose.name)
                pose.keyframe_insert('scale',frame=frame,group=pose.name)
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        if any(curve.data_path.startswith(rig.pose.bones[m['helper']].path_from_id()) for m in modules(rig)):
                            for key in curve.keyframe_points:key.interpolation='LINEAR'
        action['lc_twists_baked']=True
        return action
    except Exception:
        rig.animation_data.action=selection['action']
        if selection['slot'] is not None:rig.animation_data.action_slot=selection['slot']
        if action.users==0:bpy.data.actions.remove(action)
        raise
    finally:context.scene.frame_set(original_frame,subframe=original_subframe)


def add(context,rig,meshes,fraction=.5):
    if rig.get('lc_twists'):raise ValueError('This rig already has the optional twist module')
    if not .05<=fraction<=.95:raise ValueError('Twist fraction must be .05–.95')
    mapping={skeleton.canonical_name(b.name):b for b in rig.data.bones}
    for side in ('Left','Right'):
        source=mapping.get(side+'ForeArm');parent=mapping.get(side+'Arm')
        if not source or not parent or source.parent!=parent:raise ValueError('Twists need direct upper-arm and forearm chains')
        if side+'ForeArmTwist' in rig.data.bones:raise ValueError('Twist name conflicts with an existing bone')
    names,fields,_=regions.prepare_fields(context,rig,meshes,'SURFACE')
    copied=weight_copy.create(context,rig,meshes,names,[field['original'] for field in fields],label='Twists',method=rig.get('lc_skinning','accepted_weights')+'+twists')
    collection,target,copies=copied;selected=list(context.selected_objects);active=context.view_layer.objects.active
    owned_action=None
    try:
        for o in context.selected_objects:o.select_set(False)
        target.select_set(True);context.view_layer.objects.active=target;bpy.ops.object.mode_set(mode='EDIT')
        specifications=[]
        try:
            for side in ('Left','Right'):
                source=target.data.edit_bones[mapping[side+'ForeArm'].name];name=side+'ForeArmTwist'
                helper=target.data.edit_bones.new(name);helper.head=source.head;helper.tail=source.tail;helper.roll=source.roll
                helper.parent=source.parent;helper.use_deform=True
                specifications.append(dict(source=source.name,helper=name,fraction=fraction))
        finally:bpy.ops.object.mode_set(mode='OBJECT')
        target['lc_twists']=json.dumps(specifications)
        for original,mesh,field in zip(meshes,copies,fields):
            protected=field['protected'];rigid=field['rigid']>=0
            labels,_=regions.joint_digit_labels(original,rig,field['original'],names)
            points=np.array([tuple(original.matrix_world@v.co) for v in original.data.vertices])
            for module in specifications:
                bone=rig.data.bones[module['source']];column=names.index(bone.name)
                group=mesh.vertex_groups.new(name=module['helper']);source=mesh.vertex_groups[bone.name]
                if field['locked'][column]:continue
                head=np.array(rig.matrix_world@bone.head_local);tail=np.array(rig.matrix_world@bone.tail_local);direction=tail-head
                t=np.clip((points-head)@direction/max(float(direction@direction),1e-12),0,1)
                transfer=field['original'][:,column]*.85*(1-t)**2
                transfer[protected|rigid|(labels!='')]=0
                for vertex in np.flatnonzero(transfer>1e-8):
                    source.add([int(vertex)],float(field['original'][vertex,column]-transfer[vertex]),'REPLACE')
                    group.add([int(vertex)],float(transfer[vertex]),'REPLACE')
        update_pose(target)
        if target.animation_data and target.animation_data.action:
            owned_action=bake_action(context,target,animation.selected_action(target,context.scene))
        return copied
    except Exception:
        for obj in [target,*copies]:
            block=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if block.users==0:(bpy.data.armatures if isinstance(block,bpy.types.Armature) else bpy.data.meshes).remove(block)
        if owned_action and owned_action.users==0:bpy.data.actions.remove(owned_action)
        bpy.data.collections.remove(collection)
        for obj in context.selected_objects:obj.select_set(False)
        for obj in selected:obj.select_set(True)
        context.view_layer.objects.active=active
        raise
