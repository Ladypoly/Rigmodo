"""Actual three-provider workflow using only the freshly installed cache."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import bpy

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);cache=Path(args[1]);output=Path(args[2]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source/'placement-review.blend'),load_ui=False)
names=json.loads((Path(json.loads((source/'results.json').read_text())['job'])/'source.json').read_text())
rig=bpy.data.objects[names['rig']];meshes=[bpy.data.objects[e['name']] for e in names['meshes']]
before=skinning._digest(rig,meshes);workflow.select(bpy.context,rig,meshes)
s=bpy.context.scene.lc_settings
s.placement_python=str(cache/'mia-original/runtime/Scripts/python.exe')
s.skin_executable=str(cache/'skin-tokens-46dbfec/bin/skintokens-cli.exe');s.skin_models=str(cache/'skin-tokens-46dbfec/models/F16')
s.motion_provider=str(cache/'kimodo-5679ff1');s.workflow_reuse_joints=False;s.workflow_motion=True;s.workflow_twists=True
s.workflow_export=True;s.export_directory=str(output);s.character_name='InstalledWorkflow';s.motion_heading=True
run=workflow.Run(bpy.context,workflow.options(s));run.launch(bpy.context);s.workflow_id=run.id
started=time.monotonic();stages=[]
while not run.finished and not run.halted:
    state=skinning.poll(run.folder)
    if state['status']=='running':time.sleep(.2);continue
    assert state['status']=='complete',(run.folder/'worker.log').read_text()
    stages.append(dict(stage=run.stage,elapsed=state.get('elapsed_seconds')))
    assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
assert not run.halted,run.halted
assert before==skinning._digest(rig,meshes)
assert len(run.rig.data.bones)==55 and run.rig.animation_data.action
assert not workflow._runs and not skinning._jobs
bpy.ops.wm.save_as_mainfile(filepath=str(output/'installed-review.blend'))
result=dict(passed=True,fresh_cache=str(cache),actual_inference=['MIA','SkinTokens','Kimodo'],stages=stages,
    elapsed_seconds=time.monotonic()-started,bones=55,source_preserved=True,bundle=s.last_export)
(output/'results.json').write_text(json.dumps(result,indent=2));print('FRESH_PROVIDER_ACCEPTANCE',json.dumps(result))
