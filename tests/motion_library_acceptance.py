import bpy,addon_utils,importlib,sys,json,math,tempfile
from pathlib import Path
import numpy as np
from mathutils import Matrix
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
assert hasattr(bpy.context.window_manager,'lc_motion_library')
root=Path('R:/AI/MotionLibrary/Rigmodo');catalog=a.motion_store.catalog(root)
walk=next(c for c in catalog['clips'] if c['family']=='Human' and c['name'].casefold().replace('_',' ')=='walk')
data=a.motion_store.read(root,walk['id']);print('LIBRARY_TEST_WALK',walk['name'],data['poses'].shape,flush=True)
rig=a.skeleton.create_armature(bpy.context,arm_angle=35);scene=bpy.context.scene;scene.render.fps=24
rest={b.name:b.matrix_local.copy() for b in rig.data.bones};objects=set(bpy.data.objects)
action=a.motion_retarget.apply(bpy.context,rig,data,'Library acceptance',speed=1.5,mirror=True,in_place=True,spacing=12,loop=True)
assert set(bpy.data.objects)==objects
assert all(b.matrix_local==rest[b.name] for b in rig.data.bones)
assert abs(action.frame_end-(1+walk['duration']/1.5*24))<.001
length_error=0.
for frame in [1,3,7,12,int(action.frame_end)]:
    scene.frame_set(frame);bpy.context.view_layer.update()
    for p in rig.pose.bones:
        assert all(math.isfinite(v) for row in p.matrix for v in row)
        length_error=max(length_error,abs((p.tail-p.head).length-p.bone.length))
assert length_error<1e-5,length_error
before=a.unimate.source_signature(rig);frame=scene.frame_current
captured=a.motion_store.capture(bpy.context,rig,action,rig.animation_data.action_slot)
assert a.unimate.source_signature(rig)==before and scene.frame_current==frame
test_root=Path(tempfile.mkdtemp(prefix='rigmodo-library-test-'))
key,created=a.motion_store.write(test_root,captured,'Own library test',loop=True);assert created
same,created=a.motion_store.write(test_root,captured,'Duplicate');assert same==key and not created
assert len(a.motion_store.catalog(test_root)['clips'])==1 and (a.motion_store.clip_dir(test_root,key)/'preview.png').is_file()
reloaded=a.motion_store.read(test_root,key)
assert np.array_equal(reloaded['poses'],captured['poses'])
before_pose=[p.matrix_basis.copy() for p in rig.pose.bones]
old_action=rig.animation_data.action
own=a.motion_retarget.apply(bpy.context,rig,reloaded,'Own exact reuse')
for f in [1,round(own.frame_end/2),int(own.frame_end)]:
    scene.frame_set(f);bpy.context.view_layer.update()
    assert all(abs((p.tail-p.head).length-p.bone.length)<1e-5 for p in rig.pose.bones)
try:a.motion_store.clip_dir(test_root,'../bad');raise AssertionError('Unsafe path accepted')
except ValueError:pass
try:a.motion_retarget.apply(bpy.context,rig,reloaded,'Bad trim',start=2,end=1);raise AssertionError('Bad range accepted')
except ValueError:pass
rig.scale.x=2
try:a.motion_retarget.apply(bpy.context,rig,reloaded,'Bad scale');raise AssertionError('Nonuniform scale accepted')
except ValueError:pass
rig.scale.x=1
driver=rig.driver_add('location',0)
try:a.motion_retarget.apply(bpy.context,rig,reloaded,'Driven rig');raise AssertionError('Driven rig accepted')
except ValueError:pass
rig.driver_remove('location',0)
# Browser UI records and preview cancellation preserve scene objects and the active Action.
a.configuration.settings(bpy.context).motion_library_directory=str(test_root)
a.motion_library.refresh(bpy.context,key)
state=bpy.context.window_manager.lc_motion_library;state.target=rig
previous=rig.animation_data.action;previous_frame=scene.frame_current;action_count=len(bpy.data.actions)
a.motion_library.build(bpy.context,True);assert rig.animation_data.action!=previous
a.motion_library.restore_preview(bpy.context)
assert rig.animation_data.action==previous and scene.frame_current==previous_frame and len(bpy.data.actions)==action_count
assert set(bpy.data.objects)==objects
assert bpy.ops.local_character.favorite_library_motion(key=key)=={'FINISHED'}
assert a.motion_store.catalog(test_root)['clips'][0]['favorite']
report=dict(passed=True,real_cc0_source=True,humanoid_a_pose_retarget=True,mirror_and_spacing=True,speed_and_trim=True,
    lengths_preserved=True,maximum_length_error=length_error,source_capture_preserved=True,data_roundtrip=True,duplicate_detection=True,
    preview_cancel_preserved=True,no_new_objects=True,favorites_persist=True,path_validation=True,range_validation=True,target_scale_and_drivers_validated=True,starter_clips=len(catalog['clips']))
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2))
print('MOTION_LIBRARY_PASS',json.dumps(report),flush=True)
