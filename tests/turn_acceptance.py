"""Controlled SOMA turn proves world-pose preservation and Unity root/body heading."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import skeleton,motion_apply,exporter
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=24
roots=np.zeros((90,3));roots[:,1]=.988;roots[:,2]=np.linspace(0,1,90)
rotations=np.zeros((90,30,4));rotations[:,:,3]=1
angle=np.linspace(0,math.pi/2,90);rotations[:,0,1]=np.sin(angle/2);rotations[:,0,3]=np.cos(angle/2)
for heading in (False,True):
    rig=skeleton.create_armature(bpy.context,1.75,55)
    data=bpy.data.meshes.new('TurnGeometry');bone=rig.data.bones['LeftForeArm']
    from mathutils import Vector
    points=[tuple(bone.matrix_local@Vector((x,y,z))) for x,y,z in [(-.03,0,-.03),(.03,0,-.03),(.03,bone.length,.03),(-.03,bone.length,.03)]]
    data.from_pydata(points,[],[(0,1,2,3)]);data.update();mesh=bpy.data.objects.new('TurnGeometry',data);bpy.context.scene.collection.objects.link(mesh)
    mesh.parent=rig;mesh.modifiers.new('Skin','ARMATURE').object=rig;mesh.vertex_groups.new(name='LeftForeArm').add([0,1,2,3],1,'REPLACE')
    motion_apply.bake(bpy.context,rig,roots,rotations,heading=heading)
    for profile in ('GENERIC','HUMANOID'):
        bundle=exporter.export_bundle(bpy.context,rig,[mesh],str(output),'Turn'+profile+str(heading),profile=profile,include_action=True)
        motion_reference.write(rig,[mesh],bundle)
        reference=json.loads((bundle/'animation-reference.json').read_text())
        reference.update(check_heading=True,expected_body_heading_degrees=-90,expected_root_heading_degrees=-90 if heading else 0)
        (bundle/'animation-reference.json').write_text(json.dumps(reference))
print('TURN_BLENDER_ACCEPTANCE_PASSED',output)
