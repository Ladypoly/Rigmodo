"""Independent posed geometry and Unity bundles for the actual one-click avatar."""
import importlib.util
import json
from pathlib import Path
import sys
import bpy

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import exporter,skinning,motion_apply,motion_data
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source/'one-click-review.blend'),load_ui=False)
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
workflow=json.loads((Path(rig['lc_workflow'])/'workflow.json').read_text())
job=Path(next(stage['job'] for stage in workflow['stages'] if stage['stage']=='motion'))
root,rotations=motion_data.load(job,90)
motion_apply.bake(bpy.context,rig,root,rotations,contacts=True)
bpy.context.scene.frame_set(25)
print('ROTATION_PRECISION',json.dumps([dict(name=p.name,quaternion_norm=sum(v*v for v in p.rotation_quaternion)**.5,world_scale=list((rig.matrix_world@p.matrix).to_scale()),rest_scale=list(p.bone.matrix_local.to_scale()),basis_scale=list(p.scale)) for p in rig.pose.bones if p.name in ('RightFoot','RightLeg','RightUpLeg','Hips')]))
before=skinning._digest(rig,meshes)
generic=exporter.export_bundle(bpy.context,rig,meshes,str(output),'ActualGeneric',profile='GENERIC',include_action=True)
human=exporter.export_bundle(bpy.context,rig,meshes,str(output),'ActualHuman',include_action=True)
assert before==skinning._digest(rig,meshes)
# Private fixture only: evaluate the actual export weight policy for references.
for mesh in meshes:exporter._prune(mesh,rig)
for bundle in (generic,human):motion_reference.write(rig,meshes,bundle)
print('ACTUAL_CHARACTER_MOTION_REFERENCE',generic,human)
