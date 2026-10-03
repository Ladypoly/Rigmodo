"""Exercise extracted release source and its actual worker path, not the checkout."""
import importlib.util,json,sys,tempfile,time,zipfile
from pathlib import Path
import bpy
args=sys.argv[sys.argv.index('--')+1:];archive=Path(args[0]).resolve();output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
source=Path(tempfile.mkdtemp(prefix='local-character-extracted-'))
with zipfile.ZipFile(archive) as package:package.extractall(source)
spec=importlib.util.spec_from_file_location('local_character',source/'__init__.py',submodule_search_locations=[str(source)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import regional_jobs,skinning,regions,install_jobs,deformation_qa
bpy.ops.wm.read_factory_settings(use_empty=True)
settings=bpy.context.scene.lc_settings
assert not settings.workflow_allow_strain and all(install_jobs.inventory(settings).values())
bpy.ops.mesh.primitive_cube_add(size=.4,location=(0,0,1));mesh=bpy.context.active_object
settings.fit_bounds=False
assert bpy.ops.local_character.create_template()=={'FINISHED'}
rig=bpy.context.active_object;assert rig.type=='ARMATURE' and len(rig.data.bones)==53
before=skinning._digest(rig,[mesh])
folder=regional_jobs.prepare(bpy.context,rig,[mesh],parent=output,method='GEODESIC')
regional_jobs.start(folder)
while skinning.poll(folder)['status']=='running':time.sleep(.1)
assert skinning.poll(folder)['status']=='complete',(folder/'worker.log').read_text()
(_,target,meshes),_=regional_jobs.apply(bpy.context,folder)
assert before==skinning._digest(rig,[mesh])
weights=regions.dense_weights(meshes[0],[b.name for b in target.data.bones if b.use_deform])
assert abs(weights.sum(axis=1)-1).max()<1e-5
report=deformation_qa.inspect(target,meshes);assert report and report[0]['probes']
result=dict(passed=True,release_archive=str(archive),extracted_worker_binding=True,source_preserved=True,deformation_guard_available=True,
    provider_inventory_available=True,vertices=len(mesh.data.vertices),bones=len(target.data.bones))
(output/'results.json').write_text(json.dumps(result,indent=2));print('ARCHIVE_ACCEPTANCE',json.dumps(result),flush=True)
