"""Failure-derived gate and structural Root adaptation on private copies."""
import importlib.util,json,sys,time
from pathlib import Path
import bpy
import numpy as np
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning,deformation_qa,regions
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
def run_to_end(run):
    run.launch(bpy.context);bpy.context.scene.lc_settings.workflow_id=run.id
    while not run.finished and not run.halted:
        state=skinning.poll(run.folder)
        if state['status']=='running':time.sleep(.1);continue
        assert state['status']=='complete',state
        assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
    assert not workflow._runs and not skinning._jobs
private=Path(__import__('os').environ['LOCALAPPDATA'])/'Temp'
bpy.ops.wm.open_mainfile(filepath=str(private/'local-character-rpm-release/release-review.blend'),load_ui=False)
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
before=skinning._digest(rig,meshes);severe,_=deformation_qa.findings(deformation_qa.inspect(rig,meshes));assert severe
s=bpy.context.scene.lc_settings;s.workflow_reuse_joints=True;s.workflow_rebind=False;s.workflow_motion=True;s.workflow_export=True
s.export_directory=str(output);s.character_name='Blocked';s.workflow_allow_strain=False
blocked=workflow.Run(bpy.context,workflow.options(s));assert blocked.pending==['refine','motion']
run_to_end(blocked);assert blocked.halted and not blocked.finished
assert json.loads((blocked.record/'workflow.json').read_text())['status']=='needs_review'
assert [p['stage'] for p in blocked.stages]==['refine'] and not (output/'Blocked').exists()
assert before==skinning._digest(rig,meshes) and bpy.context.active_object==blocked.rig
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=r'R:\BLENDER\BANTER_Avatars\Shane.glb')
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
workflow.select(bpy.context,rig,meshes);before=skinning._digest(rig,meshes)
matrices={b.name:b.matrix_local.copy() for b in rig.data.bones};names=list(matrices)
endpoints={b.name:(b.head_local.copy(),b.tail_local.copy()) for b in rig.data.bones}
weights=[regions.dense_weights(m,names) for m in meshes]
s=bpy.context.scene.lc_settings;s.workflow_reuse_joints=True;s.workflow_rebind=False;s.workflow_motion=False;s.workflow_export=False
reuse=workflow.Run(bpy.context,workflow.options(s));assert reuse.pending==['root','refine'],reuse.pending
reuse.launch(bpy.context);s.workflow_id=reuse.id
assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
assert len(reuse.rig.data.bones)==len(matrices)+1 and reuse.rig.data.bones['Hips'].parent.name=='Root'
matrix_error=max(abs(reuse.rig.data.bones[n].matrix_local[i][j]-m[i][j]) for n,m in matrices.items() for i in range(4) for j in range(4))
joint_error=max((point-actual).length for n,points in endpoints.items() for point,actual in zip(points,(reuse.rig.data.bones[n].head_local,reuse.rig.data.bones[n].tail_local)))
print('ROOT_RECONSTRUCTION_ERROR',matrix_error,joint_error,flush=True)
assert matrix_error<1e-4 and joint_error<1e-6
assert all(np.array_equal(regions.dense_weights(m,names),w) for m,w in zip(reuse.meshes,weights))
while not reuse.finished and not reuse.halted:
    state=skinning.poll(reuse.folder)
    if state['status']=='running':time.sleep(.1);continue
    assert state['status']=='complete',state
    assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
assert reuse.finished and not reuse.halted
assert before==skinning._digest(rig,meshes)
assert max(abs(reuse.rig.data.bones[n].matrix_local[i][j]-m[i][j]) for n,m in matrices.items() for i in range(4) for j in range(4))<1e-4
bpy.ops.wm.save_as_mainfile(filepath=str(output/'accepted-root-review.blend'))
# A structural copy must not need normalized paint when AI binding is next.
workflow.select(bpy.context,rig,meshes)
for mesh in meshes:
    for group in list(mesh.vertex_groups):mesh.vertex_groups.remove(group)
s.workflow_rebind=True;s.workflow_hide_sources=False
unbound=workflow.Run(bpy.context,workflow.options(s));assert unbound.pending==['root','skin','refine']
unbound.pending=['root'];unbound.launch(bpy.context);s.workflow_id=unbound.id
assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'} and unbound.finished
assert all(not m.vertex_groups for m in unbound.meshes)
# An incompatible accepted skeleton must never silently become an AI request.
workflow.select(bpy.context,rig,meshes);rig.data.bones['Hips'].inherit_scale='NONE'
try:workflow.Run(bpy.context,workflow.options(s));raise AssertionError('Invalid reuse silently accepted')
except ValueError as error:assert 'Imported humanoid cannot be reused' in str(error)
result=dict(passed=True,failed_camera_blocked=True,no_motion_or_export_after_failure=True,imported_joint_error_meters=joint_error,imported_rest_matrix_error=matrix_error,
    imported_weights_exact_at_root_adaptation=True,unbound_root_adaptation=True,incompatible_reuse_rejected=True,
    source_preserved=True,original_bones=len(matrices),adapted_bones=len(reuse.rig.data.bones))
(output/'results.json').write_text(json.dumps(result,indent=2));print('DEFORMATION_ACCEPTANCE',json.dumps(result),flush=True)
