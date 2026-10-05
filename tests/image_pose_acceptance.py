# SPDX-License-Identifier: GPL-3.0-or-later
"""Retarget and transactional checks with a real MHR calibration fixture; no SAM inference claim."""
import addon_utils,copy,importlib,json,sys
from pathlib import Path
from types import SimpleNamespace
import bpy
import numpy as np
from mathutils import Matrix,Quaternion,Vector

assert bpy.app.background and '--factory-startup' in sys.argv
args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
if len(args)>1:
    import importlib.util
    source=Path(args[1]);spec=importlib.util.spec_from_file_location('rigmodo_archive',source/'__init__.py',submodule_search_locations=[str(source)])
    addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
else:
    addon_utils.enable('bl_ext.user_default.local_character',default_set=True)
    addon=importlib.import_module('bl_ext.user_default.local_character')
ip=addon.image_pose
fixture=Path.home()/'AppData/Local/Temp/rigmodo-sam-research/pose-fixture.json'
result=json.loads(fixture.read_text());ip.check_pose(result)
rows=[]
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
for height,angle in ((.875,0),(1.75,20),(3.5,45)):
    rig=addon.skeleton.create_armature(bpy.context,height,angle)
    bpy.ops.object.mode_set(mode='EDIT')
    for i,bone in enumerate(rig.data.edit_bones):bone.roll+=(i%7-3)*.17
    bpy.ops.object.mode_set(mode='OBJECT')
    rig.matrix_world=Matrix.Translation((2,-1,3))@Matrix.Rotation(.4,4,'Z')@Matrix.Scale(1.3,4)
    rig.pose.bones['Root'].rotation_mode='XYZ';rig.pose.bones['Root'].rotation_euler=(0,0,.25)
    rig.pose.bones['Root'].location=(.2,.3,0)
    rig.pose.bones['Hips'].location=(.01,.02,-.03)
    rig.pose.bones['LeftHandIndex2'].rotation_mode='XYZ';rig.pose.bones['LeftHandIndex2'].rotation_euler=(6.5,0,0)
    rig.pose.bones['RightHandIndex3'].rotation_mode='AXIS_ANGLE'
    bpy.context.view_layer.update()
    before=addon.auto_pose.channel_snapshot(rig);signature=addon.motion_keyframes.signature(bpy.context,rig)
    world=rig.matrix_world.copy();hip=rig.pose.bones['Hips'].head.copy()
    action=bpy.data.actions.new('Existing Animation');rig.animation_data_create();rig.animation_data.action=action
    rig.pose.bones['Spine'].keyframe_insert(data_path='rotation_quaternion',frame=1)
    bpy.context.view_layer.update()
    counts=(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.armatures),len(bpy.data.actions))
    bases=ip.bases_for(rig,result)
    bpy.context.scene.tool_settings.use_keyframe_insert_auto=True
    ip.apply(bpy.context,rig,result)
    assert bpy.context.scene.tool_settings.use_keyframe_insert_auto
    bpy.context.scene.tool_settings.use_keyframe_insert_auto=False
    assert rig.animation_data.action==action and counts==(len(bpy.data.objects),len(bpy.data.meshes),len(bpy.data.armatures),len(bpy.data.actions))
    assert rig.matrix_world==world and signature==addon.motion_keyframes.signature(bpy.context,rig)
    assert max(abs(v) for row in (rig.pose.bones['Root'].matrix_basis-before['Root']['basis']) for v in row)<1e-6
    assert (rig.pose.bones['Hips'].head-hip).length<height*1e-6
    assert rig.pose.bones['LeftHandIndex2'].rotation_mode=='XYZ' and rig.pose.bones['RightHandIndex3'].rotation_mode=='AXIS_ANGLE'
    length_error=max(abs((p.tail-p.head).length-p.bone.length)/height for p in rig.pose.bones)
    basis_error=max(abs(v) for p in rig.pose.bones for row in (p.matrix_basis-bases[p.name]) for v in row)
    if basis_error>=3e-6:print('BASIS_ERRORS',[(p.name,max(abs(v) for row in (p.matrix_basis-bases[p.name]) for v in row),list(bases[p.name].translation),list(p.location)) for p in rig.pose.bones if max(abs(v) for row in (p.matrix_basis-bases[p.name]) for v in row)>3e-6])
    assert length_error<2e-6 and basis_error<3e-6,(length_error,basis_error)
    # Independent direction check: source delta transports MHR neutral segment;
    # it must match Blender's evaluated target bone direction despite A/T rests and rolls.
    conversion=Matrix(((1,0,0),(0,0,-1),(0,1,0)))
    anchor=rig.pose.bones['Root'].matrix.to_quaternion().to_matrix()@rig.data.bones['Root'].matrix_local.to_quaternion().to_matrix().transposed()
    errors=[]
    for name in ('LeftArm','RightArm','LeftForeArm','RightForeArm','LeftHandIndex2','RightHandThumb1'):
        row=result['joints'][name]
        expected=anchor@conversion@Matrix(row['rotation'])@Matrix(row['neutral_rotation']).transposed()@Vector(row['neutral_direction'])
        actual=rig.pose.bones[name].tail-rig.pose.bones[name].head
        errors.append(actual.normalized().angle(expected.normalized()))
    assert max(errors)<.001,errors
    addon.auto_pose.restore_channels(rig,before);bpy.context.view_layer.update()
    ip.apply(bpy.context,rig,result,hands=False)
    assert rig.pose.bones['LeftHandIndex2'].rotation_euler==before['LeftHandIndex2']['euler']
    addon.auto_pose.restore_channels(rig,before);bpy.context.view_layer.update()
    # Malformed results cannot partially write channels.
    for invalid in ('nan','reflection','missing'):
        bad=copy.deepcopy(result)
        if invalid=='nan':bad['joints']['LeftArm']['rotation'][0][0]=float('nan')
        if invalid=='reflection':bad['joints']['LeftArm']['rotation']=[[-1,0,0],[0,1,0],[0,0,1]]
        if invalid=='missing':del bad['joints']['LeftArm']
        try:ip.apply(bpy.context,rig,bad)
        except ValueError:pass
        else:raise AssertionError(invalid+' accepted')
        assert all(p.matrix_basis==before[p.name]['basis'] for p in rig.pose.bones)
    rows.append(dict(height=height,arm_angle=angle,length_error=length_error,basis_error=basis_error,direction_error_rad=max(errors)))
    rig.animation_data.action=None

