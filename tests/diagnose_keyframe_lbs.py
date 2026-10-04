"""Independent linear skinning diagnostic for the private animated fixture."""
import bpy,numpy as np,json
from pathlib import Path
rig=max((o for o in bpy.data.objects if o.type=='ARMATURE'),key=lambda o:len(o.name))
mesh=next(o for o in bpy.data.objects if o.type=='MESH' and o.parent==rig)
surface={i for polygon in mesh.data.polygons for i in polygon.vertices}
folder=Path(bpy.data.filepath).parent/'AvatarKeyPosesGENERIC'
reference=json.loads((folder/'animation-reference.json').read_text())
weight_reference=json.loads((folder/'weight-reference.json').read_text())
hips=rig.matrix_world@rig.data.bones['Hips'].head_local
up=(rig.matrix_world@rig.data.bones['Head'].head_local-hips).normalized()
left=(rig.matrix_world@rig.data.bones['LeftArm'].head_local-rig.matrix_world@rig.data.bones['RightArm'].head_local).normalized()
forward=left.cross(up).normalized();axes=np.array([left,forward,up]);gram=axes@axes.T
print('FRAME_GRAM',gram.tolist(),flush=True)
for frame in (1,13,25,49,73):
    bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
    mats={g.index:rig.matrix_world@rig.pose.bones[g.name].matrix@rig.data.bones[g.name].matrix_local.inverted()@rig.matrix_world.inverted() for g in mesh.vertex_groups if g.name in rig.data.bones and rig.data.bones[g.name].use_deform}
    evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get());errors=[]
    for v,actual in zip(mesh.data.vertices,evaluated.data.vertices):
        source=mesh.matrix_world@v.co;point=sum((np.array(mats[g.group]@source)*g.weight for g in v.groups if g.group in mats),start=np.zeros(3))
        errors.append(float(np.linalg.norm(point-np.array(evaluated.matrix_world@actual.co))))
    worst=int(np.argmax(errors));v=mesh.data.vertices[worst]
    print('INDEPENDENT_LBS',frame,max(errors),worst,list(v.co),[(mesh.vertex_groups[g.group].name,g.weight) for g in v.groups],flush=True)
    sample=reference['samples'][(1,13,25,49,73).index(frame)]
    provided=np.array([[p[k] for k in ('x','y','z')] for p in sample['points']])
    actual=np.array([axes@np.array(evaluated.matrix_world@v.co-hips) for v in evaluated.data.vertices if v.index in surface])
    probes={p['name']:np.array([[v[k] for k in ('x','y','z')] for v in p['points']]) for p in sample['bones']}
    predicted=[]
    for vertex_index,row in enumerate(weight_reference['meshes'][0]['vertices']):
        if vertex_index not in surface:continue
        pos=np.array([row['position'][k] for k in ('x','y','z')]);coeff=np.linalg.solve(gram,pos);v=np.zeros(3)
        for bone,weight in zip(row['bones'],row['weights']):
            probe=probes[bone];v+=weight*(probe[0]+coeff@(probe[1:]-probe[0]))
        predicted.append(v)
    print('REFERENCE_INTERNAL',frame,np.linalg.norm(actual-provided,axis=-1).max(),np.linalg.norm(np.array(predicted)-provided,axis=-1).max(),flush=True)
