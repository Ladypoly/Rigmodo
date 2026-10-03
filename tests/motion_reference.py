"""Independent Blender evaluated positions for actual exported animation samples."""
import json
import bpy
from mathutils import Vector
import numpy as np

def write(rig,meshes,bundle):
    hips=rig.matrix_world@rig.data.bones['Hips'].head_local
    up=(rig.matrix_world@rig.data.bones['Head'].head_local-hips).normalized()
    left=(rig.matrix_world@rig.data.bones['LeftArm'].head_local-rig.matrix_world@rig.data.bones['RightArm'].head_local).normalized()
    forward=left.cross(up).normalized();samples=[];start=None
    weight_reference=[];precision_budget=0.;orthogonality=0.
    defects={}
    for bone in rig.data.bones:
        matrix=np.array((rig.matrix_world@bone.matrix_local).to_3x3(),dtype=np.float64)
        u,scale,v=np.linalg.svd(matrix);uniform=float(np.mean(scale))
        defects[bone.name]=float(np.linalg.norm(matrix/uniform-u@v,ord=2))
        orthogonality=max(orthogonality,defects[bone.name])
    for mesh in meshes:
        entries=[];groups={g.index:g.name for g in mesh.vertex_groups if g.name in rig.data.bones and rig.data.bones[g.name].use_deform}
        for vertex in mesh.data.vertices:
            delta=mesh.matrix_world@vertex.co-hips
            row=[g for g in vertex.groups if g.group in groups and g.weight>0]
            allowance=0.
            for influence in row:
                bone=rig.data.bones[groups[influence.group]]
                # A rotation at either end of a rest-frame conversion can
                # amplify its measured anisotropy. Sum ancestors conservatively.
                for ancestor in [bone,*bone.parent_recursive]:
                    radius=(mesh.matrix_world@vertex.co-rig.matrix_world@ancestor.head_local).length
                    allowance+=influence.weight*2*defects[ancestor.name]*radius
            precision_budget=max(precision_budget,allowance)
            entries.append(dict(position=dict(x=delta.dot(left),y=delta.dot(forward),z=delta.dot(up)),
                bones=[groups[g.group] for g in row],weights=[g.weight for g in row]))
        weight_reference.append(dict(name=mesh.name,vertices=entries))
    (bundle/'weight-reference.json').write_text(json.dumps(dict(meshes=weight_reference)))
    for frame in (1,13,25,49,73):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();points=[]
        root=rig.matrix_world@rig.pose.bones['Root'].head
        if start is None:start=root.copy()
        for mesh in meshes:
            evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            for v in evaluated.data.vertices:
                delta=evaluated.matrix_world@v.co-hips
                points.append(dict(zip(('x','y','z'),(delta.dot(left),delta.dot(forward),delta.dot(up)))))
        probes=[]
        controls=[hips,hips+left,hips+forward,hips+up]
        for bone in rig.data.bones:
            matrix=rig.matrix_world@rig.pose.bones[bone.name].matrix@bone.matrix_local.inverted()@rig.matrix_world.inverted()
            transformed=[]
            for control in controls:
                delta=matrix@control-hips
                transformed.append(dict(x=delta.dot(left),y=delta.dot(forward),z=delta.dot(up)))
            probes.append(dict(name=bone.name,points=transformed))
        samples.append(dict(time=(frame-1)/24,points=points,bones=probes))
    trajectory=[]
    for frame in range(1,74):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        delta=rig.matrix_world@rig.pose.bones['Root'].head-start
        trajectory.append(dict(time=(frame-1)/24,position=dict(x=-delta.x,y=delta.z,z=-delta.y)))
    if precision_budget>.0005:raise ValueError('Rest-frame precision budget exceeds 0.5 mm; inspect the accepted skeleton')
    (bundle/'animation-reference.json').write_text(json.dumps(dict(samples=samples,root_travel=(root-start).length,trajectory=trajectory,
        rig_rest_precision_budget_m=precision_budget,maximum_rest_rotation_anisotropy=orthogonality)))
