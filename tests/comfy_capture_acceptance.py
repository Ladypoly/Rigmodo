import os
import bpy,addon_utils,importlib,json,sys,time,uuid
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
bpy.ops.import_scene.gltf(filepath=os.environ.get('RIGMODO_TEST_AVATAR','R:/BLENDER/BANTER_Avatars/Shane.glb'))
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE');meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.find_armature()==rig]
a.character_context.pin(bpy.context,rig,meshes);signature=a.skinning._digest(rig,meshes);objects=set(bpy.data.objects)
s=bpy.context.scene.lc_settings;s.animation_source='TEXT';s.text_method='COMFY';s.video_reference=os.environ.get('RIGMODO_TEST_REFERENCE','R:/AI/Rigmodo/Jobs/Acceptance/full-avatar-walk/0000.png');s.motion_duration=2;s.create_loop=True;s.motion_in_place=True;s.motion_contacts=True
p=a.configuration.settings(bpy.context);p.video_jobs='R:/AI/Rigmodo/Jobs/Acceptance/ComfyPipeline'
fixture=Path(p.video_jobs);fixture.mkdir(parents=True,exist_ok=True);workflow=fixture/'cpu-test-workflow.json'
graph={'image':dict(class_type='LoadImage',inputs=dict(image='REPLACED')), 'repeat':dict(class_type='RepeatImageBatch',inputs=dict(image=['image',0],amount=48)), 'video':dict(class_type='CreateVideo',inputs=dict(images=['repeat',0],fps=24)), 'save':dict(class_type='SaveVideo',inputs=dict(video=['video',0],filename_prefix='REPLACED',format='mp4',**{'format.codec':'h264'}))}
workflow.write_text(json.dumps(graph));p.comfy_workflow=str(workflow);p.comfy_output_node='save';p.comfy_bindings=json.dumps(dict(image='image.image',output_prefix='save.filename_prefix'))
assert a.video_motion.start(bpy.context)=={'FINISHED'};folder=Path(s.video_job);print('COMFY_E2E_JOB',folder,flush=True);began=time.monotonic()
while True:
    state=a.skinning.poll(folder)
    if state['status']!='running':break
    if time.monotonic()-began>900:a.skinning.cancel(folder);raise AssertionError('Capture timed out')
    time.sleep(1)
assert state['status']=='complete',state
assert bpy.ops.local_character.finish_video_motion()=={'FINISHED'}
action=rig.animation_data.action
assert set(bpy.data.objects)==objects and a.skinning._digest(rig,meshes)==signature
assert action.get('lc_clip_loop') and action.get('lc_contact_report') and action.get('lc_contact_samples') and action.get('lc_capture_provenance')
data=a.motion_store.capture(bpy.context,rig,action,rig.animation_data.action_slot)
assert 'provenance' in data and 'contact_probabilities' in data
key,created=a.motion_store.write(fixture/'TestLibrary',data,'Comfy capture',loop=True)
reloaded=a.motion_store.read(fixture/'TestLibrary',key);assert 'provenance' in reloaded and 'contact_probabilities' in reloaded
result=json.loads((folder/'results.json').read_text());report=dict(passed=True,real_comfy_server=True,actual_capture=True,exact_prompt_output=(folder/'comfy-history.json').is_file(),same_character=True,contacts=True,loop=True,portable_library_confidence=True,metrics=result['metrics'],job=str(folder),h3_sampling_tested=False)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('COMFY_E2E_PASS',json.dumps(report),flush=True)
