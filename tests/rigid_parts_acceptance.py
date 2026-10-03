"""Actual mechanical parts, unchanged ambiguous paint and durable rigid policies."""
import importlib.util
import json
from pathlib import Path
import sys
import time
import shutil
import bpy
import numpy as np
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import skinning,regions,regional_jobs,workflow,exporter
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
# Corpus volume preview adds other objects to selection. Resolve the intended
# workflow result by its durable record and captured final rig.
rigs=[o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('lc_workflow')]
rig=rigs[0];meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
before=skinning._digest(rig,meshes);names,fields,_=regions.prepare_fields(bpy.context,rig,meshes,'RIGID_PARTS')
folder=regional_jobs.prepare(bpy.context,rig,meshes,parent=output,method='RIGID_PARTS');regional_jobs.start(folder)
while skinning.poll(folder)['status']=='running':time.sleep(.1)
assert skinning.poll(folder)['status']=='complete',(folder/'worker.log').read_text()
(collection,target,copies),reports=regional_jobs.apply(bpy.context,folder)
assert before==skinning._digest(rig,meshes)
count=0
for mesh,field in zip(copies,fields):
    weights=regions.dense_weights(mesh,names);ids=np.flatnonzero(field['rigid']>=0);count+=len(ids)
    assert np.all(weights[ids,field['rigid'][ids]]==1)
    untouched=field['rigid']<0;assert np.array_equal(weights[untouched],field['original'][untouched])
    mask=np.zeros(len(weights),dtype=bool)
    for policy in json.loads(mesh.get(regions.POLICIES,'[]')):mask|=regions.group_mask(mesh,policy['group'])
    assert np.count_nonzero(mask)==len(ids)
assert count>0
record=json.loads((Path(target['lc_workflow'])/'workflow.json').read_text())
previous=Path(next(s['job'] for s in record['stages'] if s['stage']=='skin'))
rebuild=skinning.prepare(bpy.context,target,copies,parent=output)
shutil.copyfile(previous/'output.glb',rebuild/'output.glb');skinning._state(rebuild,'complete')
_,rebuilt,rebound=skinning.apply(bpy.context,rebuild)
for mesh,new in zip(copies,rebound):
    a,b=regions.dense_weights(mesh,names),regions.dense_weights(new,names)
    mask=np.zeros(len(a),dtype=bool)
    for policy in json.loads(mesh.get(regions.POLICIES,'[]')):mask|=regions.group_mask(mesh,policy['group'])
    assert np.array_equal(a[mask],b[mask]),'AI rebuild lost accepted rigid policy'
workflow.select(bpy.context,target,copies)
bundle=exporter.export_bundle(bpy.context,target,copies,str(output),'RigidMechanical',profile='GENERIC',include_action=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output/'rigid-review.blend'))
result=dict(passed=True,rigid_vertices=count,ambiguous_weights_exact=True,source_preserved=True,policies_persistent=True,
    ai_rebuild_policies_exact=True,ai_result_replayed=True,reports=reports,bundle=str(bundle))
(output/'results.json').write_text(json.dumps(result,indent=2));print('RIGID_PARTS_ACCEPTANCE',json.dumps(result))
