# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit direct-bone Action export; source Actions and NLA are never edited."""
import json
import math
import re

_BONE_PATH = re.compile(r'^pose\.bones\[("(?:\\.|[^"\\])*")\]\.(location|rotation_quaternion|rotation_euler|rotation_axis_angle|scale)$')


def selected_action(rig, scene):
    data = rig.animation_data
    if data is None or data.action is None:
        raise ValueError("Assign the Action to export to the selected armature first")
    action, slot = data.action, data.action_slot
    if data.drivers or rig.constraints or any(b.constraints for b in rig.pose.bones):
        raise ValueError("Animation export needs a direct deform-bone Action without drivers or constraints. Bake the evaluated rig to a separate deform rig first")
    parent = rig.parent
    while parent:
        if parent.animation_data or parent.constraints:
            raise ValueError("Animated or constrained armature parents need baking before clip export")
        parent = parent.parent
    curves = []
    if action.is_action_layered:
        if slot is None:
            raise ValueError("The selected Action has no armature slot")
        for layer in action.layers:
            for strip in layer.strips:
                bag = strip.channelbag(slot, ensure=False)
                if bag: curves.extend(bag.fcurves)
    else:
        curves = list(action.fcurves)
    keyed = [curve for curve in curves if len(curve.keyframe_points) or len(curve.sampled_points)]
    if not keyed:
        raise ValueError("The selected Action slot has no keyed bone animation")
    for curve in keyed:
        match = _BONE_PATH.fullmatch(curve.data_path)
        if not match or json.loads(match[1]) not in rig.data.bones:
            raise ValueError(f"Unsupported Action channel: {curve.data_path}. Export supports direct bone transforms; object motion and custom properties need baking")
    # Action.frame_range spans all slots, including animation for other objects.
    # Respect an explicit artist range, otherwise use only the selected slot's keys.
    times = [p.co.x for curve in keyed for p in (*curve.keyframe_points, *curve.sampled_points)]
    start, end = (action.frame_start, action.frame_end) if action.use_frame_range else (min(times), max(times))
    if not all(math.isfinite(v) for v in (start, end)) or end <= start:
        raise ValueError("The Action needs a finite range spanning at least two frames")
    fps = scene.render.fps / scene.render.fps_base
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("The scene frame rate must be positive")
    return {"action": action, "slot": slot, "frame_start": math.floor(start),
            "frame_end": math.ceil(end), "fps": fps}


def attach_action(rig, selection):
    rig.data.pose_position = "POSE"
    for bone in rig.pose.bones:
        bone.matrix_basis.identity()
    data = rig.animation_data_create()
    data.action = selection["action"]
    if selection["slot"] is not None:
        data.action_slot = selection["slot"]
    data.use_nla = False
    data.action_blend_type = "REPLACE"
    data.action_influence = 1.0
