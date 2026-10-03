# SPDX-License-Identifier: GPL-3.0-or-later
"""Selection-scoped export in an isolated scene, committed as a new bundle."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import tomllib

import bpy
from mathutils import Matrix
from .preflight import inspect, UNITY_WEIGHT_FLOOR
from .skeleton import HIERARCHY_VERSION, resolve_mapping
from .animation import selected_action, attach_action

VERSION = tomllib.loads(Path(__file__).with_name('blender_manifest.toml').read_text())['version']


def _root_motion(scene, rig, selection):
    """Independent root trajectory in Unity's reflected model frame, meters."""
    from mathutils import Vector
    if selection['frame_end']-selection['frame_start'] > 3600: raise ValueError('Explicit Root motion exceeds the 3600-frame export budget')
    conversion=Matrix(((-1,0,0),(0,0,1),(0,-1,0)))
    samples=[];first=None;previous=None
    for frame in range(selection['frame_start'],selection['frame_end']+1):
        scene.frame_set(frame)
        evaluated=rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        matrix=evaluated.matrix_world@evaluated.pose.bones['Root'].matrix
        if first is None:first=matrix.copy()
        delta=(matrix.translation-first.translation)*scene.unit_settings.scale_length
        rotation=conversion@(matrix.to_quaternion().to_matrix()@first.to_quaternion().to_matrix().transposed())@conversion.transposed()
        q=rotation.to_quaternion()
        if previous and q.dot(previous)<0:q.negate()
        previous=q.copy();p=conversion@delta
        samples.append(dict(time=(frame-selection['frame_start'])/selection['fps'],
            position=dict(x=p.x,y=p.y,z=p.z),rotation=dict(x=q.x,y=q.y,z=q.z,w=q.w)))
    return dict(coordinate_space='unity_model_meters',samples=samples)

def safe_name(value):
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", value).strip("_")[:80]
    if not name or name.upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
        raise ValueError("Choose a character name containing letters or numbers")
    return name


def _prune(mesh, rig):
    bone_groups = {g.index: g for g in mesh.vertex_groups if g.name in rig.data.bones}
    deform = {index for index, group in bone_groups.items() if rig.data.bones[group.name].use_deform}
    rows = []
    for vertex in mesh.data.vertices:
        row = sorted(((g.group, g.weight) for g in vertex.groups if g.group in deform and g.weight > 0),
                     key=lambda pair: (-pair[1], pair[0]))[:4]
        total = sum(weight for _, weight in row)
        if not total:
            raise ValueError(f"{mesh.name}: vertex {vertex.index} has no deform weights")
        # Unity 6.3/6.4 reload a requested smaller minimum as .001. Mirror
        # its policy on the export copy, always retaining the strongest bone.
        normalized = [(index, weight / total) for index, weight in row]
        retained = [pair for n, pair in enumerate(normalized) if n == 0 or pair[1] >= UNITY_WEIGHT_FLOOR]
        retained_total = sum(weight for _, weight in retained)
        rows.append([(index, weight / retained_total) for index, weight in retained])
    vertices = list(range(len(mesh.data.vertices)))
    for group in bone_groups.values():
        group.remove(vertices)
    for vertex, row in enumerate(rows):
        for index, weight in row:
            bone_groups[index].add([vertex], weight, "REPLACE")

def _add_root(context, rig):
    if "Root" in rig.data.bones:
        if rig.data.bones["Root"].parent:
            raise ValueError("Existing Root must be a top-level structural bone")
        return
    context.view_layer.objects.active = rig
    rig.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        existing = list(rig.data.edit_bones)
        root = rig.data.edit_bones.new("Root")
        root.head, root.tail = (0, 0, 0), (0, 0, .1)
        root.use_deform = False
        for bone in existing:
            if not bone.parent:
                bone.parent = root
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")

