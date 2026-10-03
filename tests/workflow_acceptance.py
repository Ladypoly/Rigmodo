"""Actual geometry-only MIA -> SkinTokens -> refinement -> Kimodo -> FBX."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import bpy

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning,placement
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source/'placement-review.blend'),load_ui=False)
original_names=json.loads((Path(json.loads((source/'results.json').read_text())['job'])/'source.json').read_text())
original_rig=bpy.data.objects[original_names['rig']];meshes=[bpy.data.objects[entry['name']] for entry in original_names['meshes']]
workflow.select(bpy.context,original_rig,meshes)
before=skinning._digest(original_rig,meshes);settings=bpy.context.scene.lc_settings
settings.workflow_reuse_joints=False;settings.workflow_export=True;settings.export_directory=str(output);settings.character_name='OneClick';settings.motion_frames=90
run=workflow.Run(bpy.context,workflow.options(settings));run.launch(bpy.context)
settings.workflow_id=run.id
start=time.monotonic();stages=[]
while not run.finished and not run.halted:
    state=skinning.poll(run.folder)
    if state['status']=='running':time.sleep(.2);continue
    assert state['status']=='complete',(run.folder/'worker.log').read_text()
    stages.append(dict(stage=run.stage,elapsed=state.get('elapsed_seconds')))
    # Exactly the production undo-owning phase application.
    assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
assert not run.halted,run.halted
assert before==skinning._digest(original_rig,meshes),'Source data changed'
assert len(run.rig.data.bones)==53 and len(run.meshes)==2 and run.rig.animation_data.action
assert not workflow._runs and not skinning._jobs
assert original_rig.hide_get() and all(o.hide_get() for o in meshes)
assert all(not o.hide_get() for o in [run.rig,*run.meshes])
assert set(bpy.context.selected_objects)=={run.rig,*run.meshes}
assert (output/'OneClick/OneClick.character.json').is_file()
# Reuse mode skips AI placement and retains artist corrections by construction.
settings.workflow_export=False;settings.workflow_motion=False;settings.workflow_rebind=False
settings.workflow_reuse_joints=True
reuse=workflow.Run(bpy.context,workflow.options(settings));assert reuse.pending==['refine'];reuse.cancel()
bpy.ops.wm.save_as_mainfile(filepath=str(output/'one-click-review.blend'))
summary=dict(passed=True,original_joints_or_weights_used=False,elapsed_seconds=time.monotonic()-start,stages=stages,
             workflow_record=str(run.record),bundle=settings.last_export,bones=53,vertices=sum(len(m.data.vertices) for m in run.meshes),
             original_data_preserved=True,reuse_skips_joint_placement=True)
(output/'results.json').write_text(json.dumps(summary,indent=2));print('WORKFLOW_ACCEPTANCE',json.dumps(summary))
