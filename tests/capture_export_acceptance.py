import os
import bpy,addon_utils,importlib,json,sys,math
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
bpy.ops.import_scene.gltf(filepath=os.environ.get('RIGMODO_TEST_AVATAR','R:/BLENDER/BANTER_Avatars/Shane.glb'));rig=next(o for o in ctx.scene.objects if o.type=='ARMATURE');meshes=[o for o in ctx.scene.objects if o.type=='MESH' and o.find_armature()==rig]
a.character_context.pin(ctx,rig,meshes);signature=a.skinning._digest(rig,meshes)
data=a.motion_store.read_file(Path(os.environ.get('RIGMODO_TEST_CAPTURE','R:/AI/Rigmodo/Jobs/Acceptance/gemx-avatar/output.npz')));s=ctx.scene.lc_settings;s.motion_in_place=True;s.create_loop=True;s.motion_contacts=True
action=a.animation_transfer.finish(ctx,rig,data,'RigmodoCaptureWalk');scene=ctx.scene;scene.frame_start=1;scene.frame_end=round(action.frame_end)
samples={}
for frame in (1,12,24,scene.frame_end):
    scene.frame_set(frame);ctx.view_layer.update();samples[frame]={p.name:rig.matrix_world@p.head for p in rig.pose.bones}
for obj in ctx.selected_objects:obj.select_set(False)
for obj in [rig,*meshes]:obj.select_set(True)
ctx.view_layer.objects.active=rig
path=out/'RigmodoCaptureWalk.fbx'
bpy.ops.export_scene.fbx(filepath=str(path),use_selection=True,object_types={'ARMATURE','MESH'},add_leaf_bones=False,bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0.,axis_forward='-Z',axis_up='Y',mesh_smooth_type='FACE')
assert a.skinning._digest(rig,meshes)==signature
before=set(bpy.data.objects);bpy.ops.import_scene.fbx(filepath=str(path),use_anim=True,anim_offset=0.);imported=next(o for o in set(bpy.data.objects)-before if o.type=='ARMATURE');maximum=0.
for frame,points in samples.items():
    scene.frame_set(frame);ctx.view_layer.update()
    for name,point in points.items():maximum=max(maximum,(imported.matrix_world@imported.pose.bones[name].head-point).length)
assert maximum<.001,maximum
report=dict(passed=True,fbx=str(path),actual_capture=True,fbx_roundtrip_max_joint_error_m=maximum,source_rig_skin_preserved=True,frames=scene.frame_end,period=action.get('lc_loop_period_frames'),bones=len(rig.data.bones))
(out/'results.json').write_text(json.dumps(report,indent=2));print('CAPTURE_EXPORT_PASS',json.dumps(report))
