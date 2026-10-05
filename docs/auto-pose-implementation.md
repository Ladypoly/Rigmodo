# Rigmodo 0.10: procedural Auto Pose

5 October 2026. The research-only scope was superseded by the user's explicit request to start implementation. Auto Pose is now an opt-in posing tool for the standard Rigmodo humanoid, running on the CPU using Blender's bundled NumPy. It requires no model weights, additional provider, helper armature or cloud service.

## Using it

Enter Pose Mode using **Test Deformation** or **Motion → Edit Pose**. Press **Auto Pose** in the focused Rigmodo panel, select a body bone, then use **G** to move or **R** to rotate. The sidebar buttons invoke the same operators. The active bone supplies the target even if several bones are selected.

- Move is on the initial view plane. **X/Y/Z** constrains a global axis; repeat the key for the bone's initial local axis, repeat again to release it.
- Rotation uses the initial view normal or the chosen axis. Numeric movement is in meters, accounting for scene unit scale; numeric rotation is in degrees. Backspace edits the number. Shift makes subsequent mouse increments precise without jumping the existing displacement.
- Enter/LMB confirms; Esc/RMB cancels the **entire** pose. A confirmed gesture is one undo step and supports redo. Disabling the tool, changing frame/view/mode/rest data, losing focus, loading a file or unloading the extension invalidates the gesture and restores the initial channels.
- **Keep feet planted** holds both ankle positions and orientations, except the foot being actively manipulated. Blue viewport rings mark held joints.
- **Pin Joint** toggles explicit pins on hands, feet or pelvis. Under **Pose options**, hand/foot pins can hold position or position plus rotation. Pelvis pins hold the full frame. Explicit pins are never silently released; unpin a joint before manipulating it.
- **Body follows reach** allows the shoulders, spine and pelvis to contribute. Turn it off for local limb posing. **Joint limits** enables conservative swing/twist limits; enabling never clamps an already authored pose.
- An unattainable target displays **Reach limit · pins held**, with an orange line to the requested position. The actual armature remains attached and unscaled.
- **Insert Pose Key** keys every bone's location, current rotation representation and scale at the current frame, including helpers and fingers. It edits the assigned local, single-user Action or creates **Rigmodo Auto Pose**. Make at least two pose keys to export an animation.
- For Kimodo, insert ordinary pose keyframes after confirming the gesture and enable **Use Key Poses** in the Motion tab. The active Action's pose keys guide generation; no separate capture is needed.

When Auto Pose is off, G/R remain Blender's native transforms. Fingers, Root and unsupported non-body bones use native posing even while it is enabled. Use the keyboard or Rigmodo buttons for Auto Pose: native Blender transform gizmos do not invoke the solver.

## Implementation

Pins constrain each gesture, not the interpolation between ordinary animation keys. Review intermediate frames for foot sliding, or use Kimodo generation and its contact correction for the intervening motion.

`auto_pose_solver.py` builds a per-gesture indexed skeleton from actual rest matrices and the current authored local channels. The standard core supplies 22 rotational body joints plus permitted Hips translation; Root and non-body local transforms stay at their authored values. Parent offsets make the pelvis/hip sockets and chest/shoulder attachments exact. Every numerical iterate is already valid forward kinematics, rather than a disconnected particle proposal awaiting conversion.

The production path uses hierarchical damped least squares, an alternative identified in the research. Hard pin tasks occupy the primary Jacobian solution; the selected target is solved in its null space. Per-joint mobility biases changes toward limbs before the torso, and every mouse sample restarts from the same authored reference to prevent cumulative drift. Step sizes and iteration counts are bounded. A stable bend-plane seed escapes straight-arm shortening singularities; swing/twist projection supplies conservative angular bounds. Final actual FK position and orientation residuals gate pins. An infeasible proposal retains a feasible result rather than stretching bones.

This replaces the research's free-point relaxation prototype, whose medium target errors and FK attachment residuals were inadequate. It avoids adding free-particle constraints only to correct their offsets afterward. It is a procedural minimum-change approximation, not a learned human-pose prediction model or a physical balance simulation.

