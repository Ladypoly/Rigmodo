# SPDX-License-Identifier: GPL-3.0-or-later
"""Render a character reference in a disposable scene without changing the user scene."""
from pathlib import Path
import bpy
from bpy.types import Operator
from mathutils import Vector
from . import motion_jobs


def render(context,rig,path,width=416,height=736):
    meshes=motion_jobs.character_meshes(context,rig)
    if not meshes:raise ValueError('The character has no visible meshes to render')
    scene=bpy.data.scenes.new('Rigmodo Reference');objects=[];data=[];materials=[];world=None
    try:
        depsgraph=context.evaluated_depsgraph_get();points=[]
        for original in meshes:
            evaluated=original.evaluated_get(depsgraph);mesh=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=depsgraph);data.append(mesh)
            obj=bpy.data.objects.new('Reference '+original.name,mesh);objects.append(obj);scene.collection.objects.link(obj);obj.matrix_world=evaluated.matrix_world.copy()
            points.extend(obj.matrix_world@Vector(p) for p in obj.bound_box)
        low=Vector(tuple(min(p[i] for p in points) for i in range(3)));high=Vector(tuple(max(p[i] for p in points) for i in range(3)));center=(low+high)/2;size=max((high-low).length,.1)
        camera=bpy.data.cameras.new('Reference camera');data.append(camera);obj=bpy.data.objects.new('Reference camera',camera);objects.append(obj);scene.collection.objects.link(obj)
        obj.location=center+Vector((.25,-1,.15)).normalized()*size*3;obj.rotation_euler=(center-obj.location).to_track_quat('-Z','Y').to_euler();camera.type='ORTHO'
        camera.ortho_scale=max(high.z-low.z,(high.x-low.x)/(width/height))*1.22;scene.camera=obj
        world=bpy.data.worlds.new('Reference world');world.use_nodes=True;world.node_tree.nodes['Background'].inputs['Color'].default_value=(.35,.35,.35,1);world.node_tree.nodes['Background'].inputs['Strength'].default_value=.65;scene.world=world
        for offset,power in [(Vector((-1,-2,3)),600),(Vector((2,1,2)),400)]:
            light=bpy.data.lights.new('Reference softbox','AREA');data.append(light);light.energy=power;light.shape='DISK';light.size=size*2
            obj=bpy.data.objects.new('Reference softbox',light);objects.append(obj);scene.collection.objects.link(obj);obj.location=center+offset*size;obj.rotation_euler=(center-obj.location).to_track_quat('-Z','Y').to_euler()
        floor=bpy.data.meshes.new('Reference floor');data.append(floor);radius=size*5;z=low.z-.002
        floor.from_pydata([(center.x+x,center.y+y,z) for x,y in [(-radius,-radius),(radius,-radius),(radius,radius),(-radius,radius)]],[],[(0,1,2,3)])
        obj=bpy.data.objects.new('Reference floor',floor);objects.append(obj);scene.collection.objects.link(obj)
        material=bpy.data.materials.new('Reference floor');materials.append(material);material.diffuse_color=(.32,.32,.32,1);floor.materials.append(material)
        scene.render.engine='BLENDER_EEVEE';scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.resolution_percentage=100
        scene.render.image_settings.file_format='PNG';path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);scene.render.filepath=str(path)
        scene.render.film_transparent=False
        bpy.ops.render.render(write_still=True,scene=scene.name)
        return path
    finally:
        bpy.data.scenes.remove(scene)
        for obj in objects:
            if obj.name in bpy.data.objects:bpy.data.objects.remove(obj,do_unlink=True)
        for item in data:
            if item.users==0:
                collection=bpy.data.meshes if isinstance(item,bpy.types.Mesh) else bpy.data.cameras if isinstance(item,bpy.types.Camera) else bpy.data.lights
                collection.remove(item)
        for material in materials:
            if material.users==0:bpy.data.materials.remove(material)
        if world and world.users==0:bpy.data.worlds.remove(world)


class LC_OT_character_reference(Operator):
    bl_idname='local_character.render_character_reference';bl_label='Use Character Image'
    def execute(self,context):
        try:
            from . import configuration
            import uuid
            from . import skinning
            if skinning._jobs:raise ValueError('Wait for the current task to finish')
            rig=motion_jobs.selected_rig(context);folder=Path(bpy.path.abspath(configuration.settings(context).video_jobs))/'References'
            path=render(context,rig,folder/(uuid.uuid4().hex+'.png'));context.scene.lc_settings.video_reference=str(path)
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


CLASSES=(LC_OT_character_reference,)
