"""Render selected character copies in a private background scene, never save."""
from pathlib import Path
import sys
import bpy
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(source),load_ui=False)
meshes=[o for o in bpy.context.selected_objects if o.type=='MESH'];assert meshes
for obj in bpy.context.scene.objects:
    if obj.type=='MESH':obj.hide_render=obj not in meshes
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.color_type='SINGLE';scene.display.shading.show_cavity=True
scene.render.resolution_x=700;scene.render.resolution_y=900;scene.render.resolution_percentage=100
data=bpy.data.cameras.new('Review');camera=bpy.data.objects.new('Review',data);scene.collection.objects.link(camera);scene.camera=camera;data.type='ORTHO'
points=[m.matrix_world@Vector(v) for m in meshes for v in m.bound_box]
lo=Vector([min(p[i] for p in points) for i in range(3)]);hi=Vector([max(p[i] for p in points) for i in range(3)]);center=(lo+hi)/2
camera.location=center+Vector((0,-4,0));camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();data.ortho_scale=max((hi-lo).z,(hi-lo).x*900/700)*1.2
for frame in (1,25,49):
    scene.frame_set(frame);scene.render.filepath=str(output/f'frame-{frame}.png');bpy.ops.render.render(write_still=True)
