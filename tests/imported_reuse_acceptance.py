"""Imported anatomy/paint reuse plus real cached Kimodo motion, no AI rerig."""
import importlib.util,json,sys,time
from pathlib import Path
import bpy
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning,motion_jobs,motion_data,motion_apply,exporter,deformation_qa
sys.path.insert(0,str(root/'tests'));import motion_reference
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
workflow.select(bpy.context,rig,meshes);before=skinning._digest(rig,meshes)
s=bpy.context.scene.lc_settings;s.workflow_rebind=False;s.workflow_reuse_joints=True;s.workflow_export=False;s.workflow_motion=False
run=workflow.Run(bpy.context,workflow.options(s));assert run.pending==['root','refine'],run.pending
run.launch(bpy.context);s.workflow_id=run.id
while not run.finished and not run.halted:
    state=skinning.poll(run.folder)
    if state['status']=='running':time.sleep(.1);continue
    assert state['status']=='complete',state
    assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
assert not run.halted,run.halted
motion_jobs.validate_rig(bpy.context,run.rig)
roots,q=motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
motion_apply.bake(bpy.context,run.rig,roots,q,contacts=True,heading=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output/'reuse-review.blend'))
bundles=[exporter.export_bundle(bpy.context,run.rig,run.meshes,str(output),'Reuse'+profile,profile=profile,include_action=True) for profile in ('GENERIC','HUMANOID')]
for mesh in run.meshes:exporter._prune(mesh,run.rig)
for bundle in bundles:motion_reference.write(run.rig,run.meshes,bundle)
assert before==skinning._digest(rig,meshes)
result=dict(passed=True,case=source.stem,accepted_imported_joints=True,imported_weights_used=True,cached_real_kimodo_motion=True,
    source_preserved=True,bones=len(run.rig.data.bones),deformation_report=str(run.record/'deformation-report.json'))
(output/'results.json').write_text(json.dumps(result,indent=2));print('IMPORTED_REUSE_ACCEPTANCE',json.dumps(result),flush=True)
