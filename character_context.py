# SPDX-License-Identifier: GPL-3.0-or-later
"""An explicit character scope, independent of viewport selection."""
import bpy
from bpy.types import Operator,PropertyGroup
from bpy.props import PointerProperty


class LC_CharacterMesh(PropertyGroup):
    object:PointerProperty(type=bpy.types.Object)


def bound_meshes(context,rig):
    helpers={p.custom_shape for p in rig.pose.bones if p.custom_shape}
    return [o for o in context.view_layer.objects if o.type=='MESH' and o.visible_get() and o not in helpers and
            any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]


def from_selection(context):
    meshes=[o for o in context.selected_objects if o.type=='MESH']
    rigs={o for o in context.selected_objects if o.type=='ARMATURE'}
    rigs.update(m.object for o in meshes for m in o.modifiers if m.type=='ARMATURE' and m.object)
    if len(rigs)>1:raise ValueError('Select one character, then use Use Selection')
    rig=next(iter(rigs),None)
    if rig:
        helpers={p.custom_shape for p in rig.pose.bones if p.custom_shape};meshes=[o for o in meshes if o not in helpers]
        if not meshes:meshes=[o for o in bound_meshes(context,rig) if o.visible_get()]
    if not rig and not meshes:raise ValueError('Select a character armature or its meshes')
    return rig,meshes


def pin(context,rig,meshes):
    s=context.scene.lc_settings;s.character=rig or next(iter(meshes),None);s.character_meshes.clear()
    for obj in meshes:
        item=s.character_meshes.add();item.object=obj
    s.character_pinned=True


def resolve(context):
    s=context.scene.lc_settings
    if not s.character_pinned:return None
    obj=s.character
    if not obj or obj.name not in context.scene.objects:raise ValueError('Character was removed; use Use Selection to choose another')
    if obj.name not in context.view_layer.objects:raise ValueError('Character is excluded from this view layer')
    rig=obj if obj.type=='ARMATURE' else obj.find_armature() if obj.type=='MESH' else None
    meshes=[item.object for item in s.character_meshes if item.object and item.object.name in context.scene.objects]
    if not meshes:
        meshes=bound_meshes(context,rig) if rig else [obj] if obj.type=='MESH' else []
    return rig,meshes


def changed(self,context):
    if context and self.character:
        obj=self.character;rig=obj if obj.type=='ARMATURE' else obj.find_armature()
        meshes=bound_meshes(context,rig) if rig else [obj]
        self.character_meshes.clear()
        for mesh in meshes:item=self.character_meshes.add();item.object=mesh
        self.character_pinned=True


class LC_OT_use_character(Operator):
    bl_idname='local_character.use_character_selection';bl_label='Use Selection';bl_options={'UNDO'}
    bl_description='Keep this character selected in Rigmodo while editing other objects'
    def execute(self,context):
        from . import skinning
        if skinning._jobs:self.report({'ERROR'},'Finish the current task before changing character');return {'CANCELLED'}
        try:rig,meshes=from_selection(context);pin(context,rig,meshes)
        except ValueError as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_release_character(Operator):
    bl_idname='local_character.release_character';bl_label='Follow Viewport Selection'
    def execute(self,context):
        from . import skinning
        if skinning._jobs:return {'CANCELLED'}
        context.scene.lc_settings.character_pinned=False;context.scene.lc_settings.character=None
        context.scene.lc_settings.character_meshes.clear();return {'FINISHED'}


CLASSES=(LC_CharacterMesh,LC_OT_use_character,LC_OT_release_character)
