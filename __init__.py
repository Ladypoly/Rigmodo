# SPDX-License-Identifier: GPL-3.0-or-later
"""Rigmodo: independent local humanoid workflow."""
import json
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup, AddonPreferences
from mathutils import Vector
from . import skeleton, preflight, exporter, skinning, regions, regional_jobs, motion_jobs, motion_apply, placement, motion_finish, workflow,twists,install_jobs,rig_modules,hand_pose,deformation_qa,configuration,landmarks,hands,ui,motion_keyframes,character_result,auto_pose,image_pose

class LC_Settings(PropertyGroup):
    image_pose_provider: StringProperty(name='SAM 3D Body runtime',subtype='DIR_PATH',default=str(image_pose.cache()))
    image_pose_models: StringProperty(name='Approved SAM checkpoints',subtype='DIR_PATH',default=str(image_pose.cache()/'models'))
    image_pose_hands: BoolProperty(name='Infer hand pose',default=True,description='Use the separate hand decoder; disabling preserves authored finger channels')
    image_pose_job: StringProperty(default='',options={'HIDDEN'})
    image_pose_status: StringProperty(default='')
    height: FloatProperty(name="Height (m)", default=1.75, min=.1, max=10)
    arm_angle: FloatProperty(name="Arm drop (degrees)", default=0, min=0, max=70)
    eyes: BoolProperty(name="Eye bones", default=False)
    fit_bounds: BoolProperty(name="Use selected mesh bounds", default=True,
        description="Rough template fit for upright Z-up geometry; joint placement still needs review")
    character_name: StringProperty(name="Character", default="Character")
    export_directory: StringProperty(name="Export folder", subtype="DIR_PATH", default="//LocalCharacterExports/",options={'PATH_SUPPORTS_BLEND_RELATIVE'})
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
        ('SURFACE', 'Surface heat', 'Refine all selected scope on actual surface adjacency'),
        ('RIGID_PARTS','Rigid mesh parts','Declare selected meshes rigid: confident connected parts bind to one AI-suggested bone; ambiguous parts retain their weights'),
        ('GEODESIC','Surface distance binding','Bind or refine along actual surface edges without crossing disconnected geometry'),
        ('VOXEL','Volume heat with surface details','Closed-volume diffusion; digits use surface distance; unsuitable geometry falls back with a report')], default='AUTO')
    voxel_resolution: IntProperty(name='Volume resolution',default=48,min=24,max=64)
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
    motion_provider: StringProperty(name='Kimodo runtime folder', subtype='DIR_PATH', default=str(motion_jobs.cache()))
    motion_prompt: StringProperty(name='Motion', default='A person walks forward naturally at a steady pace.')
    motion_frames: IntProperty(name='Frames at 30 fps', default=90, min=15, max=900)
    motion_steps: IntProperty(name='Sampling steps', default=100, min=10, max=200)
    motion_seed: IntProperty(name='Seed', default=101, min=0, max=2147483647)
    motion_in_place: BoolProperty(name='In place', default=False, description='Remove ground travel while preserving hip sway and jump height')
    motion_use_keyframes: BoolProperty(name='Use Key Poses',default=False,description='Use pose keyframes from this armature’s active Action within the generated clip, starting at the Timeline Start frame')
    motion_start_frame: IntProperty(name='Start frame',default=1,min=-100000,max=100000,description='First timeline frame of the generated clip; length is sampled at 30 fps')
    motion_contacts: BoolProperty(name='Correct foot contacts',default=True,description='Bake local leg IK for detected contacts; review ground height and reachable foot positions')
    motion_heading: BoolProperty(name='Extract turning to Root',default=True,description='Move the source hip’s changing ground heading into Root while preserving the body’s world pose')
    motion_loop_blend: IntProperty(name='Loop blend frames',default=8,min=2,max=120)
    motion_hand_curl: FloatProperty(name='Hand curl', default=0., min=0, max=1, description='Editable finger pose; SOMA motion has no animated finger joints')
    hand_controls: BoolProperty(name='Individual hand controls',default=False,description='Override the shared curl with per-hand, per-finger settings')
    hand_side: EnumProperty(name='Hand',items=[('Left','Left',''),('Right','Right','')])
    hand_preset: EnumProperty(name='Pose',items=[(p,p.title(),'Editable finger preset') for p in hand_pose.PRESETS])
    optional_kind: EnumProperty(name='Optional bone',items=[('LEFT_EYE','Left eye','Cursor at the eye centre'),('RIGHT_EYE','Right eye','Cursor at the eye centre'),('JAW','Jaw','Cursor at jaw hinge'),('SOCKET','Attachment socket','Unweighted attachment bone')])
    optional_parent: StringProperty(name='Socket parent',default='RightHand')
    optional_name: StringProperty(name='Socket name',default='WeaponSocket')
    motion_job: StringProperty(default='')
    motion_status: StringProperty(default='')
    placement_python: StringProperty(name='MIA Python runtime',subtype='FILE_PATH',default=str(placement.cache()/'runtime/Scripts/python.exe'))
    placement_job: StringProperty(default='')
    placement_status: StringProperty(default='')
    workflow_reuse_joints: BoolProperty(name='Reuse accepted joints',default=True,description='Keep corrected humanoid joints when an accepted Root and core hierarchy already exist')
    workflow_rebind: BoolProperty(name='Rebuild AI weights',default=True,description='Protected paint and locked bone weights remain fixed')
    workflow_motion: BoolProperty(name='Generate motion',default=True)
    workflow_export: BoolProperty(name='Export when complete',default=False)
    workflow_loop: BoolProperty(name='Blend loop endpoint',default=False,description='Create an editable pose blend; inspect foot timing before using it as a loop')
    workflow_hide_sources: BoolProperty(name='Hide source and intermediate copies',default=True,description='Hide only after success; originals remain recoverable in the Outliner')
    keep_skin_copies: BoolProperty(name='Keep skinning review copies',default=False,description='Keep separate weighted results instead of updating the selected character after successful skinning')
    workflow_twists: BoolProperty(name='Optional forearm twists',default=False,description='Add two deform helpers after core AI binding; arbitrary Unity Humanoid clips use the companion twist component')
    workflow_rigid: BoolProperty(name='Treat meshes as rigid character parts',default=False,description='An explicit material decision for robots: clear connected parts use one AI-suggested joint; ambiguous parts stay editable')
    workflow_allow_strain: BoolProperty(name='Allow severe deformation findings',default=False,description='Expert override after inspecting the recorded edge-strain probes; automatic motion/export normally stops for correction')
    deformation_report: StringProperty(default='')
    workflow_status: StringProperty(default='')
    workflow_id: StringProperty(default='')
    setup_python: StringProperty(name='Python 3.11',subtype='FILE_PATH',default=str(__import__('pathlib').Path.home()/'miniconda3/python.exe'))
    setup_archive: StringProperty(name='Windows provider archive',subtype='FILE_PATH',default=str(__import__('pathlib').Path(__file__).parent/'artifacts/local_character-windows-providers.zip'))
    setup_status: StringProperty(default='')
    setup_job: StringProperty(default='')
    show_controls: BoolProperty(name='Joint, skinning and export controls',default=False)
    ui_step: EnumProperty(name='Step',items=[('RIG','Rig','Create or adjust joints'),('SKIN','Skin','Bind and refine weights'),('MOTION','Motion','Generate and preview animation')],default='RIG')
    ui_rig_mode: EnumProperty(name='Rigging',items=[('AUTO','Automatic','Infer joints from geometry'),('ASSISTED','Landmarks','Guide joints in a front-view editor')],default='AUTO')
    ui_skin_advanced: BoolProperty(name='Advanced skinning',default=False)
    ui_skin_method: EnumProperty(name='Binding',items=[('AI','AI','Use learned skinning'),('GEODESIC','Surface','Bind along surface edges'),('VOXEL','Volume','Closed-volume heat with surface fallback')],default='AI')
    workflow_skin_only: BoolProperty(default=False,options={'HIDDEN'})
    landmark_data: StringProperty(default='')
    landmark_symmetry: BoolProperty(name='Mirror left and right',default=True)
    hand_guide_data: StringProperty(default='',options={'HIDDEN'})
    ui_weight_bone: StringProperty(name='Bone',update=ui.choose_weight_bone)

