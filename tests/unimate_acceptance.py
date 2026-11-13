"""Blender: --factory-startup --background --python THIS -- OUTPUT [--model BLEND]."""
import importlib.util,json,math,sys,time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix

args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
root=Path(__file__).resolve().parents[1];name='rigmodo_unimate_test'
spec=importlib.util.spec_from_file_location(name,root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[name]=addon;spec.loader.exec_module(addon);addon.register()
bpy.context.preferences.addons.new().module=name
u=addon.unimate;g=u.geometry

def check(condition,message):
    if not condition:raise AssertionError(message)

def curves(action):
    return [c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]

def unit():
    bpy.ops.object.armature_add();rig=bpy.context.object;rig.name='Motion Test'
    bpy.ops.object.mode_set(mode='EDIT');bones=rig.data.edit_bones;root_bone=bones[0];root_bone.name='Root';root_bone.use_deform=False
    parent=root_bone
    for i in range(5):
        b=bones.new('Joint'+str(i));b.head=(0,i*.25,.6+i*.07);b.tail=(.04,i*.25+.2,.65+i*.07);b.roll=.3*i;b.parent=parent;parent=b
    bpy.ops.object.mode_set(mode='OBJECT');rig.matrix_world=Matrix.Rotation(.7,4,'Z')@Matrix.Diagonal((1.7,1.7,1.7,1.));rig.location=(2,3,1)
    rig.pose.bones['Joint2'].rotation_mode='QUATERNION';rig.pose.bones['Joint2'].rotation_quaternion=(1,0,0,0)
    rig.pose.bones['Joint2'].keyframe_insert(data_path='rotation_quaternion',frame=2)
    bpy.context.view_layer.update()
    source_action=rig.animation_data.action;before=u.source_signature(rig);source_digest=addon.skinning._digest(rig,[])
    folder=u.prepare(bpy.context,rig,'An object bends.',30,101,False,'Y',3.,str(u.cache()),parent=out)
    request=json.loads((folder/'request.json').read_text());s=request['skeleton'];canon=g.canonicalize(s)
    check(s['structural_root']=='Root' and s['bone_names'][0]=='Joint0' and s['bone_names'][-1] is None,'Structural root/tip export')
    features=np.zeros((30,len(s['parents']),12));features[:,:,:3]=canon['positions'];features[:,:,3:9]=[1,0,0,0,1,0]
    features[:,0,1]=canon['positions'][0,1]
    positions,rotations=g.decode(features,canon)
    check(np.max(np.abs(positions-np.asarray(s['heads'])))<1e-8,'Rest feature recovery')
    np.savez(folder/'motion.npz',positions=positions,rotations=rotations)
    report=dict(schema_version=1,provider='unimate',request_sha256=u.sha(folder/'request.json'),output_sha256=u.sha(folder/'motion.npz'),fps=30,frames=30)
    (folder/'result.json').write_text(json.dumps(report));addon.skinning._state(folder,'complete')
    rig.data.bones['Joint1'].lc_unimate_label='Changed'
    try:u.apply(bpy.context,folder);raise AssertionError('Stale labels accepted')
    except ValueError:pass
    rig.data.bones['Joint1'].lc_unimate_label=''
    curve=curves(source_action)[0];key=curve.keyframe_points[0];old=key.co.y;key.co.y=old+.1
    try:u.apply(bpy.context,folder);raise AssertionError('Changed Action accepted')
    except ValueError:pass
    key.co.y=old
    collection,target,meshes,action,_=u.apply(bpy.context,folder)
    bpy.context.scene.frame_set(2);bpy.context.view_layer.update()
    error=max(max(abs(v) for row in (p.matrix-p.bone.matrix_local) for v in row) for p in target.pose.bones)
    check(error<2e-5,'Rest-frame inverse bake '+str(error))
    check(rig.animation_data.action==source_action and u.source_signature(rig)==before and addon.skinning._digest(rig,[])==source_digest,'Source preserved '+str((rig.animation_data.action==source_action,u.source_signature(rig)==before,addon.skinning._digest(rig,[])==source_digest)))
    check(len(curves(action))==5*4+3,'Quaternion and moving-body root channels')
    try:u.apply(bpy.context,folder);raise AssertionError('Duplicate apply accepted')
    except ValueError:pass
    result=dict(passed=True,rest_bake_max_error=error,stale_labels_rejected=True,stale_action_rejected=True,source_preserved=True,virtual_tips=True)
    (out/'unit.json').write_text(json.dumps(result,indent=2));print('UNIMATE_UNIT_PASS',json.dumps(result),flush=True)

def annotate_scorpion(rig):
    rig.lc_unimate_forward='X'
    labels={0:'Pelvis',1:'Spine',2:'Spine',3:'Tail',4:'Tail',5:'Tail',6:'Tail End',22:'Neck',23:'Head',24:'Jaw',25:'Jaw',26:'Jaw End'}
    for start,side,part in [(7,'Right','Hind'),(10,'Left','Hind'),(13,'Right','Middle'),(16,'Right','Middle'),(19,'Left','Middle'),(41,'Right','Front'),(46,'Left','Front')]:
        count=5 if start in (41,46) else 3
        for j in range(count):labels[start+j]=side+' '+part+' '+(['Hip','Knee','Foot'] if count==3 else ['Hip','Thigh','Knee','Ankle','Foot'])[j]
    for start,side in [(27,'Right'),(34,'Left')]:
        for j,part in enumerate(['Shoulder','Arm','Forearm','Claw','Claw End','Finger','Finger End']):labels[start+j]=side+' '+part
    for i,label in labels.items():
        b=rig.data.bones.get(f'Creature_{i:03d}')
        if b:b.lc_unimate_label=label

def model(blend):
    bpy.ops.wm.open_mainfile(filepath=blend);rig=bpy.context.view_layer.objects.active
    check(rig and rig.type=='ARMATURE','Select the Scorpion rig in test copy');annotate_scorpion(rig)
    for obj in bpy.context.selected_objects:obj.select_set(False)
    rig.select_set(True)
    meshes=addon.motion_jobs.character_meshes(bpy.context,rig)
    before=addon.skinning._digest(rig,meshes);action=u.source_signature(rig);count=len(bpy.data.objects);frame=bpy.context.scene.frame_current
    folder=u.prepare(bpy.context,rig,'An object walks forward.',60,101,False,rig.lc_unimate_forward,3.,str(u.cache()),parent=out)
    (out/'model-job.txt').write_text(str(folder));u.start(folder)
    while True:
        state=addon.skinning.poll(folder)
        if state['status']!='running':break
        time.sleep(.5)
    check(state['status']=='complete','Model failed: '+str(state))
    request,report,positions,rotations=u.output(folder)
    check(np.max(np.abs(rotations[1:]-rotations[:-1]))>1e-4,'Motion must vary')
    collection,target,copies,new_action,report=u.apply(bpy.context,folder)
    check(addon.skinning._digest(rig,meshes)==before and u.source_signature(rig)==action,'Source rig/weights/Action preserved')
    check(bpy.context.scene.frame_current==frame,'Current frame preserved')
    target_points=[]
    for f in (1,12,24,36,48):
        bpy.context.scene.frame_set(f);bpy.context.view_layer.update()
        target_points.append([(target.matrix_world@p.head).to_tuple() for p in target.pose.bones])
        for p in target.pose.bones:check(abs(p.length-p.bone.length)<2e-4,'Bone length changed')
        for mesh in copies:
            evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            check(all(math.isfinite(v) for vertex in evaluated.data.vertices for v in vertex.co),'Invalid deformation')
    bpy.context.scene.frame_set(frame)
    for obj in bpy.context.selected_objects:obj.select_set(False)
    for obj in [target,*copies]:obj.select_set(True)
    bpy.context.view_layer.objects.active=target
    settings=bpy.context.scene.lc_settings;settings.profile='GENERIC';settings.include_action=True;settings.character_name='ScorpionUniMate';settings.export_directory=str(out/'export')
    export=addon.exporter.export_bundle(bpy.context,target,copies,settings.export_directory,settings.character_name,'GENERIC',True,False)
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'scorpion-unimate-review.blend'),copy=True)
    report.update(passed=True,job=str(folder),source_preserved=True,source_objects=count,created_objects=1+len(copies),action=new_action.name,
        animated_joint_variation=float(np.max(np.ptp(np.asarray(target_points),axis=0))),export=str(export),review=str(out/'scorpion-unimate-review.blend'))
    (out/'model.json').write_text(json.dumps(report,indent=2));print('UNIMATE_MODEL_PASS',json.dumps(report),flush=True)

if '--model' in args:model(args[args.index('--model')+1])
else:unit()
