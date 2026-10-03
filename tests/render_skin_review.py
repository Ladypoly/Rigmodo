"""Render a private fixed-rig comparison; do not modify the live Blender scene."""
import json
import importlib.util
import math
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

output = Path(sys.argv[sys.argv.index('--') + 1]).resolve()
bpy.ops.wm.open_mainfile(filepath=str(output / 'ai-skin-review.blend'), load_ui=False)
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and not o.get('lc_skin_job'))
proposal = next(o for o in bpy.data.objects if o.type == 'ARMATURE' and o.get('lc_skin_job'))
source_meshes = [o for o in bpy.data.objects if o.type == 'MESH' and not o.get('lc_skin_job')]
ai_meshes = [o for o in bpy.data.objects if o.type == 'MESH' and o.get('lc_skin_job')]
# Evaluate the exact exported policy on private temporary object/data copies.
# Full neural weights remain available on the review scene's original proposal.
extension = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('local_character', extension / '__init__.py', submodule_search_locations=[str(extension)])
addon = importlib.util.module_from_spec(spec); sys.modules[spec.name] = addon; spec.loader.exec_module(addon)
export_meshes=[]
for mesh in ai_meshes:
    copy=mesh.copy(); copy.data=mesh.data.copy(); bpy.context.scene.collection.objects.link(copy)
    addon.exporter._prune(copy, proposal); export_meshes.append(copy)
for bone in proposal.pose.bones: bone.matrix_basis.identity()
bpy.context.view_layer.update()
hips = proposal.matrix_world @ proposal.pose.bones['Hips'].head
up = (proposal.matrix_world @ proposal.pose.bones['Head'].head - hips).normalized()
left = (proposal.matrix_world @ proposal.pose.bones['LeftArm'].head - proposal.matrix_world @ proposal.pose.bones['RightArm'].head).normalized()
forward = left.cross(up).normalized()
arm = proposal.pose.bones['LeftForeArm']; pivot = proposal.matrix_world @ arm.head
arm.matrix = proposal.matrix_world.inverted() @ Matrix.Translation(pivot) @ Matrix.Rotation(math.radians(50), 4, forward) @ Matrix.Translation(-pivot) @ proposal.matrix_world @ arm.bone.matrix_local
bpy.context.view_layer.update()
points = []
for mesh in export_meshes:
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    for vertex in evaluated.data.vertices:
        delta = evaluated.matrix_world @ vertex.co - hips
        points.append(dict(zip(('x', 'y', 'z'), (delta.dot(left), delta.dot(forward), delta.dot(up)))))
(output / 'ShaneAISkin/generic-lbs-reference-flat.json').write_text(json.dumps({'angle': 50, 'points': points}))
arm.matrix_basis.identity()
for mesh in export_meshes:
    data=mesh.data; bpy.data.objects.remove(mesh,do_unlink=True); bpy.data.meshes.remove(data)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.color_type = 'SINGLE'
scene.display.shading.single_color = (.65, .71, .78)
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.display.shading.background_type = 'WORLD'
if scene.world is None: scene.world = bpy.data.worlds.new('AI Review World')
scene.world.color = (.04, .04, .04)
scene.render.resolution_x = 1000; scene.render.resolution_y = 800
scene.render.resolution_percentage = 100
camera_data = bpy.data.cameras.new('AI Review Camera')
camera = bpy.data.objects.new('AI Review Camera', camera_data)
scene.collection.objects.link(camera); scene.camera = camera
camera_data.type = 'ORTHO'
def frame(center, scale):
    camera.location = Vector(center) + Vector((0, -4, .3))
    camera.rotation_euler = (Vector(center) - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera_data.ortho_scale = scale
def render(name):
    scene.render.filepath = str(output / (name + '.png'))
    bpy.ops.render.render(write_still=True)
# Avoid transform changes: render each reference/proposal with the same camera.
for name, bone, axis, angle in [('forearm', 'LeftForeArm', (0, 0, 1), 60),
                              ('index', 'LeftHandIndex1', (1, 0, 0), 55)]:
    for armature in (rig, proposal):
        armature.pose.bones[bone].rotation_mode = 'QUATERNION'
        armature.pose.bones[bone].rotation_quaternion = Quaternion(Vector(axis), math.radians(angle))
    bpy.context.view_layer.update()
    if name == 'index':
        point = rig.matrix_world @ rig.pose.bones['LeftHand'].head
        frame(point, .4)
    else: frame((0, 0, .9), 2.4)
    for label, visible in [('reference', source_meshes), ('neural', ai_meshes)]:
        for mesh in source_meshes + ai_meshes: mesh.hide_render = mesh not in visible
        render(name + '-' + label)
    for armature in (rig, proposal): armature.pose.bones[bone].matrix_basis.identity()
print('LOCAL_CHARACTER_SKIN_RENDERED', str(output))