`auto_pose.py` owns a complete transaction: all location/scale/rotation representations and Euler winding are snapshotted, output is computed in memory, optional forearm twists are updated before one scene write, and cancel restores the original channels. Only its scoped G/R modal operators write poses; no depsgraph handler writes alongside native transforms. A short modal timer checks invalidation. File-load/undo/redo hooks and unregister remove session ownership; unregister also removes keymaps and the viewport overlay.

The existing rig, mesh, weights, accepted rest joints, materials, shape keys and animation data are not rebuilt by a gesture. Explicit pose-key insertion is a separate operation. No skinning provider, motion provider or Unity importer implementation was changed.

## Validation and remaining limits

Reproducible tests and compact measurements are in `auto-pose-acceptance-2026-10-05.json`:

- `tests/auto_pose_acceptance.py`: 36 scenarios across half/default/double stature with varied rest rolls; independent Blender FK evaluation, reachable targets, multiple position/frame pins, unreachable targets, bone lengths/scales/translations, complete channel restoration, rotation targets, authored finger poses, optional twist helpers, key insertion and unsafe-rig rejection.
- `tests/auto_pose_interaction_acceptance.py`: separate GUI Blender driven through its real keymap and documented event queue; G/R confirm/cancel, undo/redo, numeric axis entry, sidebar invocation, disabled-tool native G and timer cancellation after disabling during a gesture. This is not a physical-mouse or full native-transform-parity test.
- `tests/auto_pose_avatar_acceptance.py`: 60 varied wrist updates on the private 6,598-vertex, 53-bone skinned avatar; source Action preservation, full cancel restoration, finite deformation, Kimodo capture and direct whole-pose animation exports for Humanoid and Generic. Private renders were inspected. Timing includes solve, all bone writes, dependency evaluation and skinned vertex reads; it excludes viewport drawing.
- Existing UI/landmark and Kimodo-keyframe controls regressions pass. Extracted-package and Unity results are recorded separately in the compact acceptance/release evidence.

Ordinary tested targets converge much more accurately than the research prototypes. Sideways pelvis and arbitrary knee-head displacements can remain limited because exact rigid offsets, pinned feet and limb lengths constrain their reachable sets. The initial Unity probe found 7.8 mm of stationary Humanoid root drift: new authored Actions lacked the existing explicit Root-export marker. Pose-key insertion now marks the Action so the existing companion creates the corrected editable clip, including zero-travel motion; both profiles pass with zero unintended Root travel. The old fixed 73-frame reference also needed a configurable short-clip sampling interval, but changing the interval alone did not fix the drift. Failed observations are retained in acceptance evidence.

Initial support requires the complete standard Rigmodo parent hierarchy, unit pose scales, zero non-Root/Hips pose translations, normal inheritance, a local rig, and uniform positive object scale. Constraints, drivers, Blender Auto IK/X mirror, rendering, playback and Auto Keying are rejected with an explanation. Pose-key insertion additionally requires a local editable single-user Action without active NLA tracks. The UI deliberately offers explicit key insertion instead of silently modifying source animation during a drag.

Conservative swing/twist limits and bend seeding do not constitute a complete anatomical model. Robust hinge-sign enforcement across arbitrary imported rest frames, self-collision, balance, contact surfaces, shared Actions/NLA editing, automatic keying, native gizmos, snapping, trackball, continuous rotation winding and complete Blender transform-input parity remain future work. A 30/60 Hz viewport guarantee is not inferred from CPU timings. Existing Unity Humanoid retargeting tolerances apply; Generic is the direct skeletal/surface fidelity path.

## Commands

Run every test in a separate factory-startup process. Private fixture/output paths are arguments, never distributed assets:

```powershell
blender --background --factory-startup --python tests/auto_pose_acceptance.py -- OUTPUT
blender --factory-startup --enable-event-simulate --python tests/auto_pose_interaction_acceptance.py -- OUTPUT
blender --background --factory-startup --python tests/auto_pose_avatar_acceptance.py -- PRIVATE_BLEND OUTPUT
python tests/run_motion_unity.py PRIVATE_EXPORT_ROOT
```

The earlier [research and 30-part plan](auto-pose-research-and-plan.md) and its failed prototypes remain historical evidence, rather than descriptions of the shipped solver.