for _side in ('Left','Right'):
    for _finger in skeleton.FINGERS:
        LC_Settings.__annotations__['hand_'+_side.lower()+'_'+_finger.lower()]=FloatProperty(name=_finger+' curl',default=0,min=0,max=1)


class LC_Preferences(AddonPreferences):
    bl_idname=__package__
    settings_migrated: BoolProperty(default=False,options={'HIDDEN'})
    page: EnumProperty(name='Settings',items=[('SETUP','Setup','Local provider installation'),('DEFAULTS','Defaults','Runtime and solver defaults'),('RECOVERY','Recovery','Finished jobs and expert workflow options')],default='SETUP')
    def draw(self,context):ui.draw_preferences(self.layout,context,self)

LC_Preferences.__annotations__.update({key:LC_Settings.__annotations__[key] for key in configuration.KEYS})


class LC_OT_optional_bone(Operator):
    bl_idname='local_character.add_optional_bone'
    bl_label='Add at Cursor to New Copy'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs and not workflow._runs
    def execute(self,context):
        try:
            rig,meshes=skinning.selection(context);s=context.scene.lc_settings
            collection,rig,meshes=rig_modules.add(context,rig,meshes,s.optional_kind,s.optional_parent,s.optional_name)
            workflow.select(context,rig,meshes)
            self.report({'INFO'},'Optional bone added. Review its position, then paint weights or mark a rigid region')
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_hand_preset(Operator):
    bl_idname='local_character.hand_preset'
    bl_label='Use Hand Preset'
    bl_options={'UNDO'}
    def execute(self,context):
        s=context.scene.lc_settings;s.hand_controls=True
        for finger,value in zip(skeleton.FINGERS,hand_pose.PRESETS[s.hand_preset]):
            setattr(s,'hand_'+s.hand_side.lower()+'_'+finger.lower(),value)
        return {'FINISHED'}


