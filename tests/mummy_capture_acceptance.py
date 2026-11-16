"""Real video -> reusable ExMR source -> skinned target -> automatic contacts."""
import bpy,addon_utils,importlib,json,sys,time,hashlib
from pathlib import Path
import numpy as np
video,prepared,destination=sys.argv[sys.argv.index('--')+1:]
out=Path(destination);out.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=prepared,load_ui=False,use_scripts=False)
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
ctx=bpy.context;s=ctx.scene.lc_settings;p=a.configuration.settings(ctx);rig=ctx.scene.objects['Mummy_Rig'];meshes=[ctx.scene.objects[n] for n in ('Mummy_Body','Mummy_staff')]
p.capture_backend='EXMR';p.video_jobs=str(out/'Jobs');p.motion_library_directory=str(out/'Library')
s.motion_system='VIDEO';s.video_input='FILES';s.video_path=video;s.capture_whole_video=True;s.source_loop=False;s.source_in_place=False;s.source_name='Mummy · Staff Motion';s.retarget_selected_characters=False;s.retarget_loop='ONCE';s.retarget_in_place=False;s.motion_contacts=True;s.ground_height=0
ctx.window_manager.lc_motion_library.loaded_sources='[]';a.motion_library.refresh(ctx);assert not ctx.window_manager.lc_motion_library.entries
a.character_context.pin(ctx,rig,meshes);ctx.view_layer.update();before=a.skinning._digest(rig,meshes);objects=set(ctx.scene.objects)
began=time.monotonic();assert a.motion_sources.start(ctx)=={'FINISHED'};folder=Path(s.source_job);stages={};last=''
print('MUMMY_EXMR_JOB',folder,flush=True)
while True:
 state=a.skinning.poll(folder)
 if state.get('total'):
  assert 0<=state['completed']<=state['total'];stages[state['phase']]=dict(completed=state['completed'],total=state['total'],unit=state.get('unit'))
 if state.get('phase')!=last:print('MEASURED_STAGE',state.get('phase'),flush=True);last=state.get('phase')
 if state['status']!='running':break
 if time.monotonic()-began>1200:a.skinning.cancel(folder);raise AssertionError('ExMR acceptance exceeded 20 minutes')
 time.sleep(.3)
assert state['status']=='complete',(state,(folder/'worker.log').read_text(errors='replace')[-4000:])
assert bpy.ops.local_character.finish_motion_source()=={'FINISHED'}
assert len(ctx.window_manager.lc_motion_library.entries)==1
entry=a.motion_sources.chosen(ctx)[0];library=a.motion_library.root(ctx);raw=a.motion_store.clip_dir(library,entry['id'])/'motion.npz';source_hash=hashlib.sha256(raw.read_bytes()).hexdigest()
for obj in ctx.selected_objects:obj.select_set(False)
rig.select_set(True);ctx.view_layer.objects.active=rig
assert bpy.ops.local_character.retarget_sources()=={'FINISHED'} and not json.loads(s.retarget_report),s.retarget_report
action=rig.animation_data.action
assert not action.lc_clip_loop and action.get('lc_capture_stabilized')
duration=(action.frame_end-action.frame_start)/(ctx.scene.render.fps/ctx.scene.render.fps_base)
assert 7.8<duration<8.05,duration
assert before==a.skinning._digest(rig,meshes),'Retarget changed character geometry, rest bones or weights'
assert set(ctx.scene.objects)==objects and hashlib.sha256(raw.read_bytes()).hexdigest()==source_hash
captured=a.motion_store.capture(ctx,rig,action,rig.animation_data.action_slot);a.motion_store.validate(captured)
report=json.loads(action['lc_contact_report']);source=a.motion_store.read(library,entry['id'])
assert 'contact_probabilities' in source and len(stages)>=3
finger_ids=[i for i,n in enumerate(source['names']) if 'Hand' in str(n) and str(n)[-1:] in ('1','2','3')]
local_fingers=source['poses'][:,source['parents'][finger_ids],:3,:3].swapaxes(-1,-2)@source['poses'][:,finger_ids,:3,:3]
finger_variances=np.var(local_fingers,axis=0).mean(axis=(-1,-2));finger_variation=float(finger_variances.mean());animated_fingers=int((finger_variances>1e-8).sum())
assert finger_ids and animated_fingers,'No inferred finger articulation'
raw_result=json.loads((folder/'captures/0000/results.json').read_text())
result=dict(passed=True,real_exmr_inference=True,video=video,prepared=prepared,job=str(folder),source_id=entry['id'],source_motion=str(raw),source_sha256=source_hash,duration_seconds=duration,frames=len(source['times']),source_only_working_list=True,rest_and_weights_preserved=True,one_shot=True,automatic_foot_correction=report,finger_channels=len(finger_ids),animated_finger_channels=animated_fingers,finger_rotation_variance=finger_variation,measured_stages=stages,elapsed_seconds=time.monotonic()-began,capture=raw_result['metrics'])
ctx.scene.frame_set(1);s.animation_view='EDIT';s.ui_step='MOTION'
bpy.ops.wm.save_as_mainfile(filepath=str(out/'Mummy-ExMR-Review.blend'),copy=True)
(out/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print('MUMMY_EXMR_ACCEPTANCE_PASS',str(out/'results.json'),flush=True)
