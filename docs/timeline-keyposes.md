# Kimodo from timeline keyframes

Pose the armature in Blender and insert normal pose-transform keyframes in its
active Action. Use **I** / Blender's keying sets for selected bones, or Auto Pose's
**Insert Pose Key** for a complete pose. In Rigmodo's Motion tab, enable **Use Key
Poses**, enter the motion description and generate. Edit, move and delete keys
in the Timeline or Dope Sheet. There is no separate capture/recall/remove list.

The clip begins at the scene Timeline's **Start** frame. Rigmodo's Length remains
the number of 30 fps model samples, mapped to the scene's FPS. The sidebar shows
the corresponding guide interval; keys outside it are ignored. Each pose-keyed
frame contributes the evaluated full-body pose, including interpolation on
partially keyed bones. Only the armature's assigned Action slot is read; keys
in another character's slot or on unrelated objects are not guides. Keep keys
sparse so Kimodo has time to generate movement between poses. Two guide frames
cannot map to the same model sample.

Bone rotations and Root/Hips translation are supported. Object transform
animation, pose scaling, other bone translations, drivers, active NLA and
constrained rigs need preparation first. Euler, quaternion and axis-angle
rotation channels are evaluated through Blender. Optional twist helpers are
derived from the animated forearms while sampling. Fingers and accessory channels
retain exact artist anchors and interpolate between them; Kimodo still predicts
body motion only. Contradictory poses or close contacts need artist review.

Sampling restores the current frame/subframe, complete working pose and rotation
modes, and does not change the Action or its keys. A job records the evaluated
guides, native key data, source Action/slot identity and the rest signature. Changed guide poses,
added/moved/deleted keys, a different Action/slot or FPS reject application before
allocating a result. Existing prepared jobs from the old snapshot workflow remain
compatible. Old stored snapshots are preserved for recovery through the legacy
API; new generation uses the native Action exclusively.

`tests/timeline_keyposes_acceptance.py` exercises real local Kimodo conditioning,
exact generated FK anchors, partial keys, three rotation modes, 24/30 fps,
subframes, multiple Action slots, source preservation, invalid-sample rollback,
stale edits and a private 6,598-vertex skinned avatar. Retarget-only cases use a
clearly identified cached motion result. Source and extracted-extension receipts,
UI checks and actual image-to-keyframe GUI validation are collected in
`timeline-keyposes-acceptance-2026-10-05.json`.
