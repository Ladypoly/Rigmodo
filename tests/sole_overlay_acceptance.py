"""Blender background regression: stationary soles, override priority and overlays."""
import bpy,addon_utils,importlib,json,sys
import numpy as np
from pathlib import Path
from mathutils import Matrix,Vector
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
rig=a.skeleton.create_armature(ctx);ctx.scene.render.fps=30
for f in (1,31):rig.pose.bones['Root'].keyframe_insert('location',frame=f)
source=rig.animation_data.action;data=a.motion_store.capture(ctx,rig,source,rig.animation_data.action_slot);names=list(map(str,data['names']));roles={r:b.name for r,b in zip(a.rig_mapping.names(rig),rig.data.bones)}
tilted=dict(data,poses=data['poses'].copy(),contact_probabilities=np.ones((31,2),dtype=np.float32))
markers=a.motion_contacts.soles(ctx,rig,roles)
for side in ('Left','Right'):
 foot=rig.data.bones[roles[side+'Foot']];i=names.index(foot.name);old=Matrix(tilted['poses'][0,i].tolist());turn=Matrix.Rotation(.24,4,'X');turn.translation=old.translation-turn@old.translation
 for child in (foot,*foot.children_recursive):
  j=names.index(child.name);tilted['poses'][:,j]=np.asarray(turn@Matrix(data['poses'][0,j].tolist()))
 toe=rig.data.bones.get(roles.get(side+'ToeBase',''))
 if toe:
  j=names.index(toe.name);old=Matrix(tilted['poses'][0,j].tolist());turn=Matrix.Rotation(.3,4,'Y');turn.translation=old.translation-turn@old.translation
  tilted['poses'][:,j]=np.asarray(turn@old)
clean,report=a.motion_contacts.solve(ctx,rig,tilted)
assert report['flat_contact_frames']==62,report
error=0.
for side in ('Left','Right'):
 i=names.index(roles[side+'Foot'])
 for frame in range(31):
  matrix=rig.matrix_world@Matrix(clean['poses'][frame,i].tolist());error=max(error,max(abs((matrix@p).z) for p in markers[side]))
assert error<1e-5,error
air,air_report=a.motion_contacts.solve(ctx,rig,tilted,overrides=[dict(side=s,start=0.,end=1.,mode='AIR') for s in ('Left','Right')])
assert air_report['contact_frames']==0 and np.allclose(air['poses'][:,:,:3,:3],tilted['poses'][:,:,:3,:3])
# Reapplying contact correction must retain learned contact samples from the active variant.
action=a.motion_retarget.apply(ctx,rig,tilted,'Tilted standing');action['lc_contact_samples']=json.dumps(dict(times=data['times'].tolist(),probabilities=np.ones((31,2)).tolist()))
grounded=a.motion_contacts.correct(ctx,rig,action);again=a.motion_contacts.correct(ctx,rig,grounded)
assert json.loads(again['lc_contact_report'])['flat_contact_frames']==62
looped,periodic=a.animation_transfer.periodic_contacts(ctx,rig,again,0)
assert periodic['periodic_three_cycle_solve'] and all(0<=e['start']<e['end']<=1.0001 for e in periodic['flat_intervals'])
ctx.scene.lc_settings.show_contact_indicators=True;ctx.scene.frame_set(1);ctx.view_layer.update();objects=set(bpy.data.objects)
states={p['state'] for p in a.contact_visuals.sample(ctx,rig)};assert states=={'PLANTED'},states
rig.location.z+=.1;ctx.view_layer.update();assert {p['state'] for p in a.contact_visuals.sample(ctx,rig)}=={'OFF FLOOR'}
again['lc_contact_report']='{}';a.contact_visuals.clear();assert {p['state'] for p in a.contact_visuals.sample(ctx,rig)}=={'AIRBORNE'}
rig.location.z-=.2;ctx.view_layer.update();assert {p['state'] for p in a.contact_visuals.sample(ctx,rig)}=={'OFF FLOOR'}
ctx.scene.lc_settings.show_contact_indicators=False;assert not a.contact_visuals.sample(ctx,rig) and set(bpy.data.objects)==objects
record=dict(passed=True,tilted_stationary_soles_max_error_m=error,full_contact_at_clip_boundaries=True,air_override_preserved=True,reapply_samples_preserved=True,learned_contacts_repeat_in_loops=True,overlay_states=['PLANTED','OFF FLOOR','AIRBORNE'],overlay_creates_no_objects=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(record,indent=2));print('SOLE_OVERLAY_REGRESSION_PASS',record)
