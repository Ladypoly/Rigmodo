import bpy,addon_utils,importlib,json,sys,time
import numpy as np
from pathlib import Path
from mathutils import Quaternion
folder=Path(sys.argv[sys.argv.index('--')+1]);out=folder/'MotionBricks';out.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(folder/'Mummy-Feet-Fixed.blend'),load_ui=False,use_scripts=False);addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context;rig=ctx.scene.objects['Mummy_Rig'];a.character_context.pin(ctx,rig,[ctx.scene.objects['Mummy_Body'],ctx.scene.objects['Mummy_staff']]);bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);ctx.view_layer.objects.active=rig
p=a.configuration.settings(ctx);p.video_jobs=str(out/'Jobs');before=rig.animation_data.action;original=a.motion_store.capture(ctx,rig,before,rig.animation_data.action_slot);signature=a.skinning._digest(rig,a.motion_jobs.character_meshes(ctx,rig))
job=a.motion_refine.start(ctx,.35,.5);print('REFINE_JOB',job,flush=True);began=time.monotonic();last=''
while True:
 state=a.skinning.poll(job)
 if state.get('phase')!=last:print('REFINE_STAGE',state.get('phase'),flush=True);last=state.get('phase')
 if state['status']!='running':break
 if time.monotonic()-began>600:a.skinning.cancel(job);raise AssertionError('Refinement timed out')
 time.sleep(.3)
assert state['status']=='complete',(state,(job/'worker.log').read_text(errors='replace')[-4000:])
assert rig.animation_data.action==before
curve=next(c for c in a.motion_clips.slot_curves(before,rig.animation_data.action_slot) if c.data_path.endswith('.location') and c.array_index==0);saved=[(k.co.copy(),k.handle_left.copy(),k.handle_right.copy()) for k in curve.keyframe_points];curve.keyframe_points[0].co.y+=.01;curve.update()
try:
 a.motion_refine.finish(ctx,job);raise AssertionError('Edited source was accepted')
except ValueError as error:
 assert 'changed' in str(error) and rig.animation_data.action==before
finally:
 for i,(co,left,right) in enumerate(saved):
  key=curve.keyframe_points[i];key.co=co;key.handle_left=left;key.handle_right=right
 curve.update();before.update_tag();rig.update_tag();ctx.scene.frame_set(1);ctx.view_layer.update()
new=a.motion_refine.finish(ctx,job);assert new!=before and not new.lc_clip_loop and before.name in bpy.data.actions
assert new.name==before.name+' · MotionBricks' and before.use_fake_user
assert signature==a.skinning._digest(rig,a.motion_jobs.character_meshes(ctx,rig))
result=a.motion_store.capture(ctx,rig,new,rig.animation_data.action_slot);names=list(map(str,result['names']));finger_error=0.
for name in names:
 if 'Hand' not in name or name[-1:] not in ('1','2','3'):continue
 i=names.index(name);parent=int(result['parents'][i]);qa=result['poses'][:,parent,:3,:3].swapaxes(-1,-2)@result['poses'][:,i,:3,:3];qb=original['poses'][:,parent,:3,:3].swapaxes(-1,-2)@original['poses'][:,i,:3,:3]
 finger_error=max(finger_error,float(np.max(np.abs(qa-qb))))
assert finger_error<2e-4,finger_error
assert json.loads(new['lc_contact_report'])['unreachable_frames']==0
assert json.loads(new['lc_contact_report'])['flat_contact_frames']>400
assert np.allclose(result['poses'][:,names.index('Root')],original['poses'][:,names.index('Root')],atol=2e-5)
record=dict(passed=True,real_motionbricks=True,job=str(job),elapsed_seconds=time.monotonic()-began,original_preserved=True,source_edit_rejected=True,rest_weights_preserved=True,finger_local_rotation_max_error=finger_error,foot_contacts=json.loads(new['lc_contact_report']),refinement=json.loads((job/'results.json').read_text()))
(out/'results.json').write_text(json.dumps(record,indent=2),encoding='utf-8');ctx.scene.frame_set(66);bpy.ops.wm.save_as_mainfile(filepath=str(out/'Mummy-MotionBricks-Review.blend'),copy=True);print('REFINEMENT_ACCEPTANCE_PASS',json.dumps(record),flush=True)
