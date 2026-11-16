import bpy,addon_utils,importlib,json,math,sys
import numpy as np
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
rig=a.skeleton.create_armature(bpy.context);rig.location.z=.18;scene=bpy.context.scene;scene.render.fps=30
root=rig.pose.bones['Root']
for f in range(31):
    root.location=(f*.003,0,0);root.keyframe_insert('location',frame=f+1)
action=rig.animation_data.action;action.name='Synthetic ground drift'
rest={b.name:b.matrix_local.copy() for b in rig.data.bones};objects=set(bpy.data.objects)
data=a.motion_store.capture(bpy.context,rig,action,rig.animation_data.action_slot)
result,stats=a.motion_contacts.solve(bpy.context,rig,data,0)
assert stats['contact_frames']>20,stats
names=list(map(str,data['names']));foot=names.index('LeftFoot')
before=np.array([(rig.matrix_world@__import__('mathutils').Matrix(p[foot].tolist())).translation for p in data['poses']])
after=np.array([(rig.matrix_world@__import__('mathutils').Matrix(p[foot].tolist())).translation for p in result['poses']])
assert np.ptp(after[4:-4,0])<np.ptp(before[4:-4,0])*.3,(before[:,0],after[:,0])
grounded=a.motion_contacts.correct(bpy.context,rig,action,0)
assert grounded.lc_contact_source==action and rig.animation_data.action==grounded
assert set(bpy.data.objects)==objects and all(b.matrix_local==rest[b.name] for b in rig.data.bones)
max_length_error=0
for f in (1,8,16,24,31):
    scene.frame_set(f);bpy.context.view_layer.update()
    max_length_error=max(max_length_error,max(abs((p.tail-p.head).length-p.bone.length) for p in rig.pose.bones))
assert max_length_error<1e-5,max_length_error
# A constant floor alignment must retain the airborne arc.
jump=dict(data);jump['poses']=data['poses'].copy()
arc=.6*np.sin(np.linspace(0,math.pi,len(jump['times'])))**2
jump['poses'][:,:,2,3]+=arc[:,None]
clean,report=a.motion_contacts.solve(bpy.context,rig,jump,0)
assert abs(float((clean['poses'][15,0,2,3]-clean['poses'][0,0,2,3])-arc[15]))<1e-5
assert report['contact_frames']<stats['contact_frames']
# An in-place cycle deliberately moves the soles horizontally; floor-only correction preserves that stride.
slide,report=a.motion_contacts.solve(bpy.context,rig,data,0,in_place=True)
assert np.max(np.abs(slide['poses'][:,foot,:2,3]-data['poses'][:,foot,:2,3]))<1e-5
report=dict(passed=True,planted_drift_reduced=True,airborne_arc_preserved=True,in_place_stride_preserved=True,original_action_preserved=True,no_new_objects=True,rest_and_lengths_preserved=True,maximum_length_error=max_length_error)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('CONTACT_SOLVE_PASS',report)
