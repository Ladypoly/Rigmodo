"""Final production defaults on an additional private RPM character."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import bpy
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning,exporter
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
args=sys.argv[sys.argv.index('--')+1:]
output=Path(args[0]);output.mkdir(parents=True,exist_ok=True)
source=Path(args[1]) if len(args)>1 else Path(r'R:\BLENDER\ReadyPlayerMe\Hazmat_female_01.glb')
file_hash=hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
before=skinning._digest(rig,meshes);workflow.select(bpy.context,rig,meshes);s=bpy.context.scene.lc_settings
s.workflow_reuse_joints=False;s.workflow_export=True;s.export_directory=str(output);s.character_name='RPMRelease'
assert s.motion_heading and not s.workflow_twists and not s.workflow_rigid
run=workflow.Run(bpy.context,workflow.options(s));run.launch(bpy.context);s.workflow_id=run.id;start=time.monotonic()
while not run.finished and not run.halted:
    state=skinning.poll(run.folder)
    if state['status']=='running':time.sleep(.2);continue
    assert state['status']=='complete',(run.folder/'worker.log').read_text()
    assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
if run.halted:
    bpy.ops.wm.save_as_mainfile(filepath=str(output/'needs-review.blend'))
    (output/'results.json').write_text(json.dumps(dict(passed=False,needs_review=True,message=run.halted,workflow_record=str(run.record)),indent=2))
    raise AssertionError(run.halted)
assert before==skinning._digest(rig,meshes) and len(run.rig.data.bones)==53
assert hashlib.sha256(source.read_bytes()).hexdigest()==file_hash
bpy.ops.wm.save_as_mainfile(filepath=str(output/'release-review.blend'))
bundle=Path(s.last_export);generic=exporter.export_bundle(bpy.context,run.rig,run.meshes,str(output),'RPMGeneric',profile='GENERIC',include_action=True)
for mesh in run.meshes:exporter._prune(mesh,run.rig)
for item in (bundle,generic):motion_reference.write(run.rig,run.meshes,item)
result=dict(passed=True,version=exporter.VERSION,case=source.stem,vertices=sum(len(m.data.vertices) for m in meshes),bones=53,
    actual_inference=['MIA','SkinTokens','Kimodo'],elapsed_seconds=time.monotonic()-start,source_preserved=True,root_heading=True,
    deformation_report=str(run.record/'deformation-report.json'))
(output/'results.json').write_text(json.dumps(result,indent=2));print('RELEASE_WORKFLOW_ACCEPTANCE',json.dumps(result))
