import bpy,addon_utils,importlib,json,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
state=ctx.window_manager.lc_motion_library;state.loaded_sources='[]';a.motion_sources.refresh(ctx);assert not state.entries
catalog=a.motion_store.catalog(a.motion_library.root(ctx));walk=next(e for e in catalog['clips'] if e['family']=='Human' and e['name'].casefold()=='walk')
a.motion_sources.refresh(ctx,[walk['id']]);assert len(state.entries)==1 and state.entries[state.index].key==walk['id'] and abs(state.trim_end-walk['duration'])<1e-5
assert bpy.ops.local_character.unload_source_motions()=={'FINISHED'} and not state.entries;assert len(a.motion_store.catalog(a.motion_library.root(ctx))['clips'])==len(catalog['clips'])
for part,role in [('lower_arm','ForeArm'),('lower_leg','Leg'),('upper_arm','Arm'),('upper_leg','UpLeg')]:
 for side,word in [('L','Left'),('R','Right')]:assert a.rig_mapping.canonical(part+'.'+side)==word+role
from importlib import import_module
progress=import_module(a.__name__+'.capture_progress');folder=Path(tempfile.mkdtemp(prefix='rigmodo-progress-lock-'));writer=progress.Progress(folder)
with patch.object(progress.os,'replace',side_effect=PermissionError('Simulated Windows reader lock')):writer('Tracking person',1,60)
writer('Tracking person',60,60);assert progress.read(folder)['completed']==60
job=Path(tempfile.mkdtemp(prefix='rigmodo-error-test-'));(job/'worker.log').write_text('ValueError: Actual capture error\nBlender 5.2.0 LTS (banner)\n');(job/'status.json').write_text(json.dumps(dict(status='failed',error='Actual nested capture error')))
a.skinning._jobs[str(job)]=dict(process=SimpleNamespace(poll=lambda:1),log=(job/'worker.log').open('ab'),started=__import__('time').monotonic())
assert a.skinning.poll(job)['error']=='Actual nested capture error'
times=np.arange(90)/30;ground=.005*times;jump=np.where((times>1)&(times<2),.4*np.sin(np.pi*(times-1)),0);heights=ground+jump
samples={side:np.stack([np.column_stack((np.zeros(90),np.zeros(90),heights))]*2,axis=1) for side in ('Left','Right')};prob=np.ones((90,2))*.95;prob[(times>1)&(times<2)]=0
drift=a.motion_contacts.floor_drift(samples,prob,times,1,());assert np.max(np.abs(drift-ground))<.02 and (heights-drift).max()>.35
prob[:]=.95;overrides=[dict(side=side,start=1,end=2,mode='AIR') for side in ('Left','Right')];drift=a.motion_contacts.floor_drift(samples,prob,times,1,overrides);assert (heights-drift).max()>.35
rig=a.skeleton.create_armature(ctx);data=a.motion_store.read(a.motion_library.root(ctx),walk['id']);signature=a.skinning._digest(rig,[])
action=a.motion_retarget.apply(ctx,rig,data,'Stabilization invariant');a.motion_finish.stabilize_capture(ctx,rig,action)
assert signature==a.skinning._digest(rig,[])
for frame in (1,8,16):
 ctx.scene.frame_set(frame);ctx.view_layer.update();assert all(abs(p.bone.length-(p.tail-p.head).length)<1e-5 for p in rig.pose.bones)
report=dict(passed=True,working_list_starts_empty=True,explicit_loading_only=True,new_source_selects_own_trim=True,unload_keeps_external_assets=True,left_right_suffix_mapping=True,progress_lock_nonfatal=True,actual_worker_error_preserved=True,confidence_and_manual_air_preserve_flight=True,stabilization_keeps_rest_and_bone_lengths=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2),encoding='utf-8');print('WULIN_REGRESSION_PASS',report)
