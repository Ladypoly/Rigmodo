"""Isolated actual Kimodo output retargeting; optional fresh inference with --infer."""
import importlib.util
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
import bpy
from mathutils import Matrix, Vector
import numpy as np

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import skeleton,motion_data,motion_jobs,motion_apply,skinning,exporter
args=sys.argv[sys.argv.index('--')+1:];output=Path(args[0]);output.mkdir(parents=True,exist_ok=True)
source=motion_jobs.cache()/'evaluation/walk'
results=[]
def check(value,message):
    if not value: raise AssertionError(message)

def fixture(rig):
    vertices=[];faces=[];assign=[]
    for b in rig.data.bones:
        if not b.use_deform:continue
        center=b.head_local.lerp(b.tail_local,.5); y=(b.tail_local-b.head_local)/2
        x=b.matrix_local.to_3x3()@Vector((.008 if 'Hand' in b.name else .025,0,0))
        z=b.matrix_local.to_3x3()@Vector((0,0,.008 if 'Hand' in b.name else .025))
        start=len(vertices);vertices.extend(tuple(center+v) for v in (y,-y,x,-x,z,-z))
        faces.extend(tuple(start+i for i in tri) for tri in ((0,2,4),(0,4,3),(0,3,5),(0,5,2),(1,4,2),(1,3,4),(1,5,3),(1,2,5)))
        assign.append((b.name,list(range(start,start+6))))
    data=bpy.data.meshes.new('MotionGeometry');data.from_pydata(vertices,[],faces)
    obj=bpy.data.objects.new('MotionGeometry',data);bpy.context.scene.collection.objects.link(obj)
    for name,ids in assign:obj.vertex_groups.new(name=name).add(ids,1.,'REPLACE')
    obj.modifiers.new('Skin','ARMATURE').object=rig;obj.parent=rig
    return obj

