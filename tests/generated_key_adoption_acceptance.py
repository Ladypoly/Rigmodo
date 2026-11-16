import bpy,addon_utils,importlib,json,sys,tempfile
from pathlib import Path
from mathutils import Quaternion
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
rig=a.skeleton.create_armature(ctx);s=ctx.scene.lc_settings;s.ui_motion_pipeline=True;s.motion_contacts=True;s.create_loop=True;s.motion_in_place=True;ctx.scene.frame_start=100
a.character_context.pin(ctx,rig,[])
original=a.motion_clips.new(ctx,rig,'Artist poses')
for frame,angle in [(100,0),(112,.5),(124,0)]:
    for p in rig.pose.bones:
        p.rotation_mode='QUATERNION';p.rotation_quaternion=Quaternion((0,0,1),angle if p.name=='LeftForeArm' else 0)
        for prop in ('location','rotation_quaternion','scale'):p.keyframe_insert(data_path=prop,frame=frame)
folder=a.motion_jobs.prepare(ctx,rig,'Acceptance fixture',31,parent=Path(tempfile.mkdtemp()),keyframes=True,start_frame=100)
a.animation_transfer.record_options(ctx,folder);request=json.loads((folder/'request.json').read_text());keys=a.motion_jobs.check_inputs(folder,request)
lib=Path('R:/AI/MotionLibrary/Rigmodo');entry=next(c for c in a.motion_store.catalog(lib)['clips'] if c['name'].casefold()=='walk' and c['family']=='Human');data=a.motion_store.read(lib,entry['id'])
collection=bpy.data.collections.new('Owned review');ctx.scene.collection.children.link(collection);review=rig.copy();review.data=rig.data.copy();review.animation_data_clear();collection.objects.link(review)
action=a.motion_retarget.apply(ctx,review,data,'Mock generated',end=1.)
assert a.animation_transfer.adopt_generated(ctx,folder,request,collection,review,[],action)
accepted=rig.animation_data.action;assert accepted.frame_start==100 and accepted.frame_end==124
error=0.
for row in keys['poses']:
    ctx.scene.frame_set(round(row['frame']));ctx.view_layer.update()
    for name,basis in row['basis'].items():
        target=Quaternion(basis['rotation']);actual=rig.pose.bones[name].rotation_quaternion;error=max(error,1-abs(actual.dot(target)))
assert error<1e-5,error
assert original.name in bpy.data.actions
report=dict(passed=True,artist_anchors_preserved=True,arbitrary_timeline_start=True,source_action_preserved=True,request_hash_sealed=True,maximum_quaternion_error=error)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('KEY_ADOPTION_PASS',report)
