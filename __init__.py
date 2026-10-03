# SPDX-License-Identifier: GPL-3.0-or-later
"""Local Character: independent game-character workflow, foundation release."""
import json
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector
from . import skeleton, preflight, exporter, skinning

class LC_Settings(PropertyGroup):
    height: FloatProperty(name="Height (m)", default=1.75, min=.1, max=10)
    arm_angle: FloatProperty(name="Arm drop (degrees)", default=0, min=0, max=70)
    eyes: BoolProperty(name="Eye bones", default=False)
    fit_bounds: BoolProperty(name="Use selected mesh bounds", default=True,
        description="Rough template fit for upright Z-up geometry; joint placement still needs review")
    character_name: StringProperty(name="Character", default="Character")
    export_directory: StringProperty(name="Export folder", subtype="DIR_PATH", default="//LocalCharacterExports/")
    include_action: BoolProperty(name="Include armature's selected Action", default=False,
        description="Export one direct bone Action as a separate animation FBX; ignore other Actions and NLA")
    loop_action: BoolProperty(name="Loop clip in Unity", default=False,
        description="Mark the selected clip as looping; does not repair its start/end pose")
    profile: EnumProperty(name="Unity rig", items=[("HUMANOID", "Humanoid", "Mixamo-style human mapping"),
        ("GENERIC", "Generic", "Preserve mechanical or custom hierarchy")])
    last_report: StringProperty(default="")
    last_export: StringProperty(default="")
    skin_executable: StringProperty(name="SkinTokens worker", subtype="FILE_PATH",
        default=str(skinning.provider_cache() / 'bin/skintokens-cli.exe'))
    skin_models: StringProperty(name="F16 model folder", subtype="DIR_PATH",
        default=str(skinning.provider_cache() / 'models/F16'))
    skin_device: EnumProperty(name="Compute", items=[('vulkan', 'Vulkan GPU', 'Run locally on the GPU'),
        ('cpu', 'CPU', 'CPU inference can be slow')], default='vulkan')
    skin_beams: IntProperty(name="Search beams", default=10, min=1, max=10,
        description="Ten is the upstream default; fewer beams trade search quality for speed and memory")
    skin_job: StringProperty(default="")
    skin_status: StringProperty(default="")

class LC_OT_create_template(Operator):
    bl_idname = "local_character.create_template"
    bl_label = "Create Editable Humanoid"
    bl_description = "Create a separate 53-bone template; does not bind meshes or run AI"
    bl_options = {"REGISTER", "UNDO"}
    @classmethod
    def poll(cls, context): return context.mode == "OBJECT"
    def execute(self, context):
        settings = context.scene.lc_settings
        height = settings.height / context.scene.unit_settings.scale_length
        origin = tuple(context.scene.cursor.location)
        meshes = [o for o in context.selected_objects if o.type == "MESH"]
        if settings.fit_bounds and meshes:
            points = [o.matrix_world @ Vector(corner) for o in meshes for corner in o.bound_box]
            lo = Vector(tuple(min(p[i] for p in points) for i in range(3)))
            hi = Vector(tuple(max(p[i] for p in points) for i in range(3)))
            height = hi.z - lo.z; origin = ((lo.x+hi.x)/2, (lo.y+hi.y)/2, lo.z)
        try:
            skeleton.create_armature(context, height, settings.arm_angle, settings.eyes, origin)
        except ValueError as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        self.report({"INFO"}, "Editable template created. Review joint placement before binding")
        return {"FINISHED"}

class LC_OT_preflight(Operator):
    bl_idname = "local_character.preflight"
    bl_label = "Check Selected Character"
    @classmethod
    def poll(cls, context): return context.mode == "OBJECT"
    def execute(self, context):
        try:
            rig, meshes = preflight.selection(context)
            report = preflight.inspect(rig, meshes, context.scene.lc_settings.profile)
            context.scene.lc_settings.last_report = json.dumps(report)
            self.report({"INFO"} if report["ready"] else {"WARNING"},
                        f"{len(report['errors'])} errors, {len(report['warnings'])} warnings")
        except ValueError as exc:
            context.scene.lc_settings.last_report = json.dumps({"errors": [str(exc)], "warnings": [], "ready": False})
            self.report({"WARNING"}, str(exc))
        return {"FINISHED"}

class LC_OT_export(Operator):
    bl_idname = "local_character.export_unity"
    bl_label = "Export Character to Unity"
    bl_description = "Export selected bound meshes and their rig without editing originals"
    @classmethod
    def poll(cls, context): return context.mode == "OBJECT"
    def execute(self, context):
        settings = context.scene.lc_settings
        try:
            if settings.export_directory.startswith("//") and not bpy.data.filepath:
                raise ValueError("Save the blend file or choose an absolute export folder")
            rig, meshes = preflight.selection(context)
            destination = exporter.export_bundle(context, rig, meshes, settings.export_directory, settings.character_name,
                settings.profile, settings.include_action, settings.loop_action)
        except (ValueError, OSError, RuntimeError) as exc:
            self.report({"ERROR"}, str(exc)); return {"CANCELLED"}
        settings.last_export = str(destination)
        self.report({"INFO"}, f"Exported {destination}")
        return {"FINISHED"}

