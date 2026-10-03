"""Render actual mesh-only rig/skin output with a held-out native walk fixture."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import bpy
from mathutils import Vector

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
from local_character import motion_jobs,motion_apply,skinning,exporter
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source/'blind-character-review.blend'),load_ui=False)
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
assert rig.type=='ARMATURE' and len(rig.data.bones)==53
before=skinning._digest(rig,meshes)
folder=motion_jobs.prepare(bpy.context,rig,'A person walks forward naturally at a steady pace.',parent=output)
for name in ('root_positions.f32','local_rotations_xyzw.f32'):shutil.copyfile(motion_jobs.cache()/'evaluation/walk'/name,folder/name)
motion_jobs.finish(folder);skinning._state(folder,'complete',reused_native_fixture=True)
collection,animated,copies,action,report=motion_apply.apply(bpy.context,folder,contacts=True)
assert before==skinning._digest(rig,meshes)
for obj in bpy.context.scene.objects:obj.hide_render=obj not in copies
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.color_type='SINGLE'
scene.display.shading.single_color=(.65,.71,.78);scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
scene.render.resolution_x=900;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
camera_data=bpy.data.cameras.new('Motion Review Camera');camera=bpy.data.objects.new('Motion Review Camera',camera_data)
scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO';camera_data.ortho_scale=2.1
for frame in (1,25,49,72):
    scene.frame_set(frame);bpy.context.view_layer.update()
    center=animated.matrix_world@animated.pose.bones['Root'].head+Vector((0,0,.87))
    camera.location=center+Vector((2,-4,.8));camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(output/f'walk-{frame}.png');bpy.ops.render.render(write_still=True)
for obj in bpy.context.selected_objects:obj.select_set(False)
for obj in [animated,*copies]:obj.select_set(True)
bpy.context.view_layer.objects.active=animated
bundle=exporter.export_bundle(bpy.context,animated,copies,str(output),'BlindMotion',include_action=True)
bpy.ops.wm.save_as_mainfile(filepath=str(output/'blind-motion-review.blend'))
(output/'results.json').write_text(json.dumps(dict(passed=True,source_preserved=True,core_bones=53,native_motion_fixture_reused=True,
    contacts=json.loads(action['lc_contact_correction']),bundle=str(bundle)),indent=2))
print('BLIND_MOTION_REVIEW',bundle)
