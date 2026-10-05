"""Armature-only motion scope and export of an actual committed skin result."""
import importlib.util,json,sys,shutil
from pathlib import Path
import bpy
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,motion_jobs,motion_apply,skinning,exporter
args=sys.argv[sys.argv.index('--')+1:];output=Path(args[0]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=args[1],load_ui=False)
rig=bpy.context.active_object;meshes=motion_jobs.character_meshes(bpy.context,rig)
source_action=rig.animation_data.action;before=skinning._digest(rig,meshes);workflow.select(bpy.context,rig,[])
folder=motion_jobs.prepare(bpy.context,rig,'walk',90,parent=output)
assert len(json.loads((folder/'request.json').read_text())['meshes'])==len(meshes)
for file in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copy2(motion_jobs.cache()/'evaluation/walk'/file,folder/file)
motion_jobs.finish(folder);skinning._state(folder,'complete');_,copy,copies,_,_=motion_apply.apply(bpy.context,folder)
assert len(copies)==len(meshes) and before==skinning._digest(rig,meshes) and rig.animation_data.action==source_action
workflow.select(bpy.context,copy,copies);sys.path.insert(0,str(Path(__file__).parent));import motion_reference
# The private library copy has relative texture paths without its original
# asset directory. Numerical skin/animation parity uses geometry only.
for mesh in copies:mesh.data.materials.clear()
for profile in ('HUMANOID','GENERIC'):
    bundle=exporter.export_bundle(bpy.context,copy,copies,str(output),'Rigmodo'+profile,profile,include_action=True)
    for mesh in copies:exporter._prune(mesh,copy)
    motion_reference.write(copy,copies,bundle)
result=dict(passed=True,version=exporter.VERSION,actual_committed_skin_fixture=True,cached_motion_arrays=True,rig_only_motion_captures_avatar=True,
    source_action_and_skin_preserved=True,humanoid_and_generic_bundles_exported=True,materials_omitted_for_geometry_test=True)
(output/'results.json').write_text(json.dumps(result,indent=2));print('RIGMODO_EXPORT_ACCEPTANCE_PASSED',json.dumps(result),flush=True)
