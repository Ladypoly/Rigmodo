"""Fresh unnamed original rig → automatic annotation → real UniMate → loop copy."""
import bpy,importlib.util,json,sys,time,math
from pathlib import Path
import numpy as np
from mathutils import Vector
r=Path(__file__).resolve().parents[1];args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('rigmodo_auto_motion_test',r/'__init__.py',submodule_search_locations=[str(r)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register();bpy.context.preferences.addons.new().module=spec.name
bpy.ops.wm.open_mainfile(filepath=args[1]);rig=bpy.data.objects['Armature']
for b in rig.data.bones:b.lc_unimate_label=''
rig.pop('lc_creature_annotation',None);rig.lc_unimate_forward='AUTO'
for o in bpy.context.selected_objects:o.select_set(False)
rig.hide_set(False);rig.select_set(True);bpy.context.view_layer.objects.active=rig
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.parent==rig]
for o in meshes:o.hide_set(False)
before=a.skinning._digest(rig,meshes);action=a.unimate.source_signature(rig)
folder=a.unimate.prepare(bpy.context,rig,'An object attacks forward.',60,101,True,'AUTO',3.,str(a.unimate.cache()),parent=out);a.unimate.start(folder)
while True:
    status=a.skinning.poll(folder)
    if status['status']!='running':break
    time.sleep(.3)
assert status['status']=='complete',(status,(folder/'worker.log').read_text(errors='replace')[-1500:])
collection,target,copies,new_action,report=a.unimate.apply(bpy.context,folder)
assert a.skinning._digest(rig,meshes)==before and a.unimate.source_signature(rig)==action
annotation=json.loads(rig['lc_creature_annotation']);assert annotation['confidence']=='geometry' and annotation['forward'][0]>.99
loop=a.motion_finish.loop(bpy.context,target,8);points=[]
for frame in (1,49):
 bpy.context.scene.frame_set(frame);bpy.context.view_layer.update();points.append(np.asarray([tuple(target.matrix_world@p.head) for p in target.pose.bones]))
error=float(np.max(np.abs(points[0]-points[1])));assert error<1e-5,error
assert new_action.use_fake_user and loop!=new_action
report.update(passed=True,automatic_original_tripo=True,automatic_heading=annotation['forward'],labelled_bones=len(annotation['automatic_labels']),source_preserved=True,loop_pose_max_error=error,unlooped_action_retained=True)
(out/'results.json').write_text(json.dumps(report,indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(out/'auto-creature-loop-review.blend'),copy=True)
print('AUTO_CREATURE_MOTION_ACCEPTANCE',json.dumps(report),flush=True)