class LC_OT_deformation_check(Operator):
    bl_idname='local_character.check_deformation'
    bl_label='Check Deformation Probes'
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs
    def execute(self,context):
        try:
            rig,meshes=skinning.selection(context);report=deformation_qa.inspect(rig,meshes)
            context.scene.lc_settings.deformation_report=json.dumps(report)
            severe,warnings=deformation_qa.findings(report)
            self.report({'WARNING'} if severe or warnings else {'INFO'},(severe+warnings)[0] if severe or warnings else 'No severe strain detected; joint and pose review is still required')
        except (ValueError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


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
            setattr(settings, self.status_property, f"{state.get('phase','Running locally')}: {int(state['elapsed_seconds'])} s; Escape cancels")
            if context.screen:
                for area in context.screen.areas: area.tag_redraw()
            return {'PASS_THROUGH'}
        try:
            if state['status'] != 'complete': raise ValueError(state.get('error') or 'Worker failed; inspect worker.log in the last job folder')
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
    bl_label = 'AI Skin Avatar'
    bl_description = 'Run local SkinTokens on accepted joints and apply verified weights to the selected character'
    # Separate apply owns undo; intervening user edits never join the job's undo.
    bl_options = {'REGISTER'}
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and not skinning._jobs
    def execute(self, context):
        settings = configuration.settings(context)
        settings.workflow_skin_only=False
        try:
            rig, meshes = skinning.selection(context)
            self._folder = skinning.prepare(context, rig, meshes, device=settings.skin_device, beams=settings.skin_beams)
            skinning.start(self._folder, bpy.path.abspath(settings.skin_executable), bpy.path.abspath(settings.skin_models))
        except (ValueError, OSError, RuntimeError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return self.begin(context)

class LC_OT_apply_skin(Operator):
    bl_idname = 'local_character.apply_skin_job'
    bl_label = 'Apply Finished Skinning'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and bool(context.scene.lc_settings.skin_job) and not skinning._jobs
    def execute(self, context):
        settings = context.scene.lc_settings
        try:
            request=json.loads((__import__('pathlib').Path(settings.skin_job)/'request.json').read_text())
            source_objects=[bpy.data.objects.get(request['rig']),*[bpy.data.objects.get(m['name']) for m in request['meshes']]]
            collection, rig, meshes = skinning.apply(context, settings.skin_job)
            if not configuration.settings(context).keep_skin_copies:
                rig,meshes=character_result.skin(context,source_objects[0],source_objects[1:],rig,meshes)
            else:configuration.hide_sources(context,source_objects)
            for obj in context.selected_objects: obj.select_set(False)
            for obj in [rig, *meshes]: obj.select_set(True)
            context.view_layer.objects.active = rig
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            settings.skin_status = str(exc)
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        settings.skin_status = 'Skinning ready; accepted joints preserved'
        self.report({'INFO'}, settings.skin_status)
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
        self.report({'INFO'}, 'Region marked; next refinement applies it to the character')
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
    bl_label = 'Refine Skinning'
    bl_options = {'REGISTER'}
    status_property = 'region_status'
    job_property = 'region_job'
    apply_operator = 'apply_region_job'
    binding_method: StringProperty(default='',options={'HIDDEN'})
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and not skinning._jobs
    def execute(self, context):
        settings = configuration.settings(context)
        try:
            rig, meshes = skinning.selection(context)
            self._folder = regional_jobs.prepare(context, rig, meshes, method=self.binding_method or settings.refine_method,
                iterations=settings.refine_iterations, strength=settings.refine_strength,
                selected_only=settings.refine_selected, join_seams=settings.refine_seams,voxel_resolution=settings.voxel_resolution)
            regional_jobs.start(self._folder)
        except (ValueError, OSError, RuntimeError) as exc: self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        return self.begin(context)


class LC_OT_apply_region(Operator):
    bl_idname = 'local_character.apply_region_job'
    bl_label = 'Apply Finished Refinement'
    bl_options = {'REGISTER', 'UNDO'}
    @classmethod
    def poll(cls, context): return context.mode == 'OBJECT' and not skinning._jobs and bool(context.scene.lc_settings.region_job)
    def execute(self, context):
        settings = context.scene.lc_settings
        try:
            request=json.loads((__import__('pathlib').Path(settings.region_job)/'request.json').read_text())
            source_objects=[bpy.data.objects.get(request['rig']),*[bpy.data.objects.get(m['name']) for m in request['meshes']]]
            (collection, rig, meshes), report = regional_jobs.apply(context, settings.region_job)
            if not configuration.settings(context).keep_skin_copies:
                rig,meshes=character_result.skin(context,source_objects[0],source_objects[1:],rig,meshes)
            else:configuration.hide_sources(context,source_objects)
            for obj in context.selected_objects: obj.select_set(False)
            for obj in [rig, *meshes]: obj.select_set(True)
            context.view_layer.objects.active = rig
            settings.region_report = json.dumps(report)
        except (ValueError, OSError, RuntimeError, KeyError) as exc:
            settings.region_status = str(exc); self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        settings.region_status = 'Skinning ready; protected weights preserved'
        self.report({'INFO'}, settings.region_status)
        return {'FINISHED'}

class LC_OT_place(WorkerModal,Operator):
    bl_idname='local_character.place_joints'
    bl_label='Find Humanoid Joints Locally'
    bl_options={'REGISTER'}
    status_property='placement_status'
    job_property='placement_job'
    apply_operator='apply_placement_job'
    use_landmarks: BoolProperty(default=False,options={'HIDDEN'})
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs and not hands._sessions and not landmarks._sessions
    def execute(self,context):
        try:
            rig,meshes=placement.selected(context)
            settings=configuration.settings(context)
            guides=landmarks.validate(json.loads(settings.landmark_data),meshes) if self.use_landmarks else None
            self._folder=placement.prepare(context,meshes,rig,provider=__import__('pathlib').Path(bpy.path.abspath(settings.placement_python)).parent.parent.parent,landmarks=guides)
            placement.start(self._folder,bpy.path.abspath(settings.placement_python))
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return self.begin(context)


class LC_OT_apply_placement(Operator):
    bl_idname='local_character.apply_placement_job'
    bl_label='Create Editable Joint Proposal'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs and bool(context.scene.lc_settings.placement_job)
    def execute(self,context):
        settings=context.scene.lc_settings
        try:
            source=json.loads((__import__('pathlib').Path(settings.placement_job)/'source.json').read_text())
            source_objects=[bpy.data.objects.get(source['rig']) if source['rig'] else None,*[bpy.data.objects.get(m['name']) for m in source['meshes']]]
            collection,rig,meshes,result=placement.apply(context,settings.placement_job)
            configuration.hide_sources(context,source_objects)
            for obj in context.selected_objects:obj.select_set(False)
            for obj in [rig,*meshes]:obj.select_set(True)
            context.view_layer.objects.active=rig
        except (ValueError,OSError,RuntimeError,KeyError) as exc:
            settings.placement_status=str(exc);self.report({'ERROR'},str(exc));return {'CANCELLED'}
        review=[r['side']+' '+r['finger'] for r in result.get('hand_report',[]) if r.get('requires_review')]
        if source.get('hands_only'):
            settings.placement_status='Hands refined; body joints preserved. Inspect fingers, then skin again.'
            settings.ui_step='RIG'
        else:
            settings.placement_status='Rig created. Review joints before skinning.'
            settings.ui_step='SKIN'
        if review:settings.placement_status+=' Hand guides recommended: '+', '.join(review)+'.'
        self.report({'INFO'},f'Created {collection.name}; originals preserved')
        return {'FINISHED'}


class LC_OT_refine_hands(WorkerModal,Operator):
    bl_idname='local_character.refine_hands'
    bl_label='Refine Hands'
    bl_description='Predict fingers using accepted wrists, then fit clear closed sections; preserve all body joints on a review copy'
    bl_options={'REGISTER'}
    status_property='placement_status'
    job_property='placement_job'
    apply_operator='apply_placement_job'
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs and not hands._sessions and not landmarks._sessions
    def execute(self,context):
        try:
            rig,meshes=hands.character(context);settings=configuration.settings(context)
            self._folder=placement.prepare(context,meshes,rig,provider=__import__('pathlib').Path(bpy.path.abspath(settings.placement_python)).parent.parent.parent,
                hands_only=True,finger_guides=hands.saved_guides(context,rig,meshes))
            placement.start(self._folder,bpy.path.abspath(settings.placement_python))
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return self.begin(context)


class LC_OT_lock_joints(Operator):
    bl_idname='local_character.lock_joints'
    bl_label='Lock Selected Joint Positions'
    bl_options={'REGISTER','UNDO'}
    enabled:BoolProperty(default=True)
    @classmethod
    def poll(cls,context):return context.active_object and context.active_object.type=='ARMATURE' and context.mode in {'OBJECT','POSE'}
    def execute(self,context):
        bones=[b for b in context.active_object.data.bones if b.select]
        if not bones:self.report({'ERROR'},'Select corrected joints first');return {'CANCELLED'}
        if context.active_object.data.users>1:self.report({'ERROR'},'Make the armature data single-user first');return {'CANCELLED'}
        for bone in bones:bone['lc_joint_locked']=self.enabled
        self.report({'INFO'},f'{len(bones)} joint position locks updated')
        return {'FINISHED'}


class LC_OT_motion(WorkerModal, Operator):
    bl_idname='local_character.generate_motion'
    bl_label='Generate Local Motion'
    bl_options={'REGISTER'}
    status_property='motion_status'
    job_property='motion_job'
    apply_operator='apply_motion_job'
    @classmethod
    def poll(cls, context): return context.mode=='OBJECT' and not skinning._jobs
    def execute(self, context):
        settings=configuration.settings(context)
        try:
            rig=motion_jobs.selected_rig(context)
            self._folder=motion_jobs.prepare(context,rig,settings.motion_prompt,settings.motion_frames,
                settings.motion_steps,settings.motion_seed,settings.motion_in_place,keyframes=settings.motion_use_keyframes,start_frame=context.scene.frame_start)
            motion_jobs.start(self._folder,bpy.path.abspath(settings.motion_provider))
        except (ValueError,OSError,RuntimeError,KeyError) as exc: self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        return self.begin(context)


class LC_OT_apply_motion(Operator):
    bl_idname='local_character.apply_motion_job'
    bl_label='Create Copy from Finished Motion'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls, context): return context.mode=='OBJECT' and not skinning._jobs and bool(context.scene.lc_settings.motion_job)
    def execute(self, context):
        settings=context.scene.lc_settings
        try:
            request=json.loads((__import__('pathlib').Path(settings.motion_job)/'request.json').read_text())
            source_objects=[bpy.data.objects.get(request['rig']),*[bpy.data.objects.get(m['name']) for m in request['meshes']]]
            collection,rig,meshes,action,report=motion_apply.apply(context,settings.motion_job,settings.motion_hand_curl,settings.motion_contacts,settings.motion_heading,
                hand_pose.settings(settings) if settings.hand_controls else None)
            configuration.hide_sources(context,source_objects)
            for obj in context.selected_objects: obj.select_set(False)
            for obj in [rig,*meshes]: obj.select_set(True)
            context.view_layer.objects.active=rig
        except (ValueError,OSError,RuntimeError,KeyError) as exc:
            settings.motion_status=str(exc); self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        settings.motion_status='Editable motion copy created; inspect contacts and export the selected Action'
        settings.include_action=True
        self.report({'INFO'},f'Created {collection.name}: {report["frames"]} frames at 30 fps')
        return {'FINISHED'}


class LC_OT_finish_loop(Operator):
    bl_idname='local_character.finish_loop'
    bl_label='Make Editable Loop Copy'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs
    def execute(self,context):
        settings=context.scene.lc_settings
        try:
            rig=motion_jobs.selected_rig(context)
            action=motion_finish.loop(context,rig,settings.motion_loop_blend)
        except (ValueError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        settings.loop_action=True
        settings.motion_status='Loop copy created; review endpoint velocities and contact timing before export'
        self.report({'INFO'},f'Created {action.name}; original Action preserved')
        return {'FINISHED'}


class LC_OT_preview_motion(Operator):
    bl_idname='local_character.preview_motion'
    bl_label='Preview Selected Motion'
    bl_options={'UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs
    def execute(self,context):
        try:
            from .animation import selected_action
            rig=motion_jobs.selected_rig(context);selection=selected_action(rig,context.scene)
            scene=context.scene;scene.use_preview_range=True;scene.frame_preview_start=selection['frame_start'];scene.frame_preview_end=selection['frame_end']
            scene.frame_set(selection['frame_start'])
        except (ValueError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_install(WorkerModal,Operator):
    bl_idname='local_character.install_providers'
    bl_label='Install Local Providers'
    bl_description='Install verified native files and download pinned checkpoints into the local cache; inference stays local'
    bl_options={'REGISTER'}
    status_property='setup_status'
    job_property='setup_job'
    apply_operator='finish_provider_setup'
    @classmethod
    def poll(cls,context):return not skinning._jobs and not workflow._runs
    def execute(self,context):
        try:
            settings=configuration.settings(context)
            self._folder=install_jobs.start(bpy.path.abspath(settings.setup_python),bpy.path.abspath(settings.setup_archive))
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return self.begin(context)


class LC_OT_install_finished(Operator):
    bl_idname='local_character.finish_provider_setup'
    bl_label='Finish Provider Setup'
    bl_options={'INTERNAL'}
    def execute(self,context):
        if skinning.poll(context.scene.lc_settings.setup_job)['status']!='complete':return {'CANCELLED'}
        context.scene.lc_settings.setup_status='Local providers installed; model hashes are checked again when jobs launch'
        return {'FINISHED'}


class LC_OT_twists(Operator):
    bl_idname='local_character.add_twists'
    bl_label='Add Forearm Twists to New Copy'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and not skinning._jobs
    def execute(self,context):
        try:
            rig,meshes=skinning.selection(context);_,rig,meshes=twists.add(context,rig,meshes)
            workflow.select(context,rig,meshes)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'Two optional helpers added; selected Actions are baked. Unity Humanoid needs the twist component')
        return {'FINISHED'}


class LC_OT_twist_pose(Operator):
    bl_idname='local_character.update_twist_pose'
    bl_label='Update Twist Pose'
    bl_options={'UNDO'}
    @classmethod
    def poll(cls,context):return context.mode in {'OBJECT','POSE'} and not skinning._jobs
    def execute(self,context):
        try:twists.update_pose(motion_jobs.selected_rig(context))
        except (ValueError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_build(Operator):
    bl_idname='local_character.build_character'
    bl_label='Build Character Locally'
    bl_description='Place humanoid joints, bind with AI, refine regions, and optionally generate motion and export'
    bl_options={'REGISTER'}
    _timer=None
    _run=None
    auto_skin: BoolProperty(default=False,options={'HIDDEN'})
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and any(o.type=='MESH' for o in context.selected_objects) and not skinning._jobs and not workflow._runs
    def execute(self,context):
        try:
            settings=configuration.settings(context);values=workflow.options(settings,self.auto_skin,context)
            settings.workflow_skin_only=self.auto_skin
            self._run=workflow.Run(context,values);self._run.launch(context)
            context.scene.lc_settings.workflow_id=self._run.id
            self._timer=context.window_manager.event_timer_add(.5,window=context.window)
            context.window_manager.modal_handler_add(self)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:
            if self._run:self._run.cancel(str(exc))
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'RUNNING_MODAL'}
    def _finish(self,context):
        if self._timer:context.window_manager.event_timer_remove(self._timer)
        self._timer=None
    def modal(self,context,event):
        if event.type=='ESC':
            self._run.cancel();self._run.scene.lc_settings.workflow_status='Cancelled; finished review copies remain available'
            self._finish(context);return {'CANCELLED'}
        if event.type!='TIMER':return {'PASS_THROUGH'}
        try:
            settings=self._run.scene.lc_settings;state=skinning.poll(self._run.folder)
            if state['status']=='running':
                settings.workflow_status=f"{self._run.stage}: {state.get('phase','Running locally')} ({int(state['elapsed_seconds'])} s); Escape cancels"
            else:
                if state['status']!='complete':raise ValueError(state.get('error') or 'Local phase failed; inspect its worker.log')
                if context.scene!=self._run.scene:raise ValueError('Return to the original scene; finished phase is available from its individual job')
                if bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')!={'FINISHED'}:raise ValueError(settings.workflow_status)
                if self._run.halted:
                    self.report({'WARNING'},self._run.halted);self._finish(context);return {'FINISHED'}
                if self._run.finished:
                    settings.workflow_status='Character ready for deformation review; editable results selected'
                    self._finish(context);return {'FINISHED'}
            if context.screen:
                for area in context.screen.areas:area.tag_redraw()
        except (ReferenceError,ValueError,OSError,RuntimeError,KeyError) as exc:
            self._run.cancel(str(exc));self.report({'ERROR'},str(exc));self._finish(context);return {'CANCELLED'}
        return {'PASS_THROUGH'}
    def cancel(self,context):
        if self._run:self._run.cancel()
        self._finish(context)


class LC_OT_advance_workflow(Operator):
    bl_idname='local_character.advance_workflow'
    bl_label='Accept Finished Workflow Phase'
    bl_options={'UNDO','INTERNAL'}
    def execute(self,context):
        try:
            run=workflow._runs.get(context.scene.lc_settings.workflow_id)
            if not run:raise ValueError('Workflow session no longer exists; apply the finished individual job instead')
            run.apply_step(context)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:
            context.scene.lc_settings.workflow_status=str(exc);self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_PT_main(Panel):
    bl_label = "Rigmodo"
    bl_idname = "LC_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Rigmodo"
    def draw(self, context):ui.draw(self.layout,context)

CLASSES = (LC_Settings, LC_Preferences, *auto_pose.CLASSES, *image_pose.CLASSES, *ui.CLASSES, *landmarks.CLASSES, *hands.CLASSES, *motion_keyframes.CLASSES, LC_OT_create_template, LC_OT_preflight, LC_OT_export, LC_OT_skin, LC_OT_apply_skin,
           LC_OT_protect, LC_OT_mark_region, LC_OT_clear_region, LC_OT_refine, LC_OT_apply_region,
           LC_OT_place,LC_OT_refine_hands,LC_OT_apply_placement,LC_OT_lock_joints,LC_OT_motion, LC_OT_apply_motion, LC_OT_finish_loop,LC_OT_preview_motion,
           LC_OT_install,LC_OT_install_finished,LC_OT_twists,LC_OT_twist_pose,LC_OT_optional_bone,LC_OT_hand_preset,LC_OT_deformation_check,LC_OT_build,LC_OT_advance_workflow,LC_PT_main)
@persistent
def migrate_workflow_tab(_=None):
    for scene in bpy.data.scenes:
        if scene.library:continue
        settings=scene.lc_settings
        if settings.get('ui_step') in (3,'EXPORT'):settings.ui_step='MOTION'

def register():
    for cls in CLASSES: bpy.utils.register_class(cls)
    bpy.types.Scene.lc_settings = PointerProperty(type=LC_Settings)
    bpy.app.timers.register(migrate_workflow_tab,first_interval=0)
    bpy.app.handlers.load_post.append(migrate_workflow_tab)
    auto_pose.register()
    image_pose.register()

def unregister():
    if bpy.app.timers.is_registered(migrate_workflow_tab):bpy.app.timers.unregister(migrate_workflow_tab)
    if migrate_workflow_tab in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(migrate_workflow_tab)
    image_pose.unregister()
    auto_pose.cleanup()
    landmarks.cleanup()
    hands.cleanup()
    for run in list(workflow._runs.values()):run.cancel()
    skinning.cancel_all()
    del bpy.types.Scene.lc_settings
    for cls in reversed(CLASSES): bpy.utils.unregister_class(cls)
