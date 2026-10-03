# SPDX-License-Identifier: GPL-3.0-or-later
"""Local Character: independent game-character workflow, foundation release."""
import json
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup
from mathutils import Vector
from . import skeleton, preflight, exporter, skinning, regions, regional_jobs

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
    refine_method: EnumProperty(name='Refinement', items=[('AUTO', 'Auto regions', 'Keep AI body weights; surface-refine digits and apply marked rigid regions'),
        ('SURFACE', 'Surface heat', 'Refine all selected scope on actual surface adjacency')], default='AUTO')
    refine_iterations: IntProperty(name='Heat steps', default=12, min=1, max=200)
    refine_strength: FloatProperty(name='Strength', default=.35, min=.01, max=1)
    refine_selected: BoolProperty(name='Selected vertices only', default=False)
    refine_seams: BoolProperty(name='Link verified seam edges', default=True)
    region_kind: EnumProperty(name='Region policy', items=[('SURFACE', 'Surface', 'Surface refinement'),
        ('RIGID', 'Rigid attachment', 'Exact single-bone binding'), ('AUTO', 'Auto', 'Regional refinement')])
    region_bone: StringProperty(name='Attachment bone')
    region_digit: EnumProperty(name='Digit mask', items=[('NONE', 'Automatic', 'Use confident existing digit weights')] +
        [(side + 'Hand' + finger, side + ' ' + finger, 'Exclude neighboring digits')
         for side in ('Left', 'Right') for finger in skeleton.FINGERS])
    region_report: StringProperty(default='')
    region_job: StringProperty(default='')
    region_status: StringProperty(default='')

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

class WorkerModal:
    _timer = None
    _folder = None
    _scene = None
    status_property = 'skin_status'
    job_property = 'skin_job'
    apply_operator = 'apply_skin_job'
    def begin(self, context):
        self._scene = context.scene
        settings = self._scene.lc_settings
        setattr(settings, self.job_property, str(self._folder))
        setattr(settings, self.status_property, 'Running locally; Escape cancels')
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
            skinning.cancel(self._folder); setattr(settings, self.status_property, 'Cancelled; source character preserved')
            self._finish(context); return {'CANCELLED'}
        if event.type != 'TIMER': return {'PASS_THROUGH'}
        state = skinning.poll(self._folder)
        if state['status'] == 'running':
            setattr(settings, self.status_property, f"Running locally: {int(state['elapsed_seconds'])} s; Escape cancels")
            if context.screen:
                for area in context.screen.areas: area.tag_redraw()
            return {'PASS_THROUGH'}
        try:
            if state['status'] != 'complete': raise ValueError('Worker failed; inspect worker.log in the last job folder')
            if context.scene != self._scene: raise ValueError('Return to the source scene and create the weighted copy from the finished job')
            result = getattr(bpy.ops.local_character, self.apply_operator)('EXEC_DEFAULT')
            if result != {'FINISHED'}: raise ValueError(getattr(settings, self.status_property))
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            setattr(settings, self.status_property, str(exc)); self.report({'ERROR'}, str(exc))
            self._finish(context); return {'CANCELLED'}
        self._finish(context); return {'FINISHED'}
    def cancel(self, context):
        if self._folder: skinning.cancel(self._folder)
        self._finish(context)


class LC_OT_skin(WorkerModal, Operator):
    bl_idname = 'local_character.ai_skin'
    bl_label = 'AI Skin to New Copy'
    bl_description = 'Run local SkinTokens on accepted joints and create weighted copies'
    # Separate apply owns undo; intervening user edits never join the job's undo.
    bl_options = {'REGISTER'}
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
        return self.begin(context)

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

class LC_OT_protect(Operator):
    bl_idname = 'local_character.protect_region'
    bl_label = 'Protect Selected Weights'
    bl_options = {'REGISTER', 'UNDO'}
    enabled: BoolProperty(default=True)
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and context.active_object and context.active_object.type == 'MESH'
    def execute(self, context):
        mesh = context.active_object
        try:
            if mesh.data.users > 1: raise ValueError('Make the mesh data single-user before annotating a region')
            regions.protect(mesh, regions.selected_vertices(mesh), self.enabled)
        except (ValueError, RuntimeError) as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        self.report({'INFO'}, 'Protection updated; deform weights unchanged')
        return {'FINISHED'}

