# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned parametric template. No reference avatar coordinates are distributed."""
from dataclasses import dataclass
from math import cos, sin, radians, isfinite

HIERARCHY_VERSION = "mixamo-core-1"
BODY = {
    "Hips": "Hips", "Spine": "Spine", "Spine1": "Chest",
    "Spine2": "UpperChest", "Neck": "Neck", "Head": "Head",
}
LIMBS = {"Shoulder": "Shoulder", "Arm": "UpperArm", "ForeArm": "LowerArm",
         "Hand": "Hand", "UpLeg": "UpperLeg", "Leg": "LowerLeg",
         "Foot": "Foot", "ToeBase": "Toes"}
FINGERS = ("Thumb", "Index", "Middle", "Ring", "Pinky")

def human_mapping():
    mapping = dict(BODY)
    for side in ("Left", "Right"):
        mapping.update({side + k: side + v for k, v in LIMBS.items()})
        for finger in FINGERS:
            for number, segment in enumerate(("Proximal", "Intermediate", "Distal"), 1):
                mapping[f"{side}Hand{finger}{number}"] = side + ("Little" if finger == "Pinky" else finger) + segment
    return mapping

HUMAN_MAPPING = human_mapping()
REQUIRED = {"Hips", "Spine", "Head"} | {
    side + name for side in ("Left", "Right")
    for name in ("Arm", "ForeArm", "Hand", "UpLeg", "Leg", "Foot")
}

def canonical_name(name):
    return name.rsplit(":", 1)[-1]

@dataclass(frozen=True)
class Joint:
    name: str
    parent: str | None
    head: tuple
    tail: tuple
    deform: bool = True

def template(height=1.75, arm_angle=0.0, eyes=False):
    """Coordinates are Z-up, facing -Y, left is +X; angle lowers both arms."""
    if not isfinite(height) or height <= 0 or not 0 <= arm_angle <= 70:
        raise ValueError("Height must be positive and arm angle 0–70 degrees")
    joints = []
    def add(name, parent, head, tail, deform=True):
        joints.append(Joint(name, parent, tuple(v * height for v in head),
                            tuple(v * height for v in tail), deform))
    add("Root", None, (0, 0, 0), (0, 0, .06), False)
    for name, parent, lo, hi in (
        ("Hips", "Root", .51, .57), ("Spine", "Hips", .57, .65),
        ("Spine1", "Spine", .65, .73), ("Spine2", "Spine1", .73, .83),
        ("Neck", "Spine2", .83, .89), ("Head", "Neck", .89, 1.0)):
        add(name, parent, (0, 0, lo), (0, 0, hi))
    angle = radians(arm_angle)
    for side, sign in (("Left", 1), ("Right", -1)):
        def arm(x, y=0, z=0):
            return (sign * (.095 + x * cos(angle) + z * sin(angle)),
                    y, .815 - x * sin(angle) + z * cos(angle))
        add(side + "Shoulder", "Spine2", (.025 * sign, 0, .805), arm(0))
        for name, parent, start, end in (("Arm", "Shoulder", 0, .18),
                                       ("ForeArm", "Arm", .18, .33),
                                       ("Hand", "ForeArm", .33, .395)):
            add(side + name, side + parent, arm(start), arm(end))
        for finger, y, length in (("Index", -.024, .058), ("Middle", -.008, .065),
                                  ("Ring", .009, .060), ("Pinky", .024, .047)):
            for i, (lo, hi) in enumerate(((0, .45), (.45, .75), (.75, 1)), 1):
                add(f"{side}Hand{finger}{i}", side + "Hand" if i == 1 else f"{side}Hand{finger}{i-1}",
                    arm(.391 + length * lo, y), arm(.391 + length * hi, y))
        for i, (lo, hi) in enumerate(((0, .45), (.45, .75), (.75, 1)), 1):
            add(f"{side}HandThumb{i}", side + "Hand" if i == 1 else f"{side}HandThumb{i-1}",
                arm(.347 + .045 * lo, -.021 - .047 * lo),
                arm(.347 + .045 * hi, -.021 - .047 * hi))
        add(side + "UpLeg", "Hips", (sign * .055, 0, .505), (sign * .056, -.008, .28))
        add(side + "Leg", side + "UpLeg", (sign * .056, -.008, .28), (sign * .056, 0, .055))
        add(side + "Foot", side + "Leg", (sign * .056, 0, .055), (sign * .056, -.070, .025))
        add(side + "ToeBase", side + "Foot", (sign * .056, -.070, .025), (sign * .056, -.115, .025))
        if eyes:
            add(side + "Eye", "Head", (sign * .018, -.036, .944), (sign * .018, -.055, .944))
    return joints

def resolve_mapping(bones):
    mapped, seen = [], set()
    for bone in bones:
        canonical = canonical_name(bone.name)
        if canonical not in HUMAN_MAPPING and canonical not in ("LeftEye", "RightEye", "Jaw"):
            continue
        if canonical in seen:
            raise ValueError(f"Ambiguous humanoid identity: {canonical}")
        seen.add(canonical)
        mapped.append({"bone": bone.name, "human": HUMAN_MAPPING.get(canonical, canonical)})
    return mapped

def create_armature(context, height=1.75, arm_angle=0, eyes=False, origin=(0, 0, 0)):
    import bpy
    from mathutils import Vector
    specs = template(height, arm_angle, eyes)
    if not all(isfinite(v) for v in origin):
        raise ValueError("Template origin must be finite")
    data = bpy.data.armatures.new("Rigmodo_Rig")
    obj = bpy.data.objects.new("Rigmodo_Rig", data)
    collection = bpy.data.collections.new("Rigmodo")
    context.scene.collection.children.link(collection)
    collection.objects.link(obj)
    for selected in context.selected_objects:
        selected.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    obj.location = origin
    obj.show_in_front = True
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        for joint in specs:
            bone = data.edit_bones.new(joint.name)
            bone.head, bone.tail = joint.head, joint.tail
            bone.parent = data.edit_bones.get(joint.parent) if joint.parent else None
            bone.use_connect = False
            bone.use_deform = joint.deform
            # Consistent facing direction, while each bone's Y axis follows its segment.
            bone.align_roll(Vector((0, -1, 0)))
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
    obj["lc_hierarchy_version"] = HIERARCHY_VERSION
    obj["lc_placement"] = "editable_template_not_ai"
    for bone in data.bones:
        bone["lc_semantic"] = HUMAN_MAPPING.get(bone.name, bone.name)
    return obj