# Stale request and correspondence rejection through the actual undoable apply operator.
image=out/'reference.png';im=bpy.data.images.new('Test Image',width=8,height=8);im.filepath_raw=str(image);im.file_format='PNG';im.save();bpy.data.images.remove(im)
folder=ip.prepare(bpy.context,rig,image,ip.cache(),parent=out)
request=json.loads((folder/'request.json').read_text());result.update(request_sha256=ip.sha(folder/'request.json'),input_sha256=request['input_sha256'])
(folder/'pose.json').write_text(json.dumps(result));(folder/'pose.sha256').write_text(ip.sha(folder/'pose.json'));addon.skinning._state(folder,'complete')
old=ip.fingerprint(bpy.context,rig);bpy.context.scene.frame_set(2);assert ip.fingerprint(bpy.context,rig)!=old
try:assert bpy.ops.local_character.apply_image_pose(folder=str(folder))=={'CANCELLED'}
except RuntimeError as error:assert 'changed during inference' in str(error)
bpy.context.scene.frame_set(1)
# Fingerprint is now equivalent, since there is no Action assigned at this point.
assert ip.fingerprint(bpy.context,rig)==request['fingerprint']
assert bpy.ops.local_character.apply_image_pose(folder=str(folder))=={'FINISHED'}
assert addon.skinning.poll(folder)['status']=='applied'
addon.motion_keyframes.capture(bpy.context,rig)
assert len(addon.motion_keyframes.data(rig)['poses'])==1