def _manifest(rig, meshes, report, name, unit_scale):
    bones = []
    for bone in rig.data.bones:
        chain, cursor = [], bone
        while cursor:
            chain.append(cursor.name); cursor = cursor.parent
        bones.append({"name": bone.name, "parent": bone.parent.name if bone.parent else "",
                      "path": "/".join(reversed(chain)), "deform": bone.use_deform,
                      "rest_matrix_blender": [list(row) for row in bone.matrix_local]})
    signature = hashlib.sha256(json.dumps(bones, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema_version": 1, "artifact_kind": "character", "generator": "local_character/"+VERSION, "character": name,
            "profile": report["profile"], "hierarchy_version": HIERARCHY_VERSION if rig.get("lc_hierarchy_version") else "imported-preserved",
            "skeleton_signature": signature, "rig_object": rig.name,
            "mapping": resolve_mapping(rig.data.bones), "bones": bones,
            "rig_world_blender": [list(row) for row in rig.matrix_world],
            "units": {"source_meters_per_unit": unit_scale, "target": "meters", "fbx_forward": "-Z", "fbx_up": "Y"},
            "maximum_influences": 4, "minimum_export_weight": UNITY_WEIGHT_FLOOR, "root_motion_policy": "no_clips_exported",
            "calibration_state": "unity_companion_required" if report["profile"] == "HUMANOID" else "not_applicable",
            "modules": {"twist": bool(rig.get('lc_twists')), "eyes": any(b.name.endswith("Eye") for b in rig.data.bones),
                        "jaw":any(b.name.rsplit(':',1)[-1]=='Jaw' for b in rig.data.bones),
                        "sockets":any(m.get('kind')=='SOCKET' for m in json.loads(rig.get('lc_optional_bones','[]')))},
            "optional_bones":json.loads(rig.get('lc_optional_bones','[]')),
            "twists": json.loads(rig.get('lc_twists','[]')),
            "meshes": [{"name": obj.name, "vertices": len(obj.data.vertices),
                        "shape_keys": [key.name for key in obj.data.shape_keys.key_blocks][1:] if obj.data.shape_keys else [],
                        "materials": [m.name if m else "" for m in obj.data.materials]} for obj in meshes],
            "clips": [], "provenance": {"placement": rig.get("lc_placement", "imported_accepted_rig"),
                "skinning": rig.get("lc_skinning", "existing_weights_pruned_on_export_copy"),
                "skin_provider_revision": rig.get("lc_skin_provider_revision", ""),
                "skin_model_revision": rig.get("lc_skin_model_revision", ""),
                "export_weight_policy": "four_influences_001_floor_normalized_on_copy"},
            "warnings": report["warnings"]}

def export_bundle(context, rig, meshes, directory, character_name, profile="HUMANOID", include_action=False, loop=False):
    if context.mode != "OBJECT":
        raise ValueError("Switch to Object Mode before exporting")
    report = inspect(rig, meshes, profile)
    if report["errors"]:
        raise ValueError("; ".join(report["errors"]))
    selection = selected_action(rig, context.scene) if include_action else None
    name = safe_name(character_name)
    parent = Path(bpy.path.abspath(directory)).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    destination = parent / name
    if destination.exists():
        raise ValueError(f"Bundle already exists: {destination}. Choose a new name; existing exports are preserved")
    stage = Path(tempfile.mkdtemp(prefix=f".{name}-", dir=parent))
    scene = bpy.data.scenes.new("Local Character Export")
    original_scene = context.scene
    window = context.window
    original_window_scene = window.scene if window else None
    original_window_layer = window.view_layer if window else None
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = original_scene.unit_settings.scale_length
    created, copied_data, copied_materials, copied_images = [], [], [], []
    twist_action=None
    try:
        copied_rig = rig.copy(); copied_rig.data = rig.data.copy()
        created.append(copied_rig); copied_data.append(copied_rig.data)
        copied_rig.name = "LocalCharacterExportRig"
        copied_rig.parent = None; copied_rig.matrix_world = rig.matrix_world.copy()
        copied_rig.hide_viewport = False
        copied_rig.animation_data_clear()
        for constraint in list(copied_rig.constraints): copied_rig.constraints.remove(constraint)
        copied_rig.data.pose_position = "REST"
        scene.collection.objects.link(copied_rig)
        copied_meshes = []
        for source in meshes:
            mesh = source.copy(); mesh.data = source.data.copy()
            created.append(mesh); copied_data.append(mesh.data)
            mesh.animation_data_clear()
            mesh.hide_viewport = False
            for constraint in list(mesh.constraints): mesh.constraints.remove(constraint)
            mesh.parent = copied_rig; mesh.parent_type = "OBJECT"
            mesh.matrix_parent_inverse = Matrix.Identity(4)
            mesh.matrix_world = source.matrix_world.copy()
            for modifier in mesh.modifiers:
                if modifier.type == "ARMATURE": modifier.object = copied_rig
            scene.collection.objects.link(mesh)
            _prune(mesh, copied_rig)
            copied_meshes.append(mesh)
        material_map, image_map = {}, {}
        for mesh in copied_meshes:
            for index, material in enumerate(mesh.data.materials):
                if material is None: continue
                if material not in material_map:
                    copied = material.copy(); material_map[material] = copied; copied_materials.append(copied)
                    if copied.use_nodes:
                        for node in copied.node_tree.nodes:
                            if node.type != "TEX_IMAGE" or node.image is None: continue
                            image = node.image
                            if image not in image_map and image.packed_file:
                                texture = image.copy(); copied_images.append(texture)
                                texture.filepath_raw = str(stage / (safe_name(image.name) + ".png"))
                                texture.file_format = "PNG"
                                texture.save()
                                image_map[image] = texture
                            if image in image_map: node.image = image_map[image]
                mesh.data.materials[index] = material_map[material]
        if window:
            window.scene = scene
        view_layer = scene.view_layers[0]
        with context.temp_override(scene=scene, view_layer=view_layer):
            _add_root(context, copied_rig)
            if "Root" not in copied_rig.data.bones:
                raise RuntimeError("Temporary export root was not committed")
            for obj in created: obj.select_set(True, view_layer=view_layer)
            view_layer.objects.active = copied_rig
            view_layer.update()
            manifest = _manifest(copied_rig, copied_meshes, report, name, scene.unit_settings.scale_length)
            # FBX modifier application suppresses shape keys, so base geometry is explicit.
            bpy.ops.export_scene.fbx(filepath=str(stage / f"{name}.fbx"), check_existing=False,
                use_selection=True, object_types={"ARMATURE", "MESH"},
                global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                axis_forward="-Z", axis_up="Y", use_space_transform=True, bake_space_transform=False,
                use_mesh_modifiers=False, add_leaf_bones=False, use_armature_deform_only=False,
                bake_anim=False, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                path_mode="COPY", embed_textures=False)
            if selection:
                clip_name = safe_name(selection["action"].name)
                clip_dir = stage / "Animations"
                clip_dir.mkdir()
                clip_file = clip_dir / f"{clip_name}.fbx"
                # Capture the same hierarchy/rest signature before Action evaluation.
                clip_manifest = _manifest(copied_rig, [], report, name, scene.unit_settings.scale_length)
                clip = {"name": clip_name, "file": f"Animations/{clip_name}.fbx",
                        "frame_start": selection["frame_start"], "frame_end": selection["frame_end"],
                        "fps": selection["fps"], "loop": bool(loop),
                        "root_motion_policy": "preserve_bone_motion"}
                clip_manifest.update(artifact_kind="animation", source_model=f"../{name}.fbx",
                                     source_model_sha256=hashlib.sha256((stage / f"{name}.fbx").read_bytes()).hexdigest(),
                                     clips=[clip], root_motion_policy=clip["root_motion_policy"])
                attach_action(copied_rig, selection)
                scene.render.fps = original_scene.render.fps
                scene.render.fps_base = original_scene.render.fps_base
                scene.frame_start, scene.frame_end = selection["frame_start"], selection["frame_end"]
                if copied_rig.get('lc_twists'):
                    from . import twists
                    twist_action=twists.bake_action(context,copied_rig,selection)
                scene.name = clip_name
                scene.frame_set(scene.frame_start)
                if selection['action'].get('lc_explicit_root_motion'):
                    clip['explicit_root_motion']=_root_motion(scene,copied_rig,selection)
                    scene.frame_set(scene.frame_start)
                for mesh in copied_meshes: mesh.select_set(False, view_layer=view_layer)
                bpy.ops.export_scene.fbx(filepath=str(clip_file), check_existing=False,
                    use_selection=True, object_types={"ARMATURE"},
                    global_scale=1.0, apply_unit_scale=True, apply_scale_options="FBX_SCALE_ALL",
                    axis_forward="-Z", axis_up="Y", use_space_transform=True, bake_space_transform=False,
                    add_leaf_bones=False, use_armature_deform_only=False,
                    bake_anim=True, bake_anim_use_all_actions=False, bake_anim_use_nla_strips=False,
                    bake_anim_use_all_bones=True, bake_anim_force_startend_keying=True,
                    bake_anim_step=1.0, bake_anim_simplify_factor=0.0)
                clip_manifest["fbx_sha256"] = hashlib.sha256(clip_file.read_bytes()).hexdigest()
                clip_file.with_suffix(".character.json").write_text(json.dumps(clip_manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
                manifest["clips"] = [clip]
                manifest["root_motion_policy"] = clip["root_motion_policy"]
        manifest["fbx_sha256"] = hashlib.sha256((stage / f"{name}.fbx").read_bytes()).hexdigest()
        (stage / f"{name}.character.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        (stage / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        # Rename within one filesystem; incomplete work never appears as a finished bundle.
        os.rename(stage, destination)
        return destination
    finally:
        if window:
            window.scene = original_window_scene
            window.view_layer = original_window_layer
        for obj in created:
            if obj.name in bpy.data.objects: bpy.data.objects.remove(obj, do_unlink=True)
        for data in copied_data:
            if data.users == 0:
                if isinstance(data, bpy.types.Armature): bpy.data.armatures.remove(data)
                else: bpy.data.meshes.remove(data)
        if twist_action and twist_action.users==0:bpy.data.actions.remove(twist_action)
        bpy.data.scenes.remove(scene)
        for material in copied_materials:
            if material.users == 0: bpy.data.materials.remove(material)
        for image in copied_images:
            if image.users == 0: bpy.data.images.remove(image)
        if stage.exists():
            if stage.resolve().parent != parent or not stage.name.startswith(f".{name}-"):
                raise RuntimeError("Refusing cleanup outside the verified export staging directory")
            shutil.rmtree(stage)
