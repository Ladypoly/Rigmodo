import bpy,addon_utils,importlib,json,sys,tempfile,subprocess,hashlib
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
folder=Path(tempfile.mkdtemp(prefix='rigmodo-batch-acceptance-'));root=folder/'Library';rig=a.skeleton.create_armature(bpy.context)
for b in rig.data.bones:b.name='mixamorig:'+b.name
bone=rig.pose.bones['mixamorig:Hips'];bone.keyframe_insert('location',frame=1);bone.location.y=.2;bone.keyframe_insert('location',frame=25)
action=rig.animation_data.action;action.name='Own FBX import fixture'
bpy.context.scene.frame_start=1;bpy.context.scene.frame_end=25
bpy.ops.export_scene.fbx(filepath=str(folder/'fixture.fbx'),use_selection=True,object_types={'ARMATURE'},add_leaf_bones=False,bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False)
job=folder/'job';job.mkdir();request=dict(kind='import',root=str(root),files=[str(folder/'fixture.fbx')],source='User-authored test',license='User-provided')
(job/'request.json').write_text(json.dumps(request))
worker=Path(a.__file__).with_name('motion_library_worker.py')
command=[bpy.app.binary_path,'--factory-startup','--background','--disable-autoexec','--python',str(worker),'--',str(job)]
with (folder/'worker.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
result=json.loads((job/'results.json').read_text());assert len(result['added'])==1 and not result['errors'],result
catalog=a.motion_store.catalog(root);entry=catalog['clips'][0];data=a.motion_store.read(root,entry['id'])
assert a.motion_store.humanoid(data['names']) and entry['source']=='User-authored test'
with (folder/'repeat.log').open('w') as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
again=json.loads((job/'results.json').read_text());assert not again['added'] and not again['errors'] and again['skipped'][0]['reason']=='Already imported'
assert len(a.motion_store.catalog(root)['clips'])==1
# Imported FBX names and axes must retarget onto the actual humanoid template.
for o in bpy.context.selected_objects:o.select_set(False)
target=a.skeleton.create_armature(bpy.context,arm_angle=25)
applied=a.motion_retarget.apply(bpy.context,target,data,'FBX retarget acceptance')
assert applied and all(c.data_path.startswith('pose.bones[') for c in a.motion_clips.slot_curves(applied,target.animation_data.action_slot))
report=dict(passed=True,fbx_batch_import=True,mixamo_namespace_supported=True,provenance_not_inferred_from_names=True,repeat_import_skipped=True,imported_fbx_retargeted=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('BATCH_IMPORT_PASS',json.dumps(report),flush=True)
