# SPDX-License-Identifier: GPL-3.0-or-later
"""Retarget into a new editable Action on transactionally owned character copies."""
import json
import math
import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from . import motion_data, motion_jobs, skeleton, skinning, kinematics,twists,hand_pose


def _contacts(poses,mapping,world,masks,frame,pins,stats):
    inverse=world.inverted()
    goals={};pelvis_shift=0.;shift_limit=math.inf
    for index,side in enumerate(('Left','Right')):
        if not masks[frame,index]:pins.pop(side,None);continue
        upper,lower,foot=(mapping[side+part] for part in ('UpLeg','Leg','Foot'))
        if lower.parent!=upper or foot.parent!=lower:raise ValueError('Contact correction needs direct upper-leg, lower-leg, foot chains')
        hip,knee,end=(world@poses[b.name].translation for b in (upper,lower,foot))
        if side not in pins:
            anchor=end.copy();anchor.z=(world@foot.head_local).z
            pins[side]=anchor
        # Feather each contact interval so correction does not pop on/off.
        lo=frame
        while lo>0 and masks[lo-1,index]:lo-=1
        hi=frame
        while hi+1<len(masks) and masks[hi+1,index]:hi+=1
        strength=min(1.,(frame-lo+1)/3,(hi-frame+1)/3)
        goal=end.lerp(pins[side],strength)
        goals[side]=(upper,lower,foot,goal)
        length=(knee-hip).length+(end-knee).length
        horizontal=(Vector((hip.x,hip.y,0))-Vector((goal.x,goal.y,0))).length
        if horizontal<length:
            highest_hip=goal.z+math.sqrt(max(0,(length-1e-5)**2-horizontal**2))
            pelvis_shift=min(pelvis_shift,highest_hip-hip.z)
        shift_limit=min(shift_limit,length*.08)
    pelvis_shift=max(pelvis_shift,-shift_limit)
    if pelvis_shift<0:
        stats['maximum_pelvis_lowering_m']=max(stats['maximum_pelvis_lowering_m'],-pelvis_shift)
        for name,pose in poses.items():
            if name!=mapping['Root'].name:pose.translation=inverse@(world@pose.translation+Vector((0,0,pelvis_shift)))
    for side,(upper,lower,foot,goal) in goals.items():
        hip,knee,end=(world@poses[b.name].translation for b in (upper,lower,foot))
        solved_knee,solved_end,clamped=kinematics.two_bone(hip,knee,end,goal,(0,-1,0))
        stats['unreachable_contact_frames']+=int(clamped)
        stats['contact_frames']+=1
        stats['max_ankle_correction_m']=max(stats['max_ankle_correction_m'],(solved_end-end).length)
        for bone,old_direction,new_direction,position in (
            (upper,knee-hip,solved_knee-hip,hip),(lower,end-knee,solved_end-solved_knee,solved_knee)):
            original=world@poses[bone.name]
            rotation=old_direction.rotation_difference(new_direction).to_matrix()@original.to_quaternion().to_matrix()
            target=rotation.to_4x4()@Matrix.Diagonal((*original.to_scale(),1.));target.translation=position
            poses[bone.name]=inverse@target
        poses[foot.name].translation=inverse@solved_end
        # Retain the animated foot/toe orientation and move descendant pivots.
        for child in foot.children_recursive:
            inherited=poses[child.parent.name]@child.parent.matrix_local.inverted()@child.matrix_local
            poses[child.name].translation=inherited.translation


