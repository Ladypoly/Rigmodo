# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only selected-character inspection and weight validation."""
import math
from .skeleton import REQUIRED, canonical_name, resolve_mapping

def selection(context):
    selected = list(context.selected_objects)
    rigs = {o for o in selected if o.type == "ARMATURE"}
    meshes = [o for o in selected if o.type == "MESH"]
    for mesh in meshes:
        rigs.update(m.object for m in mesh.modifiers if m.type == "ARMATURE" and m.object)
    if len(rigs) != 1:
        raise ValueError("Select meshes belonging to exactly one armature (or select that armature)")
    rig = next(iter(rigs))
    shapes = {pb.custom_shape for pb in rig.pose.bones if pb.custom_shape}
    meshes = [o for o in meshes if o not in shapes]
    return rig, meshes

def inspect(rig, meshes, profile="HUMANOID"):
    errors, warnings, summaries = [], [], []
    if not meshes:
        errors.append("Select the character meshes to include; selecting the armature alone does not export all its LODs")
    names = {canonical_name(b.name) for b in rig.data.bones}
    try:
        mapping = resolve_mapping(rig.data.bones)
    except ValueError as exc:
        mapping = []; errors.append(str(exc))
    if profile == "HUMANOID":
        missing = sorted(REQUIRED - names)
        if missing:
            errors.append("Missing supported humanoid bones: " + ", ".join(missing))
    if "Root" not in names:
        warnings.append("Export will add an unweighted structural Root on a temporary copy")
    for bone in rig.data.bones:
        if not all(math.isfinite(v) for row in bone.matrix_local for v in row):
            errors.append(f"{bone.name}: nonfinite rest transform")
    for obj in [rig, *meshes]:
        if abs(obj.matrix_world.determinant()) < 1e-10:
            errors.append(f"{obj.name}: singular object transform")
        if obj.matrix_world.determinant() < 0:
            errors.append(f"{obj.name}: mirrored transform needs explicit correction before export")
    # Blender's FBX exporter cannot safely represent arbitrary armature object scaling.
    scale = rig.matrix_world.to_scale()
    if max(scale) - min(scale) > 1e-5:
        errors.append("Nonuniform armature world scale is not supported by this export profile")
    for mesh in meshes:
        modifiers = [m for m in mesh.modifiers if m.type == "ARMATURE" and m.object]
        if len(modifiers) != 1 or modifiers[0].object != rig:
            errors.append(f"{mesh.name}: requires one armature modifier using the selected rig")
        extra = [m.name for m in mesh.modifiers if m.type != "ARMATURE" and m.show_viewport]
        if extra:
            errors.append(f"{mesh.name}: resolve non-armature modifiers on a working copy: " + ", ".join(extra))
        if any(not math.isfinite(value) for vertex in mesh.data.vertices for value in vertex.co):
            errors.append(f"{mesh.name}: nonfinite vertex coordinates")
        import bpy
        from pathlib import Path
        for material in mesh.data.materials:
            if not material or not material.use_nodes: continue
            for node in material.node_tree.nodes:
                if node.type != "TEX_IMAGE" or not node.image: continue
                image = node.image
                if image.source not in {"FILE", "GENERATED"}:
                    errors.append(f"{mesh.name}: image {image.name} uses unsupported {image.source} source")
                elif image.source == "GENERATED" and not image.packed_file:
                    errors.append(f"{mesh.name}: pack generated image {image.name} before exporting")
                elif image.source == "FILE" and not image.packed_file and not Path(bpy.path.abspath(image.filepath, library=image.library)).is_file():
                    errors.append(f"{mesh.name}: missing texture {image.name}")
        groups = {g.index for g in mesh.vertex_groups if g.name in rig.data.bones and rig.data.bones[g.name].use_deform}
        unweighted = invalid = over_limit = unnormalized = 0
        for vertex in mesh.data.vertices:
            weights = [g.weight for g in vertex.groups if g.group in groups and g.weight != 0]
            invalid += any(not math.isfinite(w) or w < 0 for w in weights)
            positive = [w for w in weights if math.isfinite(w) and w > 0]
            unweighted += not positive
            over_limit += len(positive) > 4
            unnormalized += bool(positive) and abs(sum(positive) - 1) > 1e-4
        if invalid or unweighted:
            errors.append(f"{mesh.name}: {unweighted} unweighted vertices; {invalid} invalid weight rows")
        if over_limit or unnormalized:
            warnings.append(f"{mesh.name}: export copy will prune {over_limit} rows to four weights and normalize {unnormalized} rows; deformation needs review")
        summaries.append({"name": mesh.name, "vertices": len(mesh.data.vertices),
                          "polygons": len(mesh.data.polygons), "shape_keys": len(mesh.data.shape_keys.key_blocks)-1 if mesh.data.shape_keys else 0,
                          "unweighted": unweighted, "invalid": invalid, "over_four": over_limit})
    return {"schema_version": 1, "rig": rig.name, "profile": profile,
            "bones": len(rig.data.bones), "mapping": mapping, "meshes": summaries,
            "errors": errors, "warnings": warnings, "ready": not errors}