ui_ctx=SimpleNamespace(mode='OBJECT',active_object=rig,area=SimpleNamespace(type='VIEW_3D'),
    region=SimpleNamespace(type='UI',active_panel_category='Rigmodo'),scene=bpy.context.scene)
bpy.context.scene.lc_settings.ui_step='MOTION';assert ip.LC_FH_image_pose.poll_drop(ui_ctx)
ui_ctx.region.active_panel_category='Item';assert not ip.LC_FH_image_pose.poll_drop(ui_ctx)
ui_ctx.region.active_panel_category='Rigmodo';ui_ctx.region.type='WINDOW';assert not ip.LC_FH_image_pose.poll_drop(ui_ctx)
ui_ctx.region.type='UI';bpy.context.scene.lc_settings.ui_step='SKIN';assert not ip.LC_FH_image_pose.poll_drop(ui_ctx)
ip.register();assert bpy.app.handlers.load_pre.count(ip.reset_jobs)==1
native_patch=ip._native_drop_patch
addon.unregister();assert ip.reset_jobs not in bpy.app.handlers.load_pre and not bpy.app.timers.is_registered(ip.tick)
assert native_patch and native_patch[0].__dict__['poll_drop'] is native_patch[1]
addon.register()
avatar=None
avatar_fixture=Path.home()/'AppData/Local/Temp/rigmodo-auto-skin-acceptance/skin-review.blend'
if avatar_fixture.is_file():
    with bpy.data.libraries.load(str(avatar_fixture),link=False) as (src,dst):dst.objects=src.objects
    for obj in dst.objects:
        if obj:bpy.context.scene.collection.objects.link(obj);obj.hide_set(False);obj.hide_viewport=False
    avatar_rig=next(o for o in dst.objects if o and o.type=='ARMATURE')
    meshes=[o for o in dst.objects if o and o.type=='MESH' and any(m.type=='ARMATURE' and m.object==avatar_rig for m in o.modifiers)]
    for obj in bpy.context.selected_objects:obj.select_set(False)
    avatar_rig.select_set(True);bpy.context.view_layer.objects.active=avatar_rig;bpy.context.view_layer.update()
    action=avatar_rig.animation_data.action if avatar_rig.animation_data else None
    counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.actions))
    geometry={m.name:[v.co[:] for v in m.data.vertices] for m in meshes}
    snap=addon.auto_pose.channel_snapshot(avatar_rig)
    ip.apply(bpy.context,avatar_rig,result)
    dg=bpy.context.evaluated_depsgraph_get()
    evaluated=[np.asarray([v.co[:] for v in m.evaluated_get(dg).data.vertices]) for m in meshes]
    assert meshes and all(np.isfinite(v).all() for v in evaluated)
    assert geometry=={m.name:[v.co[:] for v in m.data.vertices] for m in meshes}
    assert counts==(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.actions))
    assert (avatar_rig.animation_data.action if avatar_rig.animation_data else None)==action
    addon.auto_pose.restore_channels(avatar_rig,snap);bpy.context.view_layer.update()
    assert all(p.matrix_basis==snap[p.name]['basis'] for p in avatar_rig.pose.bones)
    avatar=dict(vertices=sum(len(m.data.vertices) for m in meshes),finite_deformation=True,source_geometry_preserved=True,action_preserved=True)
receipt=dict(passed=True,version=addon.exporter.VERSION,fixture='Real public MHR skeleton with authored model parameters',sam_neural_inference_tested=False,
             cases=rows,stale_frame_rejected=True,malformed_results_atomic=True,same_objects_and_action=True,root_placement_preserved=True,
             hands_opt_out=True,capture_pose=True,scoped_drop_poll=True,lifecycle_cleanup=True,avatar=avatar,extracted_extension=len(args)>1)
(out/'results.json').write_text(json.dumps(receipt,indent=2));print('IMAGE_POSE_ACCEPTANCE',json.dumps(receipt))
