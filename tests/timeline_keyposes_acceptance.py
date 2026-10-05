# SPDX-License-Identifier: GPL-3.0-or-later
"""Native Action keys -> real Kimodo conditioning -> exact retargeted anchors."""
import addon_utils, importlib, json, math, shutil, sys, time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Quaternion

assert bpy.app.background and '--factory-startup' in sys.argv
args=sys.argv[sys.argv.index('--')+1:]
out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
extracted=len(args)>1
if extracted:
    import importlib.util
    source=Path(args[1]);spec=importlib.util.spec_from_file_location('rigmodo_archive',source/'__init__.py',submodule_search_locations=[str(source)])
    addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
else:
    addon_utils.enable('bl_ext.user_default.local_character',default_set=True)
    addon=importlib.import_module('bl_ext.user_default.local_character')
mk,mj,ma=addon.motion_keyframes,addon.motion_jobs,addon.motion_apply
rows=[]

def snapshot(rig):
    return addon.auto_pose.channel_snapshot(rig)

def unchanged(rig,saved):
    for p in rig.pose.bones:
        v=saved[p.name]
        assert p.rotation_mode==v['mode']
        for actual,key in ((p.location,'location'),(p.scale,'scale'),(p.rotation_quaternion,'quaternion'),
                           (p.rotation_euler,'euler'),(p.rotation_axis_angle,'axis')):
            assert max(abs(a-b) for a,b in zip(actual,v[key]))<1e-7,(p.name,key)

def fake_result(folder):
    for name in ('root_positions.f32','local_rotations_xyzw.f32'):
        shutil.copyfile(mj.cache()/'evaluation/walk'/name,folder/name)
    mj.finish(folder);addon.skinning._state(folder,'complete')