class LC_OT_skin(Operator):
    bl_idname = "local_character.ai_skin"
    bl_label = "AI Skin to New Copy"
    bl_description = "Run experimental local SkinTokens on accepted joints and create weighted copies"
    # A long-running job must not group the user's intervening edits into its undo.
    # The separate apply operator owns the short copy-creation undo boundary.
    bl_options = {"REGISTER"}
    _timer = None
    _folder = None
    _scene = None
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and not skinning._jobs
    def execute(self, context):
        settings = context.scene.lc_settings
        try:
            rig, meshes = skinning.selection(context)
            self._folder = skinning.prepare(context, rig, meshes, device=settings.skin_device, beams=settings.skin_beams)
            skinning.start(self._folder, bpy.path.abspath(settings.skin_executable), bpy.path.abspath(settings.skin_models))
        except (ValueError, OSError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        self._scene = context.scene
        settings.skin_job = str(self._folder); settings.skin_status = 'Running locally; Escape cancels'
        self._timer = context.window_manager.event_timer_add(.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def _finish(self, context):
        if self._timer: context.window_manager.event_timer_remove(self._timer)
        self._timer = None
        if context.screen:
            for area in context.screen.areas: area.tag_redraw()
    def modal(self, context, event):
        try: settings = self._scene.lc_settings
        except (ReferenceError, AttributeError):
            skinning.cancel(self._folder); self._finish(context); return {'CANCELLED'}
        if event.type == 'ESC':
            skinning.cancel(self._folder); settings.skin_status = 'Cancelled; source character preserved'
            self._finish(context); return {'CANCELLED'}
        if event.type != 'TIMER': return {'PASS_THROUGH'}
        state = skinning.poll(self._folder)
        if state['status'] == 'running':
            settings.skin_status = f"Running locally: {int(state['elapsed_seconds'])} s; Escape cancels"
            for area in context.screen.areas: area.tag_redraw()
            return {'PASS_THROUGH'}
        try:
            if state['status'] != 'complete': raise ValueError('Worker failed; inspect worker.log in the last job folder')
            if context.scene != self._scene: raise ValueError('Return to the source scene and create the weighted copy from the finished job')
            result = bpy.ops.local_character.apply_skin_job('EXEC_DEFAULT')
            if result != {'FINISHED'}: raise ValueError(settings.skin_status)
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            settings.skin_status = str(exc); self.report({'ERROR'}, str(exc))
            self._finish(context); return {'CANCELLED'}
        self._finish(context); return {'FINISHED'}
    def cancel(self, context):
        if self._folder: skinning.cancel(self._folder)
        self._finish(context)

class LC_OT_apply_skin(Operator):
    bl_idname = 'local_character.apply_skin_job'
    bl_label = 'Create Copy from Finished Job'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and bool(context.scene.lc_settings.skin_job) and not skinning._jobs
    def execute(self, context):
        settings = context.scene.lc_settings
        try:
            collection, rig, meshes = skinning.apply(context, settings.skin_job)
            for obj in context.selected_objects: obj.select_set(False)
            for obj in [rig, *meshes]: obj.select_set(True)
            context.view_layer.objects.active = rig
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            settings.skin_status = str(exc)
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        settings.skin_status = 'Weighted copies created; review deformation. Originals remain in place'
        self.report({'INFO'}, f'Created {collection.name}; accepted joints preserved')
        return {'FINISHED'}

class LC_PT_main(Panel):
    bl_label = "Local Character"
    bl_idname = "LC_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Local Character"
    def draw(self, context):
        layout = self.layout; settings = context.scene.lc_settings
        box = layout.box(); box.label(text="Editable humanoid", icon="ARMATURE_DATA")
        box.prop(settings, "fit_bounds")
        if not settings.fit_bounds: box.prop(settings, "height")
        box.prop(settings, "arm_angle"); box.prop(settings, "eyes")
        box.operator("local_character.create_template")
        box.label(text="Review joints before AI skinning", icon="INFO")
        box = layout.box(); box.label(text="Existing bound character", icon="MESH_DATA")
        box.label(text="Select only the meshes to export")
        box.prop(settings, "profile"); box.operator("local_character.preflight")
        if settings.last_report:
            try:
                report = json.loads(settings.last_report)
                for message in report.get("errors", []) + report.get("warnings", []):
                    column = box.column(align=True)
                    import textwrap
                    for line in textwrap.wrap(message, width=42): column.label(text=line)
                if report.get("ready"): box.label(text="Weight and hierarchy checks passed", icon="CHECKMARK")
            except (ValueError, TypeError): pass
        box.prop(settings, "character_name"); box.prop(settings, "export_directory")
        box.prop(settings, "include_action")
        if settings.include_action: box.prop(settings, "loop_action")
        box.operator("local_character.export_unity", icon="EXPORT")
        if settings.last_export: box.label(text="Last export: " + settings.last_export)
        box = layout.box(); box.label(text="Local AI providers", icon="INFO")
        box.label(text="SkinTokens: experimental weight proposal")
        box.label(text="Select accepted rig and character meshes")
        box.prop(settings, 'skin_executable'); box.prop(settings, 'skin_models')
        box.prop(settings, 'skin_device'); box.prop(settings, 'skin_beams')
        box.operator('local_character.ai_skin', icon='MOD_ARMATURE')
        if settings.skin_status:
            import textwrap
            for line in textwrap.wrap(settings.skin_status, width=42): box.label(text=line)
        if settings.skin_job: box.operator('local_character.apply_skin_job')
        box.label(text="Joint placement and generated motion: next phase")

CLASSES = (LC_Settings, LC_OT_create_template, LC_OT_preflight, LC_OT_export, LC_OT_skin, LC_OT_apply_skin, LC_PT_main)
def register():
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Scene.lc_settings = PointerProperty(type=LC_Settings)

def unregister():
    skinning.cancel_all()
    del bpy.types.Scene.lc_settings
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
