"""Stable object commits, rollback, shared data, scoped purge and rig-only motion."""
import importlib.util,json,shutil,sys
from pathlib import Path
from types import SimpleNamespace
import bpy,numpy as np
args=sys.argv[sys.argv.index('--')+1:]
root=Path(args[1]) if len(args)>1 else Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import skeleton,weight_copy,character_result,skinning,motion_jobs,motion_apply,workflow,ui
output=Path(args[0]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
rig=skeleton.create_armature(bpy.context,1.75,20)
data=bpy.data.meshes.new('Character Mesh');data.from_pydata([(0,0,1),(.1,0,1),(0,.1,1)],[],[(0,1,2)])
mesh=bpy.data.objects.new('Character',data);bpy.context.scene.collection.objects.link(mesh)
mesh.shape_key_add(name='Basis');key=mesh.shape_key_add(name='Smile');key.data[0].co.z+=.1
mesh.vertex_groups.new(name='Mask').add([0],.5,'REPLACE')
mesh.vertex_groups.new(name='Hips').add([0,1,2],1,'REPLACE')
modifier=mesh.modifiers.new('Skin','ARMATURE');modifier.object=rig;mesh.parent=rig
shared=mesh.copy();shared.data=mesh.data;bpy.context.scene.collection.objects.link(shared);shared.hide_set(True)
unrelated=bpy.data.meshes.new('User orphan to keep')
shared_before=skinning._digest(None,[shared]);rest={b.name:b.matrix_local.copy() for b in rig.data.bones}
workflow.select(bpy.context,rig,[mesh]);roots,rotations=addon.motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
action=motion_apply.bake(bpy.context,rig,roots,rotations)
pointer=(rig.as_pointer(),mesh.as_pointer());names=(rig.name,mesh.name);original_rig_data=rig.data
counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections),len(bpy.data.shape_keys))
for iteration in range(2):
    collection,copy,copies=weight_copy.create(bpy.context,rig,[mesh],['Hips','LeftArm'],[np.tile([0,1],(3,1))],metadata='test')
    intermediate=[copy,*copies]
    _,final,final_meshes=weight_copy.create(bpy.context,copy,copies,['Hips','LeftArm'],[np.tile([1,0],(3,1))])
    final['lc_parent_skin_job']='skin-test-'+str(iteration)
    character_result.skin(bpy.context,rig,[mesh],final,final_meshes,owned=intermediate+[final,*final_meshes])
    assert pointer==(rig.as_pointer(),mesh.as_pointer()) and names==(rig.name,mesh.name) and rig.data==original_rig_data
    assert rig['lc_skin_job']=='skin-test-'+str(iteration)
    assert rig.animation_data.action==action and all(rig.data.bones[n].matrix_local==m for n,m in rest.items())
    assert mesh.vertex_groups['Hips'].weight(0)==1 and mesh.vertex_groups['Mask'].weight(0)==.5
    assert 'Smile' in mesh.data.shape_keys.key_blocks and shared_before==skinning._digest(None,[shared])
    # Shared source mesh stays in place, so one additional independent mesh/key
    # is expected after the first commit. Repeated commits must not accumulate.
    current=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections),len(bpy.data.shape_keys))
    if iteration==0:stable_counts=current
    else:assert current==stable_counts,(current,stable_counts)
    assert unrelated.name in bpy.data.meshes
before=skinning._digest(rig,[mesh]);old_data=mesh.data
_,copy,copies=weight_copy.create(bpy.context,rig,[mesh],['Hips','LeftArm'],[np.tile([0,1],(3,1))])
def fail():raise RuntimeError('Injected commit failure')
context=SimpleNamespace(mode='OBJECT',scene=bpy.context.scene,view_layer=SimpleNamespace(update=fail))
try:character_result.skin(context,rig,[mesh],copy,copies);raise AssertionError('Commit failure was not raised')
except RuntimeError as error:assert 'Injected' in str(error)
assert before==skinning._digest(rig,[mesh]) and mesh.data==old_data and rig.animation_data.action==action
character_result.dispose([copy,*copies])
workflow.select(bpy.context,rig,[]);bpy.context.scene.lc_settings.ui_step='MOTION'
assert ui.scope(bpy.context)==(rig,[mesh])
folder=motion_jobs.prepare(bpy.context,rig,'walk',90,parent=output)
request=json.loads((folder/'request.json').read_text());assert [m['name'] for m in request['meshes']]==[mesh.name]
for filename in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copy2(motion_jobs.cache()/'evaluation/walk'/filename,folder/filename)
motion_jobs.finish(folder);skinning._state(folder,'complete')
_,motion_rig,motion_meshes,_,_=motion_apply.apply(bpy.context,folder)
assert len(motion_meshes)==1 and motion_meshes[0].modifiers[0].object==motion_rig
assert rig.animation_data.action==action
_,legacy,legacy_meshes=weight_copy.clone(bpy.context,rig,[mesh],label='Legacy')
_,current,current_meshes=weight_copy.clone(bpy.context,legacy,legacy_meshes,label='Current')
current['lc_skin_job']='history-test'
for obj in [legacy,*legacy_meshes]:obj.hide_set(True)
history_folder=output/'history';history_folder.mkdir(exist_ok=True)
history_request=dict(job_id='history-test',rig=legacy.name,rig_pointer=str(legacy.as_pointer()),
    meshes=[dict(name=o.name,pointer=str(o.as_pointer())) for o in legacy_meshes])
path=history_folder/'request.json';path.write_text(json.dumps(history_request))
settings=bpy.context.scene.lc_settings;settings.skin_job=str(history_folder)
settings.region_job=settings.motion_job=settings.placement_job=''
foreign=bpy.data.objects.new('Artist attachment',None);bpy.context.scene.collection.objects.link(foreign);foreign.parent=legacy
try:character_result.history(bpy.context,current,current_meshes);raise AssertionError('External attachment accepted for cleanup')
except ValueError:pass
bpy.data.objects.remove(foreign,do_unlink=True)
bad=dict(history_request,rig_pointer='stale',meshes=[dict(name=o.name,pointer='stale') for o in legacy_meshes]);path.write_text(json.dumps(bad))
assert not character_result.history(bpy.context,current,current_meshes)
path.write_text(json.dumps(history_request));legacy_names=[legacy.name,*[o.name for o in legacy_meshes]]
workflow.select(bpy.context,current,[])
assert bpy.ops.local_character.clean_history()=={'FINISHED'}
assert all(name not in bpy.data.objects for name in legacy_names) and current.name in bpy.data.objects and unrelated.name in bpy.data.meshes
result=dict(passed=True,version=addon.exporter.VERSION,stable_object_names_and_identity=True,accepted_rig_and_action_preserved=True,
    repeated_skinning_without_accumulation=True,shared_mesh_and_shape_keys_preserved=True,unrelated_orphans_preserved=True,
    commit_failure_rolls_back=True,armature_only_motion_captures_bound_meshes=True,cached_motion_transport=True,
    history_cleanup_requires_matching_job_and_pointers=True,history_cleanup_rejects_external_attachments=True,extracted_extension=len(args)>1)
(output/'results.json').write_text(json.dumps(result,indent=2));print('RIGMODO_RESULT_ACCEPTANCE_PASSED',json.dumps(result),flush=True)
