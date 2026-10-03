"""Compare edge strain on private accepted character fixtures, no scene writes."""
import importlib.util
import json
from pathlib import Path
import sys
import bpy
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import deformation_qa
args=sys.argv[sys.argv.index('--')+1:];output=Path(args[0]);results=[]
for path in args[1:]:
    bpy.ops.wm.open_mainfile(filepath=path,load_ui=False)
    rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
    if not rig or rig.type!='ARMATURE':
        rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE' and o.get('lc_workflow'))
        meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    meshes=[o for o in meshes if any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    result=dict(file=path,diagnostics=deformation_qa.inspect(rig,meshes));results.append(result);print(json.dumps(result),flush=True)
output.write_text(json.dumps(results,indent=2))
