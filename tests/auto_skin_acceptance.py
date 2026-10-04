"""Actual SkinTokens + AUTO + QA through the new Skin Avatar pipeline."""
import importlib.util,json,os,sys,time
from pathlib import Path
import bpy
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(Path(os.environ['LOCALAPPDATA'])/'Temp/local-character-one-click/one-click-review.blend'),load_ui=False)
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
before=skinning._digest(rig,meshes);matrices={b.name:b.matrix_local.copy() for b in rig.data.bones}
s=bpy.context.scene.lc_settings;s.workflow_motion=True;s.workflow_export=True
values=workflow.options(s,skin_only=True);assert not values['motion'] and not values['export'] and values['reuse_joints']
run=workflow.Run(bpy.context,values);assert run.pending==['skin','refine'];run.launch(bpy.context);s.workflow_id=run.id
started=time.monotonic()
while not run.finished and not run.halted:
    state=skinning.poll(run.folder)
    if state['status']=='running':time.sleep(.2);continue
    assert state['status']=='complete',state
    assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
assert run.finished and not run.halted
assert before==skinning._digest(rig,meshes) and all(run.rig.data.bones[n].matrix_local==m for n,m in matrices.items())
assert (run.record/'deformation-report.json').is_file() and [p['stage'] for p in run.stages]==['skin','refine']
assert s.workflow_motion and s.workflow_export and all(o.hide_get() for o in [rig,*meshes])
assert not workflow._runs and not skinning._jobs
result=dict(passed=True,actual_skin_inference=True,regional_correction_and_quality_check=True,no_rerig_or_motion_or_export=True,
    accepted_joints_exact=True,source_preserved=True,workflow_options_preserved=True,elapsed_seconds=time.monotonic()-started,version=addon.exporter.VERSION)
(output/'results.json').write_text(json.dumps(result,indent=2));print('AUTO_SKIN_ACCEPTANCE',json.dumps(result),flush=True)
