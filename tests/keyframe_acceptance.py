"""Real conditioned inference, inverse retargeting, source preservation and export."""
import importlib.util,json,math,sys,time,shutil
from pathlib import Path
import bpy,numpy as np
from mathutils import Quaternion,Vector
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import skeleton,motion_data,motion_apply,motion_jobs,motion_keyframes,skinning,exporter
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
roots,rotations=motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
bpy.context.scene.render.fps=30;results=[]
def check(value,text):
    if not value:raise AssertionError(text)
def select(rig,mesh=None):
    for obj in bpy.context.selected_objects:obj.select_set(False)
    rig.select_set(True)
    if mesh:mesh.select_set(True)
    bpy.context.view_layer.objects.active=rig
def fake_result(folder):
    for name in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copy2(motion_jobs.cache()/'evaluation/walk'/name,folder/name)
    motion_jobs.finish(folder);skinning._state(folder,'complete')
for angle,fps,unit,start in ((0,30,1.,1),(55,24,.01,101)):
    bpy.context.scene.render.fps=fps;bpy.context.scene.unit_settings.scale_length=unit
    rig=skeleton.create_armature(bpy.context,1.75,angle);select(rig)
    action=motion_apply.bake(bpy.context,rig,roots,rotations,start_frame=start,root_origin=(0,0,0),heading=True)
    before=skinning._digest(rig,[]);frames=[start,start+44*fps/30,start+89*fps/30];snapshots=[]
    for index,frame in zip((0,44,89),frames):
        bpy.context.scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update()
        rig.pose.bones['LeftHandIndex1'].rotation_mode='QUATERNION'
        rig.pose.bones['LeftHandIndex1'].rotation_quaternion=Quaternion((1,0,0),.2+index/100)
        p=motion_keyframes.capture(bpy.context,rig)
        # Inverse rotations must match known native source rotations (apart
        # from optional Neck2, which has no corresponding Mixamo bone).
        _,global_rot=motion_data.forward(roots,rotations)
        for canonical,name in motion_data.MAPPING.items():
            if canonical in rig.data.bones:
                j=motion_data.NAMES.index(name)
                check(np.max(np.abs(np.array(p['global_rotations'][j])-global_rot[index,j]))<1e-5,'Inverse rest calibration failed '+canonical)
        check(np.max(np.abs(np.array(p['root'])-roots[index]))<1e-5,'Root movement inverse failed')
        # Author a different path, so the original unconstrained walk is not
        # already the exact answer. Keep the poses reachable and compatible.
        rig.pose.bones['Root'].location.x+=index*.007
        bpy.context.view_layer.update();p=motion_keyframes.capture(bpy.context,rig)
        snapshots.append({b.name:np.array(b.matrix) for b in rig.pose.bones})
    keys=motion_keyframes.prepare(bpy.context,rig,90,start)
    folder=motion_jobs.prepare(bpy.context,rig,'A person walks forward naturally at a steady pace.',90,100,101,parent=output,keyframes=True,start_frame=start)
    if angle==0:
        motion_jobs.start(folder)
        while skinning.poll(folder)['status']=='running':time.sleep(.2)
        check(skinning.poll(folder)['status']=='complete','Native keyframed inference failed: '+(folder/'worker.log').read_text(errors='replace')[-1000:])
    else:fake_result(folder)
    timeline=bpy.context.scene.frame_current+bpy.context.scene.frame_subframe
    collection,copy,meshes,new_action,diagnostics=motion_apply.apply(bpy.context,folder,contacts=True,heading=True)
    check(action is rig.animation_data.action and action!=new_action,'Source Action changed')
    check(before==skinning._digest(rig,[]),'Source rest changed')
    check(abs(bpy.context.scene.frame_current+bpy.context.scene.frame_subframe-timeline)<1e-5,'Timeline changed')
    max_error=0
    for frame,expected in zip(frames,snapshots):
        bpy.context.scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update()
        for b in copy.pose.bones:max_error=max(max_error,float(np.max(np.abs(np.array(b.matrix)-expected[b.name]))))
    check(max_error<1e-5,'Exact artist anchor failed '+str(max_error))
    # Each changed source/transport condition must reject before allocation.
    for change in ('poses','fps','request','mask','rest'):
        pending=motion_jobs.prepare(bpy.context,rig,'walk',90,parent=output,keyframes=True,start_frame=start);fake_result(pending)
        restore=None
        if change=='poses':saved=rig[motion_keyframes.PROPERTY];rig[motion_keyframes.PROPERTY]=saved+' ';restore=lambda:rig.__setitem__(motion_keyframes.PROPERTY,saved)
        elif change=='fps':saved=bpy.context.scene.render.fps;bpy.context.scene.render.fps=saved+1;restore=lambda:setattr(bpy.context.scene.render,'fps',saved)
        elif change=='request':(pending/'request.json').write_text((pending/'request.json').read_text()+' ')
        elif change=='mask':(pending/'observed_mask.f32').write_bytes(b'bad')
        else:saved=rig.data.bones['LeftArm'].use_deform;rig.data.bones['LeftArm'].use_deform=False;restore=lambda:setattr(rig.data.bones['LeftArm'],'use_deform',saved)
        count=(len(bpy.data.objects),len(bpy.data.actions))
        try:motion_apply.apply(bpy.context,pending);raise AssertionError('Stale '+change+' accepted')
        except ValueError:pass
        finally:
            if restore:restore()
        check(count==(len(bpy.data.objects),len(bpy.data.actions)),'Stale result allocated data')
    results.append(dict(arm_angle=angle,scene_fps=fps,unit_scale=unit,start_frame=start,anchor_frames=frames,max_anchor_matrix_error=max_error,job=str(folder),diagnostics=diagnostics))
    if angle==0:
        # A weighted per-bone octahedron fixture tests full animated LBS parity.
        vertices=[];faces=[];groups=[]
        for bone in copy.data.bones:
            if not bone.use_deform:continue
            center=bone.head_local.lerp(bone.tail_local,.5);base=len(vertices)
            vertices.extend(tuple(center+Vector(v)*.007) for v in ((1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)))
            faces.extend(tuple(base+i for i in f) for f in ((0,2,4),(2,1,4),(1,3,4),(3,0,4),(2,0,5),(1,2,5),(3,1,5),(0,3,5)))
            groups.append((bone.name,list(range(base,base+6))))
        data=bpy.data.meshes.new('KeyPoseGeometry');data.from_pydata(vertices,[],faces)
        mesh=bpy.data.objects.new('KeyPoseGeometry',data);bpy.context.scene.collection.objects.link(mesh);mesh.parent=copy;mesh.modifiers.new('Skin','ARMATURE').object=copy
        for name,ids in groups:mesh.vertex_groups.new(name=name).add(ids,1.,'REPLACE')
        select(copy,mesh)
        sys.path.insert(0,str(root/'tests'));import motion_reference
        for profile in ('HUMANOID','GENERIC'):
            bundle=exporter.export_bundle(bpy.context,copy,[mesh],str(output),'KeyPoses'+profile,profile,include_action=True)
            motion_reference.write(copy,[mesh],bundle)
        # Same seed/prompt, unconstrained inference is an independent baseline.
        select(rig);plain=motion_jobs.prepare(bpy.context,rig,'A person walks forward naturally at a steady pace.',90,100,101,parent=output)
        motion_jobs.start(plain)
        while skinning.poll(plain)['status']=='running':time.sleep(.2)
        check(skinning.poll(plain)['status']=='complete','Unconstrained comparison failed')
        unroot,unrot=motion_data.load(plain,90);unpos,_=motion_data.forward(unroot,unrot)
        rawroot,rawrot=motion_data.load(folder,90);rawpos,_=motion_data.forward(rawroot,rawrot)
        expected=[]
        for p in keys['poses']:
            pos=np.empty((30,3));rot=np.array(p['global_rotations'])
            for j,parent in enumerate(motion_data.PARENTS):pos[j]=p['root'] if parent<0 else pos[parent]+rot[parent]@motion_data.OFFSETS[j]
            expected.append(pos)
        indices=[0,44,89];constrained=float(np.linalg.norm(rawpos[indices]-expected,axis=-1).mean());unconstrained=float(np.linalg.norm(unpos[indices]-expected,axis=-1).mean())
        check(constrained<unconstrained,'Conditioned sampling did not improve anchor accuracy')
        check(np.max(np.abs(rawpos[10:35]-unpos[10:35]))>.005,'Conditioning did not change intervening model motion')
        results[-1]['independent_comparison']=dict(conditioned_mean_joint_error_m=constrained,unconditioned_mean_joint_error_m=unconstrained,plain_job=str(plain))
        print('REAL_KEYFRAME_INFERENCE_PASSED',json.dumps(results[-1]),flush=True)
(output/'results.json').write_text(json.dumps(dict(passed=True,cases=results),indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(output/'keyframe-review.blend'))
print('KEYFRAME_ACCEPTANCE_PASSED',output,flush=True)
