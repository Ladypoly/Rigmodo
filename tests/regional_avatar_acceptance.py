"""Private real-avatar refinement diagnostic; references are withheld from solve."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Matrix, Quaternion, Vector
import numpy as np

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import skinning,regions,regional_jobs,exporter
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
before_file=hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False);addon.register()
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('lc_skin_job'))
meshes=[o for o in bpy.data.objects if o.type=='MESH' and o.get('lc_skin_job')]
reference=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o!=rig)
references=[o for o in bpy.data.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==reference for m in o.modifiers)]
references.sort(key=lambda o:meshes.index(next(m for m in meshes if m.name.startswith(o.name))))
before=skinning._digest(rig,meshes)
job=regional_jobs.prepare(bpy.context,rig,meshes,output/'jobs')
regional_jobs.start(job)
while skinning.poll(job)['status']=='running':time.sleep(.05)
assert skinning.poll(job)['status']=='complete',(job/'worker.log').read_text()
(collection,refined,copies),reports=regional_jobs.apply(bpy.context,job)
assert skinning._digest(rig,meshes)==before
names=[b.name for b in rig.data.bones if b.use_deform]
for source_mesh,copy in zip(meshes,copies):
    labels,_=regions.joint_digit_labels(source_mesh,rig,regions.dense_weights(source_mesh,names),names)
    a,b=regions.dense_weights(source_mesh,names),regions.dense_weights(copy,names)
    assert np.array_equal(a[labels==''],b[labels=='']),'AUTO changed unlabeled body weights'
    assert [v.co[:] for v in source_mesh.data.vertices]==[v.co[:] for v in copy.data.vertices]
diagnostics=[]
for label,bone,axis,angle in [('index','LeftHandIndex1',(1,0,0),55),('grip','LeftHandIndex2',(1,0,0),70),('forearm','LeftForeArm',(0,0,1),60)]:
    for armature in (reference,rig,refined):
        p=armature.pose.bones[bone];p.rotation_mode='QUATERNION';p.rotation_quaternion=Quaternion(Vector(axis),math.radians(angle))
    bpy.context.view_layer.update();deps=bpy.context.evaluated_depsgraph_get()
    for label2,candidates in [('AI',meshes),('regional',copies)]:
        errors=[]
        for a,b in zip(references,candidates):
            ea,eb=a.evaluated_get(deps),b.evaluated_get(deps)
            errors.extend(((ea.matrix_world@va.co)-(eb.matrix_world@vb.co)).length for va,vb in zip(ea.data.vertices,eb.data.vertices))
        assert np.isfinite(errors).all()
        diagnostics.append(dict(pose=label,method=label2,reference_difference_mean_m=float(np.mean(errors)),reference_difference_max_m=float(np.max(errors))))
    for armature in (reference,rig,refined):armature.pose.bones[bone].matrix_basis.identity()
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO';scene.display.shading.color_type='SINGLE';scene.display.shading.single_color=(.65,.71,.78)
scene.display.shading.show_cavity=True;scene.render.resolution_x=900;scene.render.resolution_y=700;scene.render.resolution_percentage=100
data=bpy.data.cameras.new('Regional Review');camera=bpy.data.objects.new('Regional Review',data);scene.collection.objects.link(camera);scene.camera=camera
data.type='ORTHO';data.ortho_scale=.32
bpy.context.view_layer.update()
point=reference.matrix_world@((reference.pose.bones['LeftHand'].head+reference.pose.bones['LeftHandMiddle3'].tail)*.5)
camera.location=point+Vector((0,-4,.3));camera.rotation_euler=(point-camera.location).to_track_quat('-Z','Y').to_euler()
for armature in (reference,rig,refined):
    p=armature.pose.bones['LeftHandIndex1'];p.rotation_mode='QUATERNION';p.rotation_quaternion=Quaternion(Vector((1,0,0)),math.radians(55))
for label,visible in [('reference',references),('AI',meshes),('regional',copies)]:
    for mesh in references+meshes+copies:mesh.hide_render=mesh not in visible
    scene.render.filepath=str(output/(label+'.png'));bpy.ops.render.render(write_still=True)
for armature in (reference,rig,refined):armature.pose.bones['LeftHandIndex1'].matrix_basis.identity()
for mesh in references+meshes+copies:mesh.hide_render=False
bpy.context.view_layer.update()
bundle=exporter.export_bundle(bpy.context,refined,copies,str(output),'ShaneAISkin')
# Independent Blender evaluation of the final export pruning policy, compared
# against Unity's imported Generic deformation by the existing transport test.
export_copies=[]
for mesh in copies:
    copied=mesh.copy();copied.data=mesh.data.copy();scene.collection.objects.link(copied)
    exporter._prune(copied,refined);export_copies.append(copied)
hips=refined.matrix_world@refined.pose.bones['Hips'].head
up=(refined.matrix_world@refined.pose.bones['Head'].head-hips).normalized()
left=(refined.matrix_world@refined.pose.bones['LeftArm'].head-refined.matrix_world@refined.pose.bones['RightArm'].head).normalized()
forward=left.cross(up).normalized();arm=refined.pose.bones['LeftForeArm'];pivot=refined.matrix_world@arm.head
arm.matrix=refined.matrix_world.inverted()@Matrix.Translation(pivot)@Matrix.Rotation(math.radians(50),4,forward)@Matrix.Translation(-pivot)@refined.matrix_world@arm.bone.matrix_local
bpy.context.view_layer.update();points=[]
for mesh in export_copies:
    evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    for vertex in evaluated.data.vertices:
        delta=evaluated.matrix_world@vertex.co-hips;points.append(dict(zip(('x','y','z'),(delta.dot(left),delta.dot(forward),delta.dot(up)))))
(bundle/'generic-lbs-reference-flat.json').write_text(json.dumps(dict(angle=50,points=points)))
arm.matrix_basis.identity()
for obj in export_copies:
    data=obj.data;bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(data)
bpy.ops.wm.save_as_mainfile(filepath=str(output/'regional-review.blend'))
assert hashlib.sha256(source.read_bytes()).hexdigest()==before_file
result=dict(passed=True,source_preserved=True,unlabeled_body_weights_exact=True,reports=reports,diagnostics=diagnostics)
(output/'avatar-results.json').write_text(json.dumps(result,indent=2));print('LOCAL_CHARACTER_REGIONAL_AVATAR',json.dumps(result))