class LC_OT_mark_region(Operator):
    bl_idname = 'local_character.mark_region'
    bl_label = 'Mark Selected Region'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and context.active_object and context.active_object.type == 'MESH'
    def execute(self, context):
        settings = context.scene.lc_settings; mesh = context.active_object
        try:
            rig, _ = skinning.selection(context)
            if mesh.data.users > 1: raise ValueError('Make the mesh data single-user before annotating a region')
            if settings.region_kind == 'RIGID' and (settings.region_bone not in rig.data.bones or not rig.data.bones[settings.region_bone].use_deform):
                raise ValueError('Choose an accepted deform attachment bone')
            regions.mark(mesh, regions.selected_vertices(mesh), settings.region_kind, settings.region_bone,
                '' if settings.region_digit == 'NONE' else settings.region_digit)
        except (ValueError, RuntimeError) as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        self.report({'INFO'}, 'Region marked; next refinement applies it on copies')
        return {'FINISHED'}

class LC_OT_clear_region(Operator):
    bl_idname = 'local_character.clear_region'
    bl_label = 'Clear Selected Policies'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return LC_OT_mark_region.poll(context)
    def execute(self, context):
        try:
            mesh = context.active_object
            if mesh.data.users > 1: raise ValueError('Make mesh data single-user before changing policies')
            regions.clear(mesh, regions.selected_vertices(mesh))
        except (ValueError, RuntimeError) as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_refine(WorkerModal, Operator):
    bl_idname = 'local_character.refine_regions'
    bl_label = 'Refine to New Copy'
    bl_options = {'REGISTER'}
    status_property = 'region_status'
    job_property = 'region_job'
    apply_operator = 'apply_region_job'
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and not skinning._jobs
    def execute(self, context):
        settings = context.scene.lc_settings
        try:
            rig, meshes = skinning.selection(context)
            self._folder = regional_jobs.prepare(context, rig, meshes, method=settings.refine_method,
                iterations=settings.refine_iterations, strength=settings.refine_strength,
                selected_only=settings.refine_selected, join_seams=settings.refine_seams)
            regional_jobs.start(self._folder)
        except (ValueError, OSError, RuntimeError) as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return self.begin(context)


class LC_OT_apply_region(Operator):
    bl_idname = 'local_character.apply_region_job'
    bl_label = 'Create Copy from Finished Refinement'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and not skinning._jobs and bool(context.scene.lc_settings.region_job)
    def execute(self, context):
        settings = context.scene.lc_settings
        try:
            (collection, rig, meshes), report = regional_jobs.apply(context, settings.region_job)
            for obj in context.selected_objects: obj.select_set(False)
            for obj in [rig, *meshes]: obj.select_set(True)
            context.view_layer.objects.active = rig
            settings.region_report = json.dumps(report)
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            settings.region_status = str(exc); self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        settings.region_status = 'Review copies created; original weights preserved'
        self.report({'INFO'}, f'Created {collection.name}; protected weights preserved')
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
        box = layout.box(); box.label(text='Regional correction', icon='GROUP_VERTEX')
        box.label(text='Select vertices in Edit Mode; return to Object Mode')
        row = box.row(align=True)
        row.operator('local_character.protect_region', text='Protect').enabled = True
        row.operator('local_character.protect_region', text='Unprotect').enabled = False
        box.prop(settings, 'region_kind')
        if settings.region_kind == 'RIGID':
            try:
                rig, _ = skinning.selection(context)
                box.prop_search(settings, 'region_bone', rig.data, 'bones')
            except ValueError: box.prop(settings, 'region_bone')
        else: box.prop(settings, 'region_digit')
        box.operator('local_character.mark_region')
        box.operator('local_character.clear_region')
        box.prop(settings, 'refine_method'); box.prop(settings, 'refine_selected')
        box.prop(settings, 'refine_seams'); box.prop(settings, 'refine_iterations'); box.prop(settings, 'refine_strength')
        box.operator('local_character.refine_regions')
        if settings.region_status:
            import textwrap
            for line in textwrap.wrap(settings.region_status, width=42): box.label(text=line)
        if settings.region_job: box.operator('local_character.apply_region_job')
        if settings.region_report:
            try:
                for report in json.loads(settings.region_report):
                    box.label(text=f"{report['mesh']}: {report['rigid_vertices']} rigid, {report['protected_vertices']} protected")
                    if report['seam_constraint_conflicts']: box.label(text='Conflicting seam constraints need review', icon='ERROR')
            except (ValueError, KeyError): pass

CLASSES = (LC_Settings, LC_OT_create_template, LC_OT_preflight, LC_OT_export, LC_OT_skin, LC_OT_apply_skin,
           LC_OT_protect, LC_OT_mark_region, LC_OT_clear_region, LC_OT_refine, LC_OT_apply_region, LC_PT_main)
def register():
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Scene.lc_settings = PointerProperty(type=LC_Settings)

def unregister():
    skinning.cancel_all()
    del bpy.types.Scene.lc_settings
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
