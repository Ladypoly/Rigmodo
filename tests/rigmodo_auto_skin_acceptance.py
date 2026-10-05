"""Actual SkinTokens + AUTO commit to a private copy of the current character."""
import importlib.util,json,sys,time
from pathlib import Path
import bpy
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning
args=sys.argv[sys.argv.index('--')+1:];output=Path(args[0]);output.mkdir(parents=True,exist_ok=True)
with bpy.data.libraries.load(args[1]) as (available,loaded):loaded.objects=available.objects
for obj in loaded.objects:
    if obj:bpy.context.scene.collection.objects.link(obj)
rig=next(o for o in loaded.objects if o and o.type=='ARMATURE')
meshes=[o for o in loaded.objects if o and o.type=='MESH'];workflow.select(bpy.context,rig,meshes)
bpy.context.scene.frame_set(bpy.context.scene.frame_current);bpy.context.view_layer.update()
objects=[rig,*meshes];identities=[(o.name,o.as_pointer()) for o in objects];rest={b.name:b.matrix_local.copy() for b in rig.data.bones}
action=rig.animation_data.action if rig.animation_data else None
before=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections),len(bpy.data.shape_keys))
values=workflow.options(bpy.context.scene.lc_settings,skin_only=True);assert not values['keep_skin_copies']
run=workflow.Run(bpy.context,values);run.launch(bpy.context);bpy.context.scene.lc_settings.workflow_id=run.id
started=time.monotonic()
while not run.finished and not run.halted:
    state=skinning.poll(run.folder)
    if state['status']=='running':time.sleep(.2);continue
    assert state['status']=='complete',state
    assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
assert run.finished and not run.halted,run.halted
assert identities==[(o.name,o.as_pointer()) for o in [run.rig,*run.meshes]]
assert rig.animation_data.action==action and all(rig.data.bones[n].matrix_local==m for n,m in rest.items())
after=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections),len(bpy.data.shape_keys))
assert before==after,(before,after)
assert set(bpy.context.selected_objects)==set(objects) and not workflow._runs and not skinning._jobs
result=dict(passed=True,version=addon.exporter.VERSION,actual_skin_inference=True,automatic_refinement_and_quality_check=True,
    source_object_identity_and_names_preserved=True,accepted_joints_and_action_preserved=True,temporary_objects_data_and_collections_purged=True,
    before_counts=before,after_counts=after,elapsed_seconds=time.monotonic()-started)
(output/'results.json').write_text(json.dumps(result,indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(output/'skin-review.blend'))
print('RIGMODO_AUTO_SKIN_ACCEPTANCE_PASSED',json.dumps(result),flush=True)
