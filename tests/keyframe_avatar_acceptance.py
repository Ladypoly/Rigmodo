"""Pose-mode controls and real inference on a private capture of the live avatar."""
import addon_utils,importlib,json,math,sys,time,hashlib,shutil
from pathlib import Path
from types import SimpleNamespace
import bpy,numpy as np
name='bl_ext.user_default.local_character';addon_utils.enable(name,default_set=True);addon=importlib.import_module(name)
motion_keyframes,motion_jobs,motion_apply,skinning,exporter,workflow,ui=(getattr(addon,n) for n in ('motion_keyframes','motion_jobs','motion_apply','skinning','exporter','workflow','ui'))
args=sys.argv[sys.argv.index('--')+1:];output=Path(args[0]);output.mkdir(parents=True,exist_ok=True)
with bpy.data.libraries.load(args[1]) as (available,loaded):loaded.objects=available.objects
for obj in loaded.objects:
    if obj: bpy.context.scene.collection.objects.link(obj)
rig=next(o for o in loaded.objects if o and o.type=='ARMATURE')
meshes=[o for o in loaded.objects if o and o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
before=skinning._digest(rig,meshes);source_action=rig.animation_data.action
def action_hash(a):return hashlib.sha256(json.dumps([(c.data_path,c.array_index,[list(p.co) for p in c.keyframe_points]) for l in a.layers for s in l.strips for bag in s.channelbags for c in bag.fcurves]).encode()).hexdigest()
source_hash=action_hash(source_action);workflow.select(bpy.context,rig,meshes);s=bpy.context.scene.lc_settings
bpy.context.scene.render.fps=24;s.motion_frames=90;s.motion_start_frame=1;s.ui_step='MOTION'
snapshots=[]
assert bpy.ops.local_character.test_pose()=={'FINISHED'}
for index,frame in enumerate((1,37,72)):
    bpy.context.scene.frame_set(frame);rig.pose.bones['Root'].location.x+=index*.2
    bpy.context.view_layer.update();assert bpy.ops.local_character.capture_key_pose()=={'FINISHED'}
    snapshots.append({p.name:np.array(p.matrix) for p in rig.pose.bones})
assert s.motion_use_keyframes and bpy.context.mode=='POSE' and source_action is rig.animation_data.action
# Recall is a temporary editing pose. Original keyed animation is untouched.
assert bpy.ops.local_character.key_pose(frame=37)=={'FINISHED'} and action_hash(source_action)==source_hash
class Layout:
    def __init__(self):self.records=[]
    def row(self,**kwargs):return self
    def box(self):return self
    def separator(self):pass
    def label(self,**kwargs):self.records.append(('label',kwargs.get('text','')))
    def prop(self,data,key,**kwargs):assert hasattr(data,key);self.records.append(('prop',key))
    def operator(self,key,**kwargs):assert hasattr(bpy.ops.local_character,key.split('.')[-1]);self.records.append(('operator',key));return SimpleNamespace()
    def panel(self,key,**kwargs):return self,None
layout=Layout();ui.draw(layout,bpy.context)
assert ('operator','local_character.capture_key_pose') in layout.records
assert ('prop','motion_start_frame') in layout.records
assert not set(addon.configuration.KEYS)&{key for kind,key in layout.records if kind=='prop'}
assert bpy.ops.local_character.object_mode()=={'FINISHED'}
assert set(bpy.context.selected_objects)==set([rig,*meshes]),'Finishing pose editing lost avatar mesh scope'
folder=motion_jobs.prepare(bpy.context,rig,'A person walks forward naturally at a steady pace.',90,100,101,parent=output,keyframes=True,start_frame=1)
start=time.monotonic()
if len(args)>2:
    previous=Path(args[2])
    for file in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copy2(previous/file,folder/file)
    motion_jobs.finish(folder);skinning._state(folder,'complete')
else:
    motion_jobs.start(folder)
    while skinning.poll(folder)['status']=='running':time.sleep(.2)
assert skinning.poll(folder)['status']=='complete',(folder/'worker.log').read_text(errors='replace')[-1000:]
collection,copy,copies,action,report=motion_apply.apply(bpy.context,folder,contacts=True,heading=True)
assert before==skinning._digest(rig,meshes) and source_action is rig.animation_data.action and action_hash(source_action)==source_hash
maximum=0.
for frame,expected in zip((1,37,72),snapshots):
    bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
    for p in copy.pose.bones:maximum=max(maximum,float(np.max(np.abs(np.array(p.matrix)-expected[p.name]))))
assert maximum<1e-5,maximum
workflow.select(bpy.context,copy,copies)
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
for profile in ('HUMANOID','GENERIC'):
    bundle=exporter.export_bundle(bpy.context,copy,copies,str(output),'AvatarKeyPoses'+profile,profile,include_action=True)
    for mesh in copies:exporter._prune(mesh,copy)
    motion_reference.write(copy,copies,bundle)
result=dict(passed=True,actual_conditioned_inference=len(args)==2,cached_actual_conditioned_output=len(args)>2,pose_editor_restores_mesh_scope=True,elapsed_seconds=time.monotonic()-start,max_anchor_matrix_error=maximum,
    vertices=sum(len(o.data.vertices) for o in meshes),source_action_preserved=True,source_rest_and_weights_preserved=True,
    pose_mode_capture_and_recall=True,clean_ui_draw=True,diagnostics=report,job=str(folder))
(output/'results.json').write_text(json.dumps(result,indent=2));bpy.ops.wm.save_as_mainfile(filepath=str(output/'avatar-keyframe-review.blend'))
print('AVATAR_KEYFRAME_ACCEPTANCE_PASSED',json.dumps(result),flush=True)
