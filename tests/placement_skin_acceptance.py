"""Private mesh-only MIA skeleton -> SkinTokens -> regional refinement -> Unity bundle."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import bpy
from mathutils import Matrix,Vector

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import skinning,regional_jobs,exporter
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source/'placement-review.blend'),load_ui=False)
metadata=json.loads((source/'results.json').read_text());job=json.loads((Path(metadata['job'])/'source.json').read_text())['job_id']
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('lc_placement_job')==job)
meshes=[o for o in bpy.data.objects if o.type=='MESH' and o.get('lc_placement_job')==job]
assert len(rig.data.bones)==53 and not any(g.name in rig.data.bones for o in meshes for g in o.vertex_groups)
before=skinning._digest(rig,meshes)
folder=skinning.prepare(bpy.context,rig,meshes,parent=output)
cache=skinning.provider_cache();skinning.start(folder,cache/'bin/skintokens-cli.exe',cache/'models/F16')
while skinning.poll(folder)['status']=='running':time.sleep(.3)
state=skinning.poll(folder);assert state['status']=='complete',(folder/'worker.log').read_text()
collection,weighted,copies=skinning.apply(bpy.context,folder)
assert before==skinning._digest(rig,meshes)
regional=regional_jobs.prepare(bpy.context,weighted,copies,parent=output)
regional_jobs.start(regional)
while skinning.poll(regional)['status']=='running':time.sleep(.2)
(collection,accepted,refined),reports=regional_jobs.apply(bpy.context,regional)
bundle=exporter.export_bundle(bpy.context,accepted,refined,str(output),'ShaneAISkin')
# Independently evaluate the export pruning policy for the established Unity LBS test.
for mesh in refined:exporter._prune(mesh,accepted)
hips=accepted.matrix_world@accepted.data.bones['Hips'].head_local
up=(accepted.matrix_world@accepted.data.bones['Head'].head_local-hips).normalized()
left=(accepted.matrix_world@accepted.data.bones['LeftArm'].head_local-accepted.matrix_world@accepted.data.bones['RightArm'].head_local).normalized()
forward=left.cross(up).normalized();arm=accepted.pose.bones['LeftForeArm'];pivot=accepted.matrix_world@arm.head
arm.matrix=accepted.matrix_world.inverted()@Matrix.Translation(pivot)@Matrix.Rotation(math.radians(50),4,forward)@Matrix.Translation(-pivot)@accepted.matrix_world@arm.bone.matrix_local
bpy.context.view_layer.update();points=[]
for mesh in refined:
    evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    for vertex in evaluated.data.vertices:
        delta=evaluated.matrix_world@vertex.co-hips;points.append(dict(zip(('x','y','z'),(delta.dot(left),delta.dot(forward),delta.dot(up)))))
(bundle/'generic-lbs-reference-flat.json').write_text(json.dumps(dict(angle=50,points=points)))
arm.matrix_basis.identity();bpy.context.view_layer.update()
for obj in bpy.context.selected_objects:obj.select_set(False)
for obj in [accepted,*refined]:obj.select_set(True)
bpy.context.view_layer.objects.active=accepted
summary=dict(passed=True,placement='geometry_only_mia',skinning='native_skin_tokens',original_joints_or_weights_used=False,
    bones=len(accepted.data.bones),vertices=sum(len(o.data.vertices) for o in refined),skin_elapsed_seconds=state['elapsed_seconds'],
    regional=reports,bundle=str(bundle))
(output/'results.json').write_text(json.dumps(summary,indent=2))
bpy.ops.wm.save_as_mainfile(filepath=str(output/'blind-character-review.blend'))
print('BLIND_CHARACTER_ACCEPTANCE',json.dumps(summary))