def bake(context, rig, root, rotations, in_place=False, hand_curl=0., label='Generated Motion',contacts=False,heading=False,hands=None):
    """Use anatomical rest-direction calibration, never assign source local quaternions directly."""
    mapping=motion_jobs.validate_rig(context,rig)
    if not 0 <= hand_curl <= 1: raise ValueError('Hand curl must be 0–1')
    _,source_rot=motion_data.forward(root,rotations)
    forward=source_rot[:,motion_data.NAMES.index('Hips'),:,2]
    yaw=np.unwrap(np.arctan2(forward[:,0],forward[:,2]));yaw-=yaw[0]
    conversion=Matrix(motion_data.Y_TO_Z.tolist())
    world=rig.matrix_world.copy(); inverse=world.inverted(); world_rot=world.to_quaternion().to_matrix()
    scene_scale=context.scene.unit_settings.scale_length
    if not math.isfinite(scene_scale) or scene_scale <= 0: raise ValueError('Scene unit scale must be positive')
    source_leg=sum(Vector(motion_data.OFFSETS[motion_data.NAMES.index('Left'+part)]).length for part in ('Shin','Foot'))
    target_leg=sum(((world@mapping['Left'+part].tail_local)-(world@mapping['Left'+part].head_local)).length for part in ('UpLeg','Leg'))
    scale=target_leg/source_leg
    source_frames={}; calibration={}
    for canonical,bone in mapping.items():
        if canonical not in motion_data.MAPPING: continue
        source=motion_data.MAPPING[canonical]
        rest_world=world_rot@bone.matrix_local.to_3x3()
        target_direction=(world_rot@(bone.tail_local-bone.head_local)).normalized()
        source_direction=Vector(motion_data.direction(source))
        # Arms need a shared T-pose reference across A/T bind poses. Body and
        # feet retain anatomical rest alignment: ankle/toe segment slopes are
        # proportions, not a different neutral foot orientation.
        arm=canonical in {side+part for side in ('Left','Right') for part in ('Arm','ForeArm','Hand')}
        calibration[bone.name]=(target_direction.rotation_difference(source_direction).to_matrix()@rest_world) if arm else rest_world
        source_frames[bone.name]=motion_data.NAMES.index(source)
    ordered=sorted(rig.data.bones,key=lambda bone:len(bone.parent_recursive))
    root_bone=mapping['Root']; hips=mapping['Hips']
    root_rest=world@root_bone.matrix_local; hips_rest=world@hips.head_local
    action=bpy.data.actions.new(label)
    rig.animation_data_create(); rig.animation_data.action=action
    previous={}; frame_rate=context.scene.render.fps/context.scene.render.fps_base
    masks=motion_data.contact_masks(root,rotations) if contacts else None
    pins={};contact_stats=dict(contact_frames=0,unreachable_contact_frames=0,max_ankle_correction_m=0.,maximum_pelvis_lowering_m=0.)
    for frame in range(len(root)):
        keyframe=1+frame*frame_rate/30
        horizontal=conversion@Vector((root[frame,0]-root[0,0],0,root[frame,2]-root[0,2]))*scale
        if in_place: horizontal=Vector((0,0,0))
        vertical=Vector((0,0,(root[frame,1]-.988)*scale))
        poses={}
        for bone in ordered:
            if bone==root_bone:
                target=(Matrix.Rotation(float(yaw[frame]),4,'Z')@root_rest) if heading else root_rest.copy()
                target.translation=root_rest.translation+horizontal; target=inverse@target
            else:
                parent_pose=poses.get(bone.parent.name) if bone.parent else None
                inherited=(parent_pose@bone.parent.matrix_local.inverted()@bone.matrix_local) if parent_pose else bone.matrix_local.copy()
                if bone.name in source_frames:
                    source=Matrix(source_rot[frame,source_frames[bone.name]].tolist())
                    rotation=world_rot.inverted()@conversion@source@conversion.transposed()@calibration[bone.name]
                    target=rotation.to_4x4(); target.translation=inherited.translation
                    if bone==hips: target.translation=inverse@(hips_rest+horizontal+vertical)
                else:
                    target=inherited
                    canonical=skeleton.canonical_name(bone.name)
                    angle=hand_pose.angles(canonical,hands)
                    if angle is None and 'Hand' in canonical and canonical[-1:] in ('1','2','3') and hand_curl:
                        angle=math.radians((45,65,45)[int(canonical[-1])-1])*hand_curl
                    if angle:
                        target=target@Matrix.Rotation(angle,4,'X')
            poses[bone.name]=target
        if contacts:_contacts(poses,mapping,world,masks,frame,pins,contact_stats)
        twists.update_matrices(rig,poses)
        for bone in ordered:
            pose=rig.pose.bones[bone.name]
            pose.matrix_basis=bone.convert_local_to_pose(poses[bone.name],bone.matrix_local,
                parent_matrix=poses[bone.parent.name] if bone.parent else Matrix.Identity(4),
                parent_matrix_local=bone.parent.matrix_local if bone.parent else Matrix.Identity(4),invert=True)
            # This retargeter preserves accepted lengths. Matrix decomposition
            # noise must not leave unkeyed micro-scales/offsets in the viewport
            # that disappear when the export copy resets to its rest basis.
            pose.scale=(1,1,1)
            if bone not in (root_bone,hips):pose.location=(0,0,0)
            pose.rotation_mode='QUATERNION'
            q=pose.rotation_quaternion.copy()
            if bone.name in previous and q.dot(previous[bone.name])<0: q.negate()
            pose.rotation_quaternion=q; previous[bone.name]=q.copy()
            pose.keyframe_insert(data_path='rotation_quaternion',frame=keyframe,group=bone.name)
            pose.keyframe_insert(data_path='location',frame=keyframe,group=bone.name)
            pose.keyframe_insert(data_path='scale',frame=keyframe,group=bone.name)
    for layer in action.layers:
        for strip in layer.strips:
            if strip.type=='KEYFRAME':
                for bag in strip.channelbags:
                    for curve in bag.fcurves:
                        for key in curve.keyframe_points: key.interpolation='LINEAR'
    action['lc_source_fps']=30; action['lc_in_place']=in_place
    action['lc_explicit_root_motion']=True
    action['lc_motion_scale']=scale*scene_scale
    action['lc_root_heading']=heading
    if hands:action['lc_hand_pose']=json.dumps(hands)
    contact_stats['max_ankle_correction_m']*=scene_scale
    contact_stats['maximum_pelvis_lowering_m']*=scene_scale
    action['lc_contact_correction']=json.dumps(contact_stats)
    return action


