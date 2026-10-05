# SPDX-License-Identifier: GPL-3.0-or-later
"""Transactionally create weighted review copies; no source data mutations."""
import math
import uuid
import bpy
from mathutils import Matrix


def clone(context,rig,meshes,label='Root'):
    """Structural adaptation must preserve even unbound or unfinished paint."""
    if context.mode!='OBJECT':raise ValueError('Return to Object Mode before copying a character')
    collection=bpy.data.collections.new('Rigmodo '+label);objects=[];blocks=[]
    try:
        target=rig.copy();target.data=rig.data.copy();objects.append(target);blocks.append(target.data)
        target.name=rig.name+'_'+label;target.parent=None;target.matrix_world=rig.matrix_world.copy();collection.objects.link(target)
        for original in meshes:
            mesh=original.copy();mesh.data=original.data.copy();objects.append(mesh);blocks.append(mesh.data)
            mesh.name=original.name+'_'+label;mesh.parent=target;mesh.parent_type='OBJECT'
            mesh.matrix_parent_inverse=Matrix.Identity(4);mesh.matrix_world=original.matrix_world.copy();collection.objects.link(mesh)
            for modifier in mesh.modifiers:
                if modifier.type=='ARMATURE' and modifier.object==rig:modifier.object=target
        target['lc_revision']=str(uuid.uuid4())
        context.scene.collection.children.link(collection)
        return collection,target,objects[1:]
    except Exception:
        for obj in objects:bpy.data.objects.remove(obj,do_unlink=True)
        for block in blocks:
            if block.users==0:(bpy.data.armatures if isinstance(block,bpy.types.Armature) else bpy.data.meshes).remove(block)
        bpy.data.collections.remove(collection)
        raise


def create(context, rig, meshes, bone_names, weights, label='Refined', method='surface_refined', metadata=None):
    if context.mode != 'OBJECT': raise ValueError('Switch to Object Mode before creating weighted copies')
    if len(meshes) != len(weights) or len(set(bone_names)) != len(bone_names): raise ValueError('Copy correspondence mismatch')
    if any(name not in rig.data.bones for name in bone_names): raise ValueError('Unknown accepted bone')
    for mesh, matrix in zip(meshes, weights):
        if len(matrix) != len(mesh.data.vertices) or any(len(row) != len(bone_names) for row in matrix):
            raise ValueError('Vertex/bone weight correspondence mismatch')
        for row in matrix:
            if any(not math.isfinite(w) or w < 0 for w in row) or abs(sum(row) - 1) > 1e-4:
                raise ValueError('Copy requires finite nonnegative normalized weights')
    collection = bpy.data.collections.new('Rigmodo ' + label)
    created, copied_data = [], []
    try:
        copied_rig = rig.copy(); copied_rig.data = rig.data.copy()
        created.append(copied_rig); copied_data.append(copied_rig.data)
        copied_rig.name = rig.name + '_' + label
        copied_rig.parent = None; copied_rig.matrix_world = rig.matrix_world.copy()
        collection.objects.link(copied_rig)
        for original, matrix in zip(meshes, weights):
            mesh = original.copy(); mesh.data = original.data.copy()
            created.append(mesh); copied_data.append(mesh.data)
            mesh.name = original.name + '_' + label
            mesh.parent = copied_rig; mesh.parent_type = 'OBJECT'
            mesh.matrix_parent_inverse = Matrix.Identity(4); mesh.matrix_world = original.matrix_world.copy()
            collection.objects.link(mesh)
            modifiers = [m for m in mesh.modifiers if m.type == 'ARMATURE']
            if not modifiers: modifiers = [mesh.modifiers.new('Rigmodo Skin', 'ARMATURE')]
            for modifier in modifiers: modifier.object = copied_rig
            locks = {g.name: g.lock_weight for g in mesh.vertex_groups}
            for group in list(mesh.vertex_groups):
                if group.name in rig.data.bones: mesh.vertex_groups.remove(group)
            groups = [mesh.vertex_groups.new(name=name) for name in bone_names]
            for group in groups: group.lock_weight = locks.get(group.name, False)
            for vertex, row in enumerate(matrix):
                for i, value in enumerate(row):
                    if value > 0: groups[i].add([vertex], float(value), 'REPLACE')
        copied_rig['lc_skinning'] = method
        for obj in created:
            if 'lc_skin_job' in obj:
                obj['lc_parent_skin_job'] = obj['lc_skin_job']
                del obj['lc_skin_job']
        copied_rig['lc_revision'] = str(uuid.uuid4())
        if metadata: copied_rig['lc_refinement'] = metadata
        context.scene.collection.children.link(collection)
    except Exception:
        for obj in created: bpy.data.objects.remove(obj, do_unlink=True)
        for data in copied_data:
            if data.users == 0:
                if isinstance(data, bpy.types.Armature): bpy.data.armatures.remove(data)
                else: bpy.data.meshes.remove(data)
        bpy.data.collections.remove(collection)
        raise
    return collection, copied_rig, created[1:]