for angle,in_place in [(0,False),(55,False),(55,True)]:
    rig=skeleton.create_armature(bpy.context,1.75,angle)
    mesh=fixture(rig)
    for obj in bpy.context.selected_objects:obj.select_set(False)
    rig.select_set(True);mesh.select_set(True);bpy.context.view_layer.objects.active=rig
    before=skinning._digest(rig,[mesh]);poses=[p.matrix_basis.copy() for p in rig.pose.bones]
    folder=motion_jobs.prepare(bpy.context,rig,'A person walks forward naturally at a steady pace.',parent=output,in_place=in_place)
    if '--infer' in args and not results:
        motion_jobs.start(folder)
        while skinning.poll(folder)['status']=='running':time.sleep(.2)
        check(skinning.poll(folder)['status']=='complete','Fresh Kimodo inference failed')
    else:
        for name in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copyfile(source/name,folder/name)
        motion_jobs.finish(folder);skinning._state(folder,'complete')
    for obj in bpy.context.selected_objects:obj.select_set(False)
    rig.select_set(True);mesh.select_set(True);bpy.context.view_layer.objects.active=rig
    collection,copy,copies,action,report=motion_apply.apply(bpy.context,folder)
    check(before==skinning._digest(rig,[mesh]),'Source binding or rest changed')
    check(all(a==p.matrix_basis for a,p in zip(poses,rig.pose.bones)),'Source pose changed')
    check(len(copy.data.bones)==53 and copy.data.bones['Hips'].parent.name=='Root','Core hierarchy changed')
    check(copies[0].modifiers[0].object==copy,'Copied binding not retargeted')
    check(action is copy.animation_data.action and not rig.animation_data,'Source Action changed')
    roots,q=motion_data.load(folder,90);_,global_rot=motion_data.forward(roots,q)
    conversion=Matrix(motion_data.Y_TO_Z.tolist());max_angle=0
    for f in (0,23,51,89):
        frame=1+f*bpy.context.scene.render.fps/30;bpy.context.scene.frame_set(math.floor(frame),subframe=frame%1)
        bpy.context.view_layer.update()
        for name in ('LeftArm','LeftForeArm','RightArm','LeftUpLeg','LeftLeg','LeftFoot'):
            source_name=motion_data.MAPPING[name];idx=motion_data.NAMES.index(source_name)
            rest=Vector(motion_data.direction(source_name)) if name in ('LeftArm','LeftForeArm','RightArm') else (copy.data.bones[name].tail_local-copy.data.bones[name].head_local).normalized()
            expected=conversion@Matrix(global_rot[f,idx].tolist())@conversion.transposed()@rest
            actual=(copy.pose.bones[name].tail-copy.pose.bones[name].head).normalized()
            error=actual.angle(expected);max_angle=max(max_angle,error)
            check(error<.0015,f'{name} rest calibration failed: {error} rad')
        root_travel=copy.pose.bones['Root'].head-copy.data.bones['Root'].head_local
        expected=0 if in_place else float(np.linalg.norm((roots[f]-roots[0])[[0,2]]))*action['lc_motion_scale']
        check(abs(Vector((root_travel.x,root_travel.y,0)).length-expected)<1e-5,'Root travel wrong')
    check(max_angle<.0015,'Rest frame calibration failed')
    try:motion_apply.apply(bpy.context,folder);raise AssertionError('Duplicate accepted')
    except ValueError as error:check('already' in str(error),'Unexpected duplicate failure')
    for obj in bpy.context.selected_objects:obj.select_set(False)
    copy.select_set(True);copies[0].select_set(True);bpy.context.view_layer.objects.active=copy
    destination=exporter.export_bundle(bpy.context,copy,copies,str(output),f'Motion{angle}{in_place}',include_action=True)
    # Independent Blender LBS at the exported scene's integer sample rate.
    hips=copy.matrix_world@copy.data.bones['Hips'].head_local
    up=(copy.matrix_world@copy.data.bones['Head'].head_local-hips).normalized()
    left=(copy.matrix_world@copy.data.bones['LeftArm'].head_local-copy.matrix_world@copy.data.bones['RightArm'].head_local).normalized()
    forward=left.cross(up).normalized();samples=[];start_root=None
    for frame in (1,13,25,49,73):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();points=[]
        root_point=copy.matrix_world@copy.pose.bones['Root'].head
        if start_root is None:start_root=root_point.copy()
        for obj in copies:
            evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
            for vertex in evaluated.data.vertices:
                delta=evaluated.matrix_world@vertex.co-hips
                points.append(dict(zip(('x','y','z'),(delta.dot(left),delta.dot(forward),delta.dot(up)))))
        samples.append(dict(time=(frame-1)/24,points=points))
    reference=dict(samples=samples,root_travel=(root_point-start_root).length)
    trajectory=[]
    for frame in range(1,74):
        bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
        delta=copy.matrix_world@copy.pose.bones['Root'].head-start_root
        trajectory.append(dict(time=(frame-1)/24,position=dict(x=-delta.x,y=delta.z,z=-delta.y)))
    reference['trajectory']=trajectory
    (destination/'animation-reference.json').write_text(json.dumps(reference))
    generic=exporter.export_bundle(bpy.context,copy,copies,str(output),f'Generic{angle}{in_place}',profile='GENERIC',include_action=True)
    (generic/'animation-reference.json').write_text(json.dumps(reference))
    results.append(dict(angle=angle,in_place=in_place,max_direction_error_radians=max_angle,report=report,bundle=str(destination)))
# Reject stale joints before allocation.
folder=motion_jobs.prepare(bpy.context,rig,'walk',parent=output)
for name in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copyfile(source/name,folder/name)
motion_jobs.finish(folder);skinning._state(folder,'complete');rig.data.bones['LeftArm'].use_deform=False
count=len(bpy.data.objects)
try:motion_apply.apply(bpy.context,folder);raise AssertionError('Stale rig accepted')
except ValueError:pass
check(len(bpy.data.objects)==count,'Stale result allocated copies')
(output/'results.json').write_text(json.dumps(results,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(output/'motion-review.blend'))
print('MOTION_ACCEPTANCE',json.dumps(results))