def apply(context, folder, hand_curl=0.,contacts=False,heading=False,hands=None):
    request,result,original,root,rotations=motion_jobs.validated(context,folder)
    # Selection changes during inference cannot change the captured output scope.
    meshes=[bpy.data.objects[entry['name']] for entry in request.get('meshes',[])]
    for mesh in meshes:
        if mesh.parent_type!='OBJECT' or mesh.constraints or any(m.type=='ARMATURE' and m.object!=original for m in mesh.modifiers):
            raise ValueError('Motion review meshes need ordinary parenting and one accepted armature')
    collection=bpy.data.collections.new('Local Character Motion')
    objects=[]; data=[]; action=None
    try:
        rig=original.copy(); rig.data=original.data.copy(); objects.append(rig); data.append(rig.data)
        rig.name=original.name+'_Motion'; rig.animation_data_clear(); collection.objects.link(rig)
        for pose in rig.pose.bones: pose.matrix_basis.identity()
        for original_mesh in meshes:
            mesh=original_mesh.copy(); mesh.data=original_mesh.data.copy(); objects.append(mesh);data.append(mesh.data)
            mesh.name=original_mesh.name+'_Motion'; mesh.parent=rig; mesh.matrix_parent_inverse=Matrix.Identity(4)
            mesh.matrix_world=original_mesh.matrix_world.copy(); collection.objects.link(mesh)
            for modifier in mesh.modifiers:
                if modifier.type=='ARMATURE': modifier.object=rig
        context.scene.collection.children.link(collection)
        action=bake(context,rig,root,rotations,request['in_place'],hand_curl,contacts=contacts,heading=heading,hands=hands)
        rig['lc_motion_job']=request['job_id']; rig['lc_motion_diagnostics']=json.dumps(result['diagnostics'])
        rig['lc_motion_prompt']=(__import__('pathlib').Path(folder)/'prompt.txt').read_text(encoding='utf-8')
        rig['lc_motion_provider']='kimodo_soma30'
        skinning._state(folder,'applied',collection=collection.name)
    except Exception:
        orphan_action=action or (rig.animation_data.action if 'rig' in locals() and rig.animation_data else None)
        for obj in objects: bpy.data.objects.remove(obj,do_unlink=True)
        for block in data:
            if block.users==0:
                (bpy.data.armatures if isinstance(block,bpy.types.Armature) else bpy.data.meshes).remove(block)
        if orphan_action and orphan_action.users==0: bpy.data.actions.remove(orphan_action)
        bpy.data.collections.remove(collection); raise
    context.scene.frame_set(context.scene.frame_current)
    return collection,rig,objects[1:],action,result['diagnostics']