for case,(fps,start,angle) in enumerate(((30,1,0),(24,101,45),(30,1,25))):
    scene=bpy.context.scene;scene.render.fps=fps;scene.frame_start=start
    if case==2:
        fixture=Path.home()/'AppData/Local/Temp/rigmodo-auto-skin-acceptance/skin-review.blend'
        with bpy.data.libraries.load(str(fixture),link=False) as (src,dst):dst.objects=src.objects
        for obj in dst.objects:
            if obj:bpy.context.scene.collection.objects.link(obj);obj.hide_set(False);obj.hide_viewport=False
        rig=next(o for o in dst.objects if o and o.type=='ARMATURE')
        for obj in bpy.context.selected_objects:obj.select_set(False)
        rig.select_set(True);bpy.context.view_layer.objects.active=rig
    else:rig=addon.skeleton.create_armature(bpy.context,1.75,angle)
    if case==1:
        bpy.ops.object.mode_set(mode='EDIT')
        source=rig.data.edit_bones['RightForeArm'];helper=rig.data.edit_bones.new('RightForeArmTwist')
        helper.head=source.head;helper.tail=source.tail;helper.roll=source.roll;helper.parent=source.parent
        bpy.ops.object.mode_set(mode='OBJECT')
        rig['lc_twists']=json.dumps([dict(source='RightForeArm',helper='RightForeArmTwist',fraction=.5)])
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    rig.animation_data_create();rig.animation_data.action=bpy.data.actions.new('Sparse Pose Guides')
    action=rig.animation_data.action
    rig.pose.bones['LeftHandIndex1'].rotation_mode='XYZ'
    rig.pose.bones['RightForeArm'].rotation_mode='AXIS_ANGLE'
    frames=[start,start+44*fps/30,start+89*fps/30]
    for i,frame in enumerate(frames):
        scene.frame_set(math.floor(frame),subframe=frame%1)
        rig.pose.bones['Root'].location.x=i*.15
        rig.pose.bones['Root'].keyframe_insert('location',frame=frame)
        rig.pose.bones['LeftArm'].rotation_quaternion=Quaternion((0,0,1),i*.4)
        rig.pose.bones['LeftArm'].keyframe_insert('rotation_quaternion',frame=frame)
        rig.pose.bones['LeftHandIndex1'].rotation_euler.x=i*.25
        rig.pose.bones['LeftHandIndex1'].keyframe_insert('rotation_euler',frame=frame)
        rig.pose.bones['RightForeArm'].rotation_axis_angle=(i*.35,0,1,0) if case==1 else (i*.35,1,0,0)
        rig.pose.bones['RightForeArm'].keyframe_insert('rotation_axis_angle',frame=frame)
        rig.pose.bones['Neck'].keyframe_insert('rotation_quaternion',frame=frame)
    # Outside keys and unrelated Action slots must not become guide frames.
    rig.pose.bones['LeftArm'].keyframe_insert('rotation_quaternion',frame=start-10)
    rig.pose.bones['LeftArm'].keyframe_insert('rotation_quaternion',frame=frames[-1]+10)
    other=addon.skeleton.create_armature(bpy.context,1.75,0)
    other.animation_data_create();other.animation_data.action=action
    other.animation_data.action_slot=action.slots.new(id_type='OBJECT',name='Other Character')
    other.pose.bones['LeftArm'].keyframe_insert('rotation_quaternion',frame=start+20)
    other.select_set(False);rig.select_set(True);bpy.context.view_layer.objects.active=rig
    expected=[]
    for frame in frames:
        scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update()
        addon.twists.update_pose(rig);bpy.context.view_layer.update()
        expected.append({p.name:np.asarray(p.matrix).copy() for p in rig.pose.bones})
    scene.frame_set(start+7,subframe=.25)
    # Unkeyed live channels must survive sampling; the active Action stays intact.
    rig.pose.bones['Spine2'].rotation_quaternion=Quaternion((1,0,0),.12)
    bpy.context.view_layer.update()
    for frame in frames:
        scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update()
        addon.twists.update_pose(rig);bpy.context.view_layer.update()
        expected[frames.index(frame)]={p.name:np.asarray(p.matrix).copy() for p in rig.pose.bones}
    scene.frame_set(start+7,subframe=.25);bpy.context.view_layer.update()
    saved=snapshot(rig);timeline=(scene.frame_current,scene.frame_subframe)
    source_digest=addon.skinning._digest(rig,meshes)
    keys=mk.prepare(bpy.context,rig,90,start)
    assert np.allclose([p['frame'] for p in keys['poses']],frames,atol=1e-5)
    assert [p['index'] for p in keys['poses']]==[0,44,89]
    assert (scene.frame_current,scene.frame_subframe)==timeline
    unchanged(rig,saved)
    assert rig.animation_data.action==action and addon.skinning._digest(rig,meshes)==source_digest
    # Scrubbing must not invalidate the Action-bound fingerprint.
    scene.frame_set(start+15);assert mk.prepare(bpy.context,rig,90,start)['source_sha256']==keys['source_sha256']
    scene.frame_set(*timeline[:1],subframe=timeline[1]);bpy.context.view_layer.update()
    folder=mj.prepare(bpy.context,rig,'A person raises their left arm while stepping forward.',90,20,101,
                      parent=out,keyframes=True,start_frame=start)
    if case==0 and not extracted:
        mj.start(folder)
        while addon.skinning.poll(folder)['status']=='running':time.sleep(.2)
        assert addon.skinning.poll(folder)['status']=='complete',(folder/'worker.log').read_text(errors='replace')[-1500:]
    else:fake_result(folder)
    _,copy,copy_meshes,generated,diagnostics=ma.apply(bpy.context,folder,contacts=True,heading=True)
    assert action==rig.animation_data.action and generated!=action
    maximum=0.
    for frame,matrices in zip(frames,expected):
        scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update()
        for p in copy.pose.bones:maximum=max(maximum,float(np.max(np.abs(np.asarray(p.matrix)-matrices[p.name]))))
    assert maximum<1e-5,maximum
    assert addon.skinning._digest(rig,meshes)==source_digest
    dg=bpy.context.evaluated_depsgraph_get()
    assert all(math.isfinite(c) for m in copy_meshes for v in m.evaluated_get(dg).data.vertices for c in v.co)
    # Editing, moving, deleting or swapping source keys rejects before allocation.
    bpy.context.view_layer.objects.active=rig
    for change in ('edit','move','delete','redundant_delete','action','slot'):
        pending=mj.prepare(bpy.context,rig,'walk',90,parent=out,keyframes=True,start_frame=start);fake_result(pending)
        curve=next(c for c in mk.pose_curves(rig) if c.data_path.endswith('rotation_euler') and c.array_index==0)
        if change=='redundant_delete':curve=next(c for c in mk.pose_curves(rig) if c.data_path==rig.pose.bones['Neck'].path_from_id()+'.rotation_quaternion' and c.array_index==0)
        point=curve.keyframe_points[1];co=tuple(point.co)
        if change=='edit':point.co.y+=.2;curve.update();restore=lambda:setattr(point,'co',co)
        elif change=='move':point.co.x+=1;curve.update();restore=lambda:setattr(point,'co',co)
        elif change in {'delete','redundant_delete'}:curve.keyframe_points.remove(point);curve.update();restore=lambda:curve.keyframe_points.insert(*co)
        elif change=='action':
            replacement=action.copy();slot=rig.animation_data.action_slot
            rig.animation_data.action=replacement
            restore=lambda:setattr(rig.animation_data,'action',action)
        else:
            slot=rig.animation_data.action_slot;rig.animation_data.action_slot=other.animation_data.action_slot
            restore=lambda:setattr(rig.animation_data,'action_slot',slot)
        counts=(len(bpy.data.objects),len(bpy.data.actions))
        try:
            ma.apply(bpy.context,pending)
            raise AssertionError('Stale '+change+' accepted')
        except ValueError:pass
        finally:
            restore();curve.update()
            if change=='action':rig.animation_data.action_slot=slot
        assert counts==(len(bpy.data.objects),len(bpy.data.actions))
    # Empty Action and invalid sampled scaling fail without changing the working pose/frame.
    rig.animation_data.action_slot=action.slots.new(id_type='OBJECT',name='Empty')
    try:mk.prepare(bpy.context,rig,90,start);raise AssertionError('Empty slot accepted')
    except ValueError:pass
    rig.animation_data.action_slot=slot if change=='slot' else rig.animation_data.action_slot
    # Restore this rig's original keyed slot by identifier.
    rig.animation_data.action_slot=next(s for s in action.slots if s!=other.animation_data.action_slot and s.identifier!='OBEmpty')
    scene.frame_set(start+7,subframe=.25);bpy.context.view_layer.update()
    rig.pose.bones['LeftArm'].scale=(2,1,1);rig.pose.bones['LeftArm'].keyframe_insert('scale',frame=frames[1])
    rig.pose.bones['LeftArm'].scale=(1,1,1);bpy.context.view_layer.update();saved=snapshot(rig)
    timeline=(scene.frame_current,scene.frame_subframe)
    try:mk.prepare(bpy.context,rig,90,start);raise AssertionError('Scaled bone accepted')
    except ValueError:pass
    unchanged(rig,saved);assert timeline==(scene.frame_current,scene.frame_subframe)
    rows.append(dict(fps=fps,start=start,arm_angle=angle,source_frames=frames,max_anchor_matrix_error=maximum,
                     actual_kimodo_inference=case==0 and not extracted,avatar_vertices=sum(len(m.data.vertices) for m in meshes),
                     finite_skin_deformation=True,diagnostics=diagnostics))

receipt=dict(passed=True,version=addon.exporter.VERSION,extracted_extension=extracted,cases=rows,partial_bone_keys=True,
             quaternion_euler_axis_angle=True,multiple_action_slots=True,outside_keys_ignored=True,
             timeline_and_working_pose_preserved=True,source_action_preserved=True,stale_key_edits_rejected=True,
             invalid_sampling_restores_pose=True,twists_derived_from_timeline=True)
(out/'results.json').write_text(json.dumps(receipt,indent=2));print('TIMELINE_KEYPOSES_ACCEPTANCE',json.dumps(receipt),flush=True)
