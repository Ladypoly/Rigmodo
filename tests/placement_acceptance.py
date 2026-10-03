"""Actual isolated geometry-only MIA job, copy preservation and artist joint locks."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import bpy
import numpy as np
from mathutils import Vector

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import placement,skinning
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=r'R:\BLENDER\BANTER_Avatars\Shane.glb')
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
before=skinning._digest(rig,meshes)
folder=placement.prepare(bpy.context,meshes,rig,parent=output)
with np.load(folder/'input.npz',allow_pickle=False) as arrays:assert set(arrays.files)=={'vertices','triangles'}
request=json.loads((folder/'request.json').read_text());assert 'joints' not in request and 'locks' not in request
placement.start(folder)
while skinning.poll(folder)['status']=='running':time.sleep(.2)
assert skinning.poll(folder)['status']=='complete',(folder/'worker.log').read_text()
collection,proposal,copies,result=placement.apply(bpy.context,folder)
assert before==skinning._digest(rig,meshes)
assert len(proposal.data.bones)==53 and proposal.data.bones['Hips'].parent.name=='Root'
assert all(not any(m.type=='ARMATURE' for m in o.modifiers) for o in copies)
assert all(not any(g.name in rig.data.bones for g in o.vertex_groups) for o in copies)
for original,copied in zip(meshes,copies):
    assert [tuple(v.co) for v in original.data.vertices]==[tuple(v.co) for v in copied.data.vertices]
    assert list(original.data.materials)==list(copied.data.materials)
    if original.data.shape_keys:
        assert [k.name for k in original.data.shape_keys.key_blocks]==[k.name for k in copied.data.shape_keys.key_blocks]
        assert all([tuple(v.co) for v in a.data]==[tuple(v.co) for v in b.data] for a,b in zip(original.data.shape_keys.key_blocks,copied.data.shape_keys.key_blocks))
    else:assert copied.data.shape_keys is None
try:placement.apply(bpy.context,folder);raise AssertionError('Duplicate placement accepted')
except ValueError as e:assert 'already' in str(e)
# Correct a known difficult toe, lock its exact head/tail, rerun the model.
bpy.context.view_layer.objects.active=proposal
for o in bpy.context.selected_objects:o.select_set(False)
proposal.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
toe=proposal.data.edit_bones['RightToeBase'];toe.head+=Vector((.008,-.03,.012));toe.tail+=Vector((.008,-.03,.012))
bpy.ops.object.mode_set(mode='OBJECT');proposal.data.bones['RightToeBase']['lc_joint_locked']=True
locked=proposal.data.bones['RightToeBase'];head=locked.head_local.copy();tail=locked.tail_local.copy()
second=placement.prepare(bpy.context,copies,proposal,parent=output)
placement.start(second)
while skinning.poll(second)['status']=='running':time.sleep(.2)
assert skinning.poll(second)['status']=='complete',(second/'worker.log').read_text()
_,corrected,new_copies,_=placement.apply(bpy.context,second)
assert corrected.data.bones['RightToeBase'].head_local==head and corrected.data.bones['RightToeBase'].tail_local==tail
assert corrected.data.bones['RightToeBase']['lc_joint_locked']
# Stale geometry and changed lock policies reject before allocating a review collection.
third=placement.prepare(bpy.context,copies,proposal,parent=output)
for name in ('output.json','result.json'):__import__('shutil').copyfile(second/name,third/name)
skinning._state(third,'complete');proposal.data.bones['RightToeBase']['lc_joint_locked']=False
count=len(bpy.data.objects)
try:placement.apply(bpy.context,third);raise AssertionError('Changed joint lock accepted')
except ValueError as e:assert 'locks' in str(e)
assert len(bpy.data.objects)==count
summary=dict(passed=True,geometry_only=True,source_preserved=True,joint_locks_preserved=True,
    provider=result['provider'],elapsed_seconds=result['elapsed_seconds'],device=result['device'],
    peak_reserved_vram_bytes=result['peak_reserved_vram_bytes'],reference_equivalence=result['reference_equivalence'],
    placement_quality='feet_toes_and_anatomical_depth_require_visual_review',job=str(folder))
# Compare only after the prediction; references were withheld from neural input.
reference={b.name.rsplit(':',1)[-1]:rig.matrix_world@b.head_local for b in rig.data.bones}
errors={name:(Vector((head[0],-head[2],head[1]))-reference[name]).length*1000 for name,head in zip(result['names'],result['heads']) if name in reference}
summary['held_out_reference_head_differences_mm']=dict(mean=sum(errors.values())/len(errors),worst=sorted(errors.items(),key=lambda p:-p[1])[:8])
summary['reference_note']='Imported joints are an independent comparison, not anatomical ground truth'
(output/'results.json').write_text(json.dumps(summary,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(output/'placement-review.blend'))
print('PLACEMENT_ACCEPTANCE',json.dumps(summary))
