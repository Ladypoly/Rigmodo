import os
import bpy,addon_utils,importlib,json,sys,time,os
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
bpy.ops.import_scene.gltf(filepath=os.environ.get('RIGMODO_TEST_AVATAR','R:/BLENDER/BANTER_Avatars/Shane.glb'))
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE');meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.find_armature()==rig]
a.character_context.pin(bpy.context,rig,meshes);signature=a.skinning._digest(rig,meshes);objects=set(bpy.data.objects)
s=bpy.context.scene.lc_settings;s.animation_source='VIDEO';s.video_path=os.environ.get('RIGMODO_TEST_VIDEO','R:/AI/Rigmodo/Jobs/Acceptance/full-avatar-walk/avatar-walk.mp4');s.motion_duration=2;s.create_loop=True;s.motion_in_place=True;s.motion_contacts=True
p=a.configuration.settings(bpy.context);p.video_jobs='R:/AI/Rigmodo/Jobs/Acceptance/FullPipeline'
assert a.video_motion.start(bpy.context)=={'FINISHED'};folder=Path(s.video_job)
print('E2E_JOB',str(folder),flush=True);began=time.monotonic()
while True:
    state=a.skinning.poll(folder)
    if state['status']!='running':break
    if time.monotonic()-began>900:a.skinning.cancel(folder);raise AssertionError('Capture timed out')
    time.sleep(1)
assert state['status']=='complete',state
assert bpy.ops.local_character.finish_video_motion()=={'FINISHED'}
action=rig.animation_data.action
assert set(bpy.data.objects)==objects and a.skinning._digest(rig,meshes)==signature
assert action.get('lc_clip_loop') and action.get('lc_contact_report')
result=json.loads((folder/'results.json').read_text());report=dict(passed=True,real_gemx_worker=True,job=str(folder),same_character=True,contacts=True,loop=True,metrics=result['metrics'])
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('VIDEO_E2E_PASS',json.dumps(report),flush=True)
