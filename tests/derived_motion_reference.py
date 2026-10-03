"""Export existing accepted Action without regenerating or replacing its channels."""
import importlib.util
from pathlib import Path
import sys
import bpy
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import exporter,skinning
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);name=args[2];output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH'];assert rig and rig.type=='ARMATURE' and meshes
before=skinning._digest(rig,meshes);bundles=[]
for profile in ('GENERIC','HUMANOID'):
    bundles.append(exporter.export_bundle(bpy.context,rig,meshes,str(output),name+profile,profile=profile,include_action=True))
assert before==skinning._digest(rig,meshes)
for mesh in meshes:exporter._prune(mesh,rig)
for bundle in bundles:motion_reference.write(rig,meshes,bundle)
print('DERIVED_MOTION_REFERENCE_PASSED',name)
