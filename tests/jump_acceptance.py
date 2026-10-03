"""Airborne pelvis height stays on Hips; planar actor Root survives Unity."""
import importlib.util
import json
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Vector
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import skeleton,motion_apply,exporter,motion_jobs,motion_data
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=24
roots,q=motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
roots=roots.copy();roots[:,1]=.988+np.sin(np.linspace(0,np.pi,90))*.4
rig=skeleton.create_armature(bpy.context,1.75,55)
data=bpy.data.meshes.new('JumpGeometry');bone=rig.data.bones['LeftForeArm']
data.from_pydata([tuple(bone.matrix_local@Vector(v)) for v in [(-.02,0,0),(.02,0,0),(.02,bone.length,0),(-.02,bone.length,0)]],[],[(0,1,2,3)])
mesh=bpy.data.objects.new('JumpGeometry',data);bpy.context.scene.collection.objects.link(mesh);mesh.parent=rig
mesh.modifiers.new('Skin','ARMATURE').object=rig;mesh.vertex_groups.new(name=bone.name).add([0,1,2,3],1,'REPLACE')
action=motion_apply.bake(bpy.context,rig,roots,q,heading=True)
start=rig.data.bones['Hips'].head_local.z;maximum=0
for frame in range(1,74):
    bpy.context.scene.frame_set(frame);maximum=max(maximum,rig.pose.bones['Hips'].head.z-start)
    assert abs(rig.pose.bones['Root'].head.z)<1e-6
assert maximum>.3
for profile in ('GENERIC','HUMANOID'):
    bundle=exporter.export_bundle(bpy.context,rig,[mesh],str(output),'Jump'+profile,profile=profile,include_action=True)
    motion_reference.write(rig,[mesh],bundle);reference=json.loads((bundle/'animation-reference.json').read_text())
    reference.update(check_jump=True,minimum_jump_height_m=.3)
    (bundle/'animation-reference.json').write_text(json.dumps(reference))
print('JUMP_BLENDER_ACCEPTANCE_PASSED',maximum)
