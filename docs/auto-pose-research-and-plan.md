# Rigmodo Auto Pose: technical investigation and implementation plan

5 October 2026. Research against Rigmodo 0.9.0, commit `b9c7d21`, Blender 5.2.0 LTS build `fbe6228777e7`, Windows, Intel Core i9-13900K. **No production Auto Pose feature has been implemented or registered.** The running extension, avatar, provider installations and release version remain unchanged. All interactive experiments ran in separate factory-startup Blender processes; numerical experiments ran in background processes. No AI inference was used.

**Recommendation:** use an internal semantic skeleton with rigid pelvis/chest frames, weighted position relaxation, analytic limb projection and exact forward kinematics. Give an opt-in Rigmodo modal operator ownership of G/R gestures. Write rotations and permitted Root/Hips channels back to the existing rig. Do not attach a permanent helper armature or make a depsgraph handler the owner of a native drag.

The architecture is sufficiently specified to start staged implementation. The research prototypes are deliberately incomplete: their medium-reach target accuracy is inadequate for shipping, anatomical angular limits are not implemented, and the full viewport frame-rate target is unmeasured. These are explicit implementation gates below, not hidden assumptions.

Reproducible scripts: [native interaction](../tests/auto_pose_research/native_transform_lab.py), [solver comparison](../tests/auto_pose_research/solver_lab.py), [Rigmodo adapter and timing](../tests/auto_pose_research/rig_adapter_lab.py). Compact measurements and failed approaches are in [research results](auto-pose-research-results-2026-10-05.json). Detailed event traces and private avatar fixtures remain outside Git.

## 1. What a procedural approximation can provide

The useful target is pin-and-drag full-body IK: resolve positions/orientations against a known articulation graph, preserve lengths and attachments, preserve user pins, and minimize unnecessary changes from the pose at invocation. This can provide wrist → elbow → shoulder → spine → pelvis participation without learning. It cannot infer intended gesture, emotional posture, balance strategy or a natural human pose from sparse handles as a learned prior can.

Cascadeur describes its relaxation as interaction between connected rigid bodies with minimal position/orientation changes; its AutoPosing predicts poses from manipulated controllers. Rigmodo should implement its own procedural relaxation and should not promise an equivalent prediction system. [Cascadeur relaxation](https://cascadeur.com/help/animation_pipeline/spline/relaxation_in_cascadeur), [AutoPosing](https://cascadeur.com/help/tools/animation_tools/autoposing).

Use the **current authored pose**, not the bind pose, as the per-gesture reference. Bind geometry supplies invariant lengths, offsets and coordinate frames. This distinction prevents enabling Auto Pose from straightening an artist's existing pose.

## 2. Blender API and source findings

`PoseBone.matrix_basis` describes editable local channels relative to parent/rest; `PoseBone.matrix` describes the evaluated armature-space pose after constraints/drivers. Native transforms modify channel storage, then tag dependencies for evaluation. A read immediately after a write can be stale until evaluation occurs. [PoseBone API](https://docs.blender.org/api/5.2/bpy.types.PoseBone.html).

Source inspection found `TransData` holding pose-channel location/rotation/scale pointers and initial channel copies. `transformEnd()` restores the transform's own data on cancel and performs final update/autokey work. This explains the observed untracked-neighbor cancellation failure. Source snapshot: `e4bea5df73c1fc1c253d63edbc01ba4c2c64843d`; this is **not asserted to be the installed binary's source revision**. Installed behavior is established separately by experiments. [Pose conversion source](https://github.com/blender/blender/blob/e4bea5df73c1fc1c253d63edbc01ba4c2c64843d/source/blender/editors/transform/transform_convert_armature.cc), [transform lifecycle source](https://github.com/blender/blender/blob/e4bea5df73c1fc1c253d63edbc01ba4c2c64843d/source/blender/editors/transform/transform.cc).

`Window.modal_operators` exposes running operator instances. It establishes that translate/rotate is active, not a guaranteed per-bone ownership list or a public completion-result callback. Snapshot active bone **and selected/eligible bones at invocation**. A changed parent can change an unselected child's evaluated matrix; matrix change alone does not identify a manipulated bone. [Window API](https://docs.blender.org/api/5.2/bpy.types.Window.html).

Message bus subscriptions did not report native viewport edits in the read-only case; subscriptions did report the experiment's explicit RNA writes. Documentation also excludes viewport transforms and warns about callback undo ownership. Use msgbus for settings/invalidation notifications, not the continuous solve loop. [Message bus](https://docs.blender.org/api/5.2/bpy.msgbus.html).

`depsgraph_update_post` can observe evaluated updates. It is not a transaction or gesture event API. Avoid writes inside it in production; mark a session dirty and solve through the owned modal operator. Blender's handler warning about rendering and viewport threads is specifically a reason to stop posing during rendering, not evidence that every depsgraph callback is necessarily on another thread. [Handlers](https://docs.blender.org/api/5.2/bpy.app.handlers.html).

The installed 5.2 build uses `PoseBone.select`; the older `Bone.select` assumption failed in the harness. Active-bone access remains `rig.data.bones.active`. Version-specific selection access belongs in one tested adapter.

## 3. Results of the ten requested transform experiments

Input was queued through documented `Window.event_simulate` in a GUI Blender launched with `--enable-event-simulate`. These were real native keymap G/R and native modal operators, not `EXEC_DEFAULT` transforms or a reimplementation. Each native drag had five mouse updates and six distinct active matrices including its initial state. This is controlled GUI input, **not a physical-mouse/gizmo test or a measured 60 Hz drag**.

| Requested test | Observed result | Consequence |
| --- | --- | --- |
| 1. Detect manipulated bone during G | Active `LeftHand` and selected scope were readable while `TRANSFORM_OT_translate` was present. The multi-selection case exposed two selected bones. | Reliable in this controlled single-rig scope; snapshot selection, do not treat active bone as the complete native transform set. |
| 2. Read changing matrix during transform | Six distinct active matrices were observed before completion, for translation and rotation. Read-only msgbus count: zero. | Continuous observation is possible through evaluation/timer sampling. |
| 3. Modify other pose bones | A post-update handler wrote unselected `RightArm` rotation once; it affected the evaluated pose while G/R remained modal. Writing `LeftForeArm` also affected its child hand. | Technically possible; parenting feedback matters. |
| 4. Does the next native update overwrite it? | Unselected-neighbor write survived all subsequent updates. When `RightArm` was selected too, seven writes were needed as native rotation repeatedly rewrote owned channels. | Never rely on arbitrary concurrent writes to native transform-owned channels. |
| 5. Recursive update loops | Cases recorded 10–13 handler calls including completion/undo/redo and maximum synchronous handler depth one. Writes occurred only on a meaningful change; no `view_layer.update()` was called inside the handler. | This limited test avoids recursion; it does not prove a complex solver cannot create repeated later updates or semantic feedback. |
| 6. Undo | For confirmed native G/R, one Undo restored all tested bone bases and Redo restored the result. On native cancel, the active bone restored but the addon neighbor remained changed. | Confirmed undo worked in the isolated case; cancel is unsafe without full-pose transaction ownership. |
| 7. Start/update/confirm/cancel | Running-operator presence detected start/end. A pass-through observer saw G/R press and **only the release** of Enter/Esc, because the native transform consumed the press. | There is no complete robust public lifecycle hook here. End-of-operator disappearance alone cannot distinguish confirmed zero movement from cancellation. |
| 8. G versus R | Both supported live reads and retained an unselected write; both had the same cancellation failure. Native G left a hand translation channel; R changed orientation. | A translation must be treated as intent, then converted to feasible rotations; do not leave displaced hand channels behind. |
| 9. Interactive rates / 20–30 joints | A 29-point solve, 53-bone adapter, analytic foot projection, writes and one bare-armature dependency update measured **5.16 ms median / 5.74 ms p95** over 100 CPU samples. | Computational headroom exists; this is not viewport FPS or dense-avatar acceptance. See §21. |
| 10. Constraints on affected bones | With a local X Limit Rotation set to zero, a neighbor basis accepted X=0.4, while its evaluated orientation remained effectively constrained to its prior orientation. | Reading/writing basis does not defeat the constraint stack; unsupported constraints must be rejected or handled by an explicit control adapter. |

Additional transaction probe: an isolated custom G/R modal changed active and neighboring channels, stored every initial bone basis, restored all of them on Esc and returned `CANCELLED`. Both move and rotate cancellations restored the full pose. Confirmations undo/redid exactly in one step. Cancel produced no new gesture undo step; a subsequent Undo reached the preceding setup operation. This probe is **not** a full transform implementation or full-body solver.

Harness mistakes were fixed before acceptance: constraint collections require removing individual entries, selection moved to PoseBone in this build, mouse-motion events require `NOTHING`, and object-scale evaluation requires an update before inspecting world scale. They are retained in evidence to prevent future sessions from repeating them.

## 4. Native G/R integration feasibility

**Observation is feasible; unrestricted handler-driven mutation during native transforms is not the recommended production architecture.** The experiments disprove the blanket claim that Blender always overwrites other bones. They also demonstrate why surviving writes alone are insufficient: cancellation, selected-channel ownership, parent feedback, auto-key ownership and exact commit timing remain problems.

A watcher could theoretically snapshot everything before a native transform, suppress writes to owned channels, and restore on detected cancellation. The current public observations cannot reliably prove all completion paths, especially zero-delta confirm, alternate keymaps, gizmos, focus changes or macros. That approach remains experimental unless a separate lifecycle proof covers those paths.

No private C++ `TransInfo` memory access, monkey-patching Blender internals or operator-identifier polling as a substitute for transaction ownership. Preserve native G/R when Auto Pose is off.

## 5. Recommended interaction architecture

When Auto Pose is on and a supported rig/body bone is active in Pose Mode, optional addon keymap entries invoke `local_character.auto_pose_move` / `local_character.auto_pose_rotate`. Their `poll` must be tightly scoped. Each operator owns one full-pose gesture and its cancel/commit.

MVP move: frozen view plane through the selected pivot, X/Y/Z axis constraints, repeated axis for local orientation, numeric input, Shift precision, Enter/LMB confirm, Esc/RMB cancel. Rotation: signed screen-plane rotation and explicit global/local axes around the selected bone's initial pivot. Defer Blender's complete snapping/trackball/individual-origin/proportional-edit/continuous-wrap equivalence; unsupported combinations must be explained, not silently behave differently.

Use Blender's view conversion utilities to form rays and projected axes. Avoid pixel-to-meter constants used in the ownership probe. For near-parallel ray/axis cases use a stable projected-axis fallback or request a different view. Freeze the orientation/pivot at invocation and evaluate intent from the initial mouse/pose so the body cannot chase its own output.

One modal operator reads events, solves in memory, validates the actual FK result and writes once. Coalesce mouse events if needed; do not create a second forever-running writer. A future GizmoGroup should invoke the **same** transaction engine. Native gizmo drags are outside the first shipping scope.

No added rig objects for ordinary use. Mode exit, disabling, file load, undo, rig deletion and unregister must clean up timers, handlers, header/status text and keymaps. Capture Pose must wait until a gesture ends.

## 6. Recommended solver algorithm

Use a **hybrid procedural constraint solver**: weighted PBD-style positional/orientation proposals on a semantic graph, rigid pelvis/chest frame projections, analytic two-bone arms/legs, joint-limit projection, and exact FK reconstruction inside the iterative loop. A final FK residual check is mandatory.

| Representation option | Assessment |
| --- | --- |
| A. Solve directly on PoseBones | Appropriate as an input/output adapter; repeated RNA writes/evaluations during numerical iterations make ordering, constraint ownership and performance harder. |
| B. Internal simplified skeleton | Recommended. Explicit semantics, rigid frames and constraints are testable independently, with one staged output to the existing rig. |
| C. Hidden solver armature | Unnecessary for the default rig; adds object duplication, constraint/dependency cycles, undo lifecycle and baking/export scope. Consider only for a future explicit control-rig adapter. |
| D. Combination | B for numerical state plus A for snapshot/write boundaries; existing analytic IK and twist conversion remain reusable. |

It is a static pose optimizer: no gravity, inertia, physical timestep, training data or neural model. Artistic mobility/stiffness is not body mass. Hard structure is represented kinematically; compliance applies to target/preferences, not permission to stretch exported bones.

Investigate XPBD-style compliance for soft constraints after the feasible geometry path is established. With a fixed solver time parameter, `alpha_tilde = compliance / h²`, the accumulated multiplier improves consistency of softness across iteration budgets. Reset/transport multipliers deliberately when a target changes; do not use real mouse-event spacing as a physical timestep. No XPBD prototype was benchmarked here, so exact invariance for our proposed pose problem is not claimed. [XPBD paper](https://matthias-research.github.io/pages/publications/XPBD.pdf).

For the positional subproblem, test `delta_lambda = (-C - alpha_tilde * lambda) / (sum(w_i * |grad_i C|²) + alpha_tilde)` and `delta_x_i = w_i * grad_i C * delta_lambda`. Keep `h` fixed in normalized units and choose posture/target compliance independently. Orientation projection needs its own calibrated rotational constraint formulation; substituting Euler channel changes into this positional equation is not justified. Exact FK still owns the bone/attachment invariants.

## 7. Comparison with alternatives and measured solver behavior

| Technique | Useful role | Reason for recommendation |
| --- | --- | --- |
| FABRIK | Fast local chains; feasible limb seed and constrained-chain alternatives | Good positional chain solver. Multi-effector/shared-junction arbitration and rigid attachments must be implemented explicitly. It is not inherently incapable of full-body work. |
| PBD / relaxation | Shared pins, region resistance and progressive participation | Fits one graph of heterogeneous relationships. Needs exact FK/rigid frames and objective-aware convergence; bare point distance constraints are insufficient. |
| XPBD | Iteration-aware soft posture/target penalties | Worth testing once geometry is valid; no simulation layer is necessary for posing. |
| CCD | Simple local angular correction | Cheap, but serial effector priority and bend/twist bias complicate symmetric multi-pin behavior. Keep as a possible local fallback. |
| Jacobian transpose / pseudoinverse | General weighted angular IK | Pure pseudoinverse is poorly conditioned near straight limbs. |
| Damped least squares / hierarchical IK | Angular refinement, preserving hard-pin task priority | A credible alternative if the hybrid fails accuracy gates. More involved task/limit handling and CPU matrix work; not benchmarked here. |
| Native IK / iTaSC | Existing Blender capabilities to compare against | Not our assumed solution. Auto IK follows connected chains; Rigmodo's template marks bones disconnected. It does not define our reach-dependent body policy or gesture ownership. |

PBD exposes general projection constraints and weighted distance correction. [Original PBD](https://matthias-research.github.io/pages/publications/posBasedDyn.pdf). FABRIK's constrained extensions include humanoids, multiple chains and model restrictions; our small sequential baseline is not the complete algorithm from those papers. [Author's FABRIK page](https://andreasaristidou.com/FABRIK), [constrained FABRIK](https://andreasaristidou.com/publications/papers/Extending_FABRIK_with_Model_C%CE%BFnstraints.pdf). DLS is a viable way to handle singular and unreachable targets, with damping and task limits requiring care. [Buss's IK analysis](https://math.ucsd.edu/~sbuss/ResearchWeb/ikmethods/iksurvey.pdf). [Blender Auto IK](https://docs.blender.org/manual/en/latest/animation/armatures/posing/tool_settings.html).

Both original research prototypes used the same 29 landmarks from Rigmodo's parametric skeleton, 48 main iterations, known pole directions, and twelve scenarios. Relaxation also used 48 final feasibility sweeps; therefore its timings are **not an equal-iteration paper benchmark**. The FABRIK-style baseline lacked rigid-junction arbitration and left cross-branch attachments inconsistent. It was faster (roughly 0.4–1.2 ms versus 2.5–2.8 ms), but those outputs are not publishable Rigmodo poses.

| Case | Bare relaxation result | Decision |
| --- | --- | --- |
| Small wrist move | Target error ~0.000416 character heights, chest movement ~0.000310 heights; pins exact in point space | Local behavior is promising. |
| Larger wrist reach | Chest movement ~0.0667 heights; target error ~0.0690 heights | Body follow appears, but accuracy is inadequate. |
| Pelvis down / knee bend | Knees react; point pins exact; requested pelvis travel only partially achieved | Test target priority and pose preference in the feasible rotation space. |
| Sideways pelvis / one pinned foot | Shared body changes; pin exact in point space | FK projection is essential; naive reconstruction slipped a pinned foot by up to ~7 cm. |
| Pinned hand / feet + hand | Shared constraints remain finite | Test angular reach and rigid body attachments, not only node pin error. |
| Extreme arm reach | Large pelvis/chest follow, but ~21.7% maximum relative bar error before reconstruction | Never publish this bare proposal. |
| Extreme leg / pinned pelvis | Requested reach cannot be satisfied | Preserve pins and lengths; clamp/report active target. |
| Active target also pinned | Target residual remains, pin stays in place | Define explicit pin priority and require an unpin action. |

Forward/reverse ordering changed residuals; symmetric sweeps improved the tested multi-pin case's target error from ~0.0252 to ~0.0185 heights. Halving/doubling character size gave effectively identical normalized outcomes. Arm-length factors 0.65 and 1.4 remained finite with zero point-pin error; this does not establish anatomical quality across stylized rigs.

Making the active target nearly immovable improved the medium target error from ~0.0690 to ~0.00845 heights **while worsening maximum bar error from ~1.34% to ~20.0%**. Increasing a target weight is not a substitute for a valid kinematic model.

The additional exact-FK/analytic projection prototype preserved every actual bone length within about 1.8e-7 m and retained the tested pins within roughly 5.1e-7 m across all twelve cases, using a full-frame pelvis pin. Medium reach still missed the active target by **0.121 m**; pelvis-down missed by ~0.055 m. These are failed target-quality gates. The recommendation is the tested hybrid architecture, **not those final parameter choices**. Put projection inside the objective loop and use target continuation; if it cannot meet gates, compare constrained multi-effector FABRIK and hierarchical DLS before building polished interaction.

## 8. Solver data model

Use compact indexed arrays for solve-time state; semantic dataclasses describe topology once. Avoid bpy references in the numerical loop.

```python
JointSpec(index, semantic, bone_name, parent_index, children,
          rest_position, reference_position, region, mobility,
          preferred_bend_frame, limit_profile)
BoneBinding(bone_name, parent_name, rest_matrix, rest_inverse,
            length, parent_attachment, inherit_scale, use_local_location)
RigidFrameSpec(semantic, members, local_offsets, rest_frame)
Pin(id, joint_or_frame, position_world, orientation_world,
    position_enabled, orientation_enabled, hardness, rest_signature)
SolveState(positions, orientations, frame_poses, local_rotations,
           hips_translation, multipliers, last_valid, residuals)
GestureSnapshot(all_basis, rotation_modes, selection, active_bone,
                frame, action_identity, action_slot, rest_signature,
                object_world, pins, preferred_pose)
Target(joint_or_frame, requested_position, requested_orientation,
       handle_local_offset, pivot, gesture_kind)
SolveReport(target_error, pin_errors, attachment_error, length_error,
            limit_violation, iterations, time_ms, saturated, valid)
```

Immutable topology and mutable pose are separate. World anchors are transformed into normalized armature space at the gesture boundary. Stable names/rig identity identify data; Python ID references are reacquired after undo/load. A rest hash prevents applying a pose to a rebuilt skeleton.

## 9. Exact body/joint representation

The initial internal positional graph has **29 landmarks**. The production state additionally stores orientations of the major frames/bones; 29 is a point count, not the total number of degrees of freedom.

| Landmarks | Count | Rigmodo binding |
| --- | --- | --- |
| Hips, Spine, Spine1, Spine2, Neck, Head heads | 6 | Direct semantic body pivots |
| Head terminal point | 1 | Head tail |
| Per side: Shoulder, Arm, ForeArm, Hand heads | 8 | Clavicle origin, upper-arm origin, elbow, wrist |
| Per side: hand terminal point | 2 | Hand tail / orientation direction |
| Per side: UpLeg, Leg, Foot, ToeBase heads | 8 | Hip socket, knee, ankle, toe pivot |
| Per side: toe terminal point | 2 | ToeBase tail |
| Pelvis and upper-chest forward markers | 2 | Virtual orientation markers; no Blender bones |

`Root` is a structural parent/gauge, not a movable relaxation particle. Body travel generated by posing goes to Hips for the initial feature; Root remains unchanged. Root transformation with active world pins is rejected in the MVP with guidance to unpin/leave Auto Pose. Fingers, eyes, jaw, sockets and twists preserve local authored channels and follow their parents.

Pelvis rigid frame: Hips pivot, Spine attachment, both UpLeg heads and a forward marker. Chest rigid frame: Spine2 pivot, Neck attachment, both Shoulder origins and a forward marker. **Read actual parent-local offsets from the rest matrices**; do not assume coincident heads/tails or the template's proportions. Their frame orientation is represented explicitly, not inferred solely from a bone's Y direction.

Spine/neck/head lengths and limb lengths are actual bone lengths. Validate elbow/knee chains' end-to-next-head correspondence; imported gaps above the declared normalized tolerance need a generalized offset-chain adapter or a clear rejection. Do not force-connect bones, edit rest joints or rewrite hierarchy.

## 10. Pinning system and conflicts

Pins capture the current evaluated pose in world coordinates, not bind pose or frame zero. Feet default to full-frame ankle pins (position + foot orientation); hands default to position pins with orientation optional. Pelvis pin defaults to a full frame in the first implementation; position-only pelvis pin requires an extra rotational-feasibility test. A full-frame ankle pin preserves the foot/toe placement without requiring a floor collision solver.

Hard priorities: fixed rig structure, explicit transform locks and valid hard pins; feasible joint limits; active target; soft posture preferences. An unreachable active request must leave residual error. Do not finish by snapping the active node after lengths/limits/pins, which would invalidate the pose again.

Reject contradictory hard pins before publishing. A pinned selected handle does not silently lose its pin: report it and offer explicit unpin. For new conflicts, retain the previous valid pose and report which relationships prevent movement. Initially support one active target plus feet/hands/pelvis pins. Optional elbow/knee/head point pins need branch/limit feasibility tests before enabling arbitrary pinning.

Persist only intentional pin records. Snapshot pins for a gesture; pin changes cannot arrive halfway through it. Rest edits invalidate pins; object/frame changes require a clear reanchor/re-evaluation policy. Disabling Auto Pose removes active solve state but should not erase stored user pins unless requested.

## 11. Influence propagation

Combine logical graph distance, semantic region, normalized target displacement, reach deficit and joint mobility. Graph distance alone cannot distinguish a slight wrist adjustment from an unreachable arm target. Use the semantic articulation graph for distance, not all dense rigid-cluster bars from the research prototype.

First solve the manipulated limb with its parent frame held. Normalize its unsatisfied target error by limb reach. Use a smooth activation band to release clavicle, chest, spine and pelvis resistance progressively. Initial tunable bands might begin around 80–90% of limb reach; these are **implementation starting values, not validated defaults**. Blend the deficit signal with invocation-relative target displacement and the user Body/Spine/Shoulder Follow settings.

Measure pressure against a frozen invocation reference, with bounded feedback from the last valid pose. Otherwise a moving shoulder changes its own release threshold and can cause stick-slip oscillation. Warm-start numerical state, but never replace the preferred-pose reference with each mouse update's output. Use hysteresis near participation boundaries.

All translation tolerances and requests are normalized by measured character extent/limb lengths. Angular limits use radians. Do not introduce absolute meter thresholds for short/tall or short/long-armed characters.

## 12. Preferred bend directions

Capture elbow/knee planes from the invocation pose when bent enough to be numerically stable. When nearly straight, derive a semantic plane using body facing and the measured shoulder/hip axis; allow artist pole overrides later. Transport this frame with torso/pelvis orientation, rather than keeping a fixed world vector during turning.

Use analytic two-bone projection to choose the correct branch of the elbow/knee circle. Enforce a signed plane/pole relationship as a medium preference, not a hard world-space location. Near full extension use the last valid plane; if degenerate, use the calibrated semantic frame, then a deterministic least-aligned axis fallback. Avoid flips at straightness and mirroring by testing handedness explicitly.

The prototypes used fixed known arm/knee poles for controlled comparisons. They do not prove general pole-frame extraction or arbitrary rest-roll hinge calibration.

## 13. Joint limits

Use semantic hinge limits for elbow/knee flexion, ball-joint swing cones plus axial twist ranges for shoulders/hips, and distributed swing/twist ranges for spine/neck. Define limits in calibrated semantic frames transported by the parent. Bone roll makes arbitrary local Euler-X clamping incorrect.

Clamp orientation, then recompute exact FK and revisit pins/targets. Limits participate during the solve; applying them only after convergence can unplant feet or lose wrist targets. Keep optional softer comfort limits inside strong mechanical bounds. Imported IK limit checkboxes may inform a profile only after axis-space interpretation is validated; they are not a universal anatomy specification.

No universal anatomical numeric defaults were validated here. The MVP requires editable, conservative humanoid profiles and a non-anatomical/stylized profile. Locked rotation axes are additional hard user constraints. Twist ambiguity near 180° requires quaternion sign continuity and a defined fallback.

## 14. Spine

Preserve the three spine bones and their parent attachments. Distribute torso swing/twist over Spine, Spine1 and Spine2 using length-weighted bounded increments and the user Spine Follow setting. The pelvis/chest frame proposals determine overall bend; minimize deviations from the authored curvature instead of straightening to bind pose.

Keep the chest attachment frame rigid so the two shoulders and neck cannot drift independently. Re-evaluate pelvis/limbs after spine projection. Permit forward lean, sideways lean and axial twist, but prevent accumulating all motion in one short vertebra. Head stabilization and hand pulls are soft competing goals, not unrestricted chest translations.

## 15. Pelvis

Hips is the only free body translation channel in the initial solver; Root is fixed. Pelvis orientation is an explicit frame, needed to preserve the two hip sockets and spine attachment. Minimize its translation/tilt for local edits and release it under arm reach pressure.

For pinned feet, pelvis movement must satisfy both leg reach volumes before analytic leg projection. Downward movement bends knees; horizontal movement usually requires both translation and tilt, within limits. The reach-sphere prototype demonstrates feasibility without limits; production must also consider minimum reach, knee limits and rotated hip attachments.

A pinned pelvis frame remains unchanged. The initial prototype mistakenly moved a position-pinned pelvis by 0.07089 m in the extreme-leg case; its corrected full-frame semantics eliminated that violation. Position-only pelvis pinning is a separate feature, not an implicit weakening of a hard pin.

No center-of-mass or support-polygon guarantee in the MVP. Planting feet does not establish physical balance.

## 16. Shoulder and clavicle

Keep Shoulder bones in the solver. Chest frame owns their origins; Shoulder rotations control the Arm origins through the existing clavicle lengths/rest offsets. This lets the clavicle participate before large spine/pelvis motion.

Use low clavicle mobility for slight reachable wrist changes and greater mobility for near-limit reaches. Bound clavicle swing/elevation and preserve the authored shoulder rest tendency. Do not allow separate Shoulder-head translations to emulate scapular motion; that would violate the current rig and motion-capture contract. A future scapular model can remain internal if it converts to supported rotations.

## 17. Conversion back to the existing Rigmodo armature

Solve in normalized armature space. Convert world targets with `rig.matrix_world.inverted()` once at the input boundary; unnormalize before assembling pose matrices. Uniform world scale/rotation/translation round-tripped within 1.8e-7 m in the adapter test. Reject mirrored, singular, sheared or nonuniform object/parent/bone scale in the MVP. Keep the existing unparented-rig contract until parenting has dedicated tests.

Process parents before children. For each bone compute its inherited pose from cached parent pose and actual rest matrices. Choose solved orientation; derive the head from the parent's unchanged attachment except for allowed Hips translation. Never freely assign every particle position as a PoseBone head. Build the full matrix map in memory, including untouched finger/module inheritance, then convert all results to basis matrices.

```python
basis = bone.convert_local_to_pose(
    desired_pose, bone.matrix_local,
    parent_matrix=solved_parent_pose,
    parent_matrix_local=bone.parent.matrix_local,
    invert=True,
)
# Keep scale exactly unit; non-Root/Hips local translation exactly zero.
```

`convert_local_to_pose` supports caller-provided matrices, avoiding a dependency evaluation for each bone. [Bone conversion API](https://docs.blender.org/api/3.2/bpy.types.Bone.html). Rigmodo already follows this pattern in `motion_apply.py` and `twists.update_matrices`; reuse its coordinate conventions.

The rolled-rest neutral-pose round-trip maximum matrix-element error was 1.02e-6. Naive free-head reconstruction required up to 0.132 m of non-Root/Hips translation on the extreme arm case; clearing those channels after the solve slipped pins. This is why exact FK must be part of the iteration, not merely export cleanup.

Validate every final pin against the **reconstructed** matrices, not just solver particles. Stage all basis values before touching bpy. Write once only if the candidate passes structure/limits/pin checks; otherwise publish the last valid state and a target saturation report.

## 18. Bone roll and twist

Blender's bone Y axis follows its length; rest X/Z depend on roll. Align the reference pose's Y direction to the solved direction with minimal swing, preserving its axial orientation. Do not use an arbitrary `track_quat` up axis that resets roll.

For explicit rotational targets or twist limits, decompose relative orientation into swing and twist around the calibrated bone axis. Preserve invocation twist when only position is manipulated; explicit R changes orientation and may distribute bounded pronation through the forearm. Preserve quaternion sign continuity.

The adapter test changed rest rolls, retained a 0.6-radian forearm twist and applied a 0.4-radian orthogonal swing; quaternion orientation error measured zero at float precision. This verifies that case, not all 180°/parallel-axis transitions.

Optional forearm helpers remain outside the position graph. Apply `twists.update_matrices(rig, poses)` to the completed matrix map before conversion/writes, respecting its source/fraction metadata. Preserve fingers, sockets and facial local bases.

## 19. Existing constraints, controls, animation and Rigmodo contracts

Current Rigmodo rigs are direct deform rigs: 52 deform bones plus unweighted Root, known semantic names/properties, optional twist leaves. `motion_jobs.validate_rig` and export already reject arbitrary constraints/drivers and nonuniform transforms. Auto Pose should use a Pose-Mode-compatible validator with the same structural policy; do not call the current Object-Mode-only validator unchanged.

MVP supports these rigs with no active bone/object constraints, drivers, Auto IK or X mirror. Reject unsupported states with preparation guidance, without removing constraints or rewriting artist controls. An IK/FK control rig later requires a registered explicit adapter identifying writable controls and evaluated deform relationships; it is not achieved by modifying arbitrary deform bones under existing IK constraints. A hidden helper armature adds dependency, bake and export problems and is unnecessary for the default path.

An assigned Action may supply the initial evaluated pose, but no timeline advancement/playback is permitted during a gesture. Changing animation evaluation can overwrite live channel edits. MVP requires auto-key off; do not turn it off silently. Keying/Capture Pose occurs after confirm. Later auto-key support must insert **all changed body channels**, not just the selected handle, in the same undo transaction and respect Action slots/keying policies/shared-Action ownership.

`motion_keyframes.validate_basis` currently permits translations only on Root/Hips. Auto Pose must honor this, preserving the current Kimodo capture/generation path. G on a hand is a target request, never a persisted hand translation. Rest joints, skin weights, morphs, hierarchy, object identity, Action data and frame remain unchanged unless an explicit keying operation is requested.

## 20. Undo and cancellation strategy

One `UNDO` modal owns each gesture. Snapshot all bone bases/modes plus context, Action identity and topology before the first write. On Esc/RMB, restore every modified channel, remove transient resources, redraw and return `CANCELLED`. On confirm, validate/publish the final candidate and return `FINISHED`, creating one undo step. Never push undo per mouse movement or write a late solve from a handler after the operator finishes.

The custom ownership probe confirms exact cancellation and one-step confirmed Undo/Redo in this Blender build. It does not validate auto-key, NLA, custom keying sets, F9 repeat or shared Actions. Those remain gates. Undo/load can invalidate bpy references; cancel/invalidate sessions and reacquire names/IDs afterwards. [Operator undo behavior](https://docs.blender.org/api/5.2/bpy.types.Operator.html).

Persist replayable target/pose properties if supporting F9; do not rely on an ephemeral Python snapshot surviving operator repeat. Do not overwrite unrelated user operations during cleanup. On external frame changes, end the gesture and let the current Action re-evaluate at the new frame rather than restoring the old timeline. Rendering, file loading or mode change should terminate through a tested cleanup path.

## 21. Performance strategy and measured limits

Bare-armature prototype: 29-point relaxation ~2.74 ms median; reconstruction + analytic hard pins + 53-bone writes ~2.13 ms; one dependency update ~0.25 ms; total **5.16 ms median / 5.74 ms p95**, 100 samples on i9-13900K. CPU math only, no GPU compute or model memory.

A separate private 6,598-vertex avatar test measured graph solving + direct body-channel writes + evaluated skinned geometry at **3.21 ms median / 3.45 ms p95**, 100 samples. This excludes the full adapter/pin projection and viewport draw, so it is not comparable as a faster full pipeline. It tests dependency/skin evaluation cost, not fitting quality on that avatar. The Blender window's G/R tests were sparse simulated mouse events, not a 60 Hz performance test.

Production target: solve + adapter + evaluated geometry p95 below 12–16 ms on the declared reference character, leaving drawing time in a 16.7–33.3 ms frame budget. Measure actual event-to-visible-update latency before claiming stable 30/60 Hz. Dense meshes, subdivision, modifier stacks and materials can dominate, independently of joint count.

Cache hierarchy, rest matrices/inverses, constraint arrays and semantic index maps. No per-event `children_recursive`, mesh scans, JSON hashing, RNA collection searches or allocations inside projection sweeps. Use bundled mathutils/NumPy where helpful; no SciPy/install step or worker that touches bpy. One dependency evaluation per published candidate, no per-bone evaluations. No edit-mode changes or constraint additions during drag.

Warm-start numerical state and coalesce queued target changes; process the latest target within a bounded timer/event budget. Idle sessions perform no solve. Never reduce iterations without checking hard residuals. Faster low-quality preview may retain larger **active target** error, not stretch bones or move pins.

## 22. Failure cases and technical risks

| Risk | Required behavior |
| --- | --- |
| Conflicting pins / impossible reach / incompatible limits | Clamp target or retain last valid pose; name residuals. Never relax a hard pin silently. |
| Straight limbs / antiparallel directions / mirrored poles | Stable cached semantic bend frame and deterministic branch selection. |
| Point-space feasible, FK-space invalid | Reconstruct every iteration; validate actual attachments and pins. |
| Soft preferences overpower useful target | Target-quality gates and objective-aware continuation; the prototype's 12 cm medium miss must be fixed before integration. |
| Bone/object scale or shear / incorrect imported offsets | Reject unsupported input; no automatic rest edits. |
| Animation/driver/constraint overwrites | Refuse unsupported state; explicit control adapters later. |
| Handler recursion or self-chasing input | Modal transaction owns writes; frozen intent/reference, changed-value guards and bounded feedback. |
| Undo/load/object deletion invalidates RNA | Cleanup/reacquire, no stale pointers. |
| Dense mesh drawing stalls | Measure event latency; optional user-selected viewport simplification later. |
| Learned-pose expectation / balance / self-collision | Explain procedural limits; do not promise natural/physical pose synthesis. |
| Rest edits, rerigging or another Rigmodo worker during posing | Block worker launch in an active gesture and invalidate signatures after edits. |

The prototypes prove interaction ownership, coordinate transport and feasible pin cleanup. They do **not** prove complete anatomical posing, orientation-pin conflicts, polished native transform parity, arbitrarily constrained rigs or frame-rate acceptance.

## 23. MVP scope

One Rigmodo humanoid, upright calibrated semantics, unit bone scale, positive uniform object scale, unparented and unconstrained. Direct existing bones in Pose Mode; one active body handle; supported G/R interaction; full-frame feet and pelvis pins, optional wrist-position pins. Rotation-only results plus Hips translation, unchanged Root/rest/hierarchy/mesh/weights. Preserve current fingers/facial channels and existing optional twists.

Body/Spine/Shoulder Follow can be simple eventual settings, but defaults are not selected until target-quality tests pass. Keep runtime/state code independent of UI. No production panel edits in this research branch. Unmapped minor bones should retain ordinary posing outside the scoped Auto Pose gesture; their edits invalidate/rebase the next invocation snapshot as necessary.

MVP excludes native gizmo piggybacking, arbitrary multi-selected transform semantics, Auto IK/X mirror, all Blender snapping modes, auto-key, constraints/control rigs, physical balance, collisions, foot-floor contact generation and pose synthesis. Pose authoring followed by the existing **Capture Pose → Kimodo** workflow remains the first integration target.

## 24. Later improvements

Explicit per-joint position/orientation pins; position-only pelvis pin; multiple active handles; hierarchical task priorities; XPBD softness calibration; a constrained multi-effector FABRIK or DLS comparison if needed; stronger joint-limit profiles; contact/foot-roll models; capsule self-collision; support-polygon/COM preference; artist pole/gaze controls; customized proportions and mechanical profiles; AutoKey/NLA/F9; common control-rig adapters; gesture-owning gizmos and more transform parity.

Physical plausibility and stylistic pose preferences should remain separate optional policies. None requires AI; none is implied by a successful basic PBD solve.

## 25. Proposed production files and existing integration points

Do **not** add these runtime modules until the staged implementation is authorized.

| File | Responsibility |
| --- | --- |
| `auto_pose_model.py` | Semantic resolver, immutable topology, normalized frames, pins, signatures and validation |
| `auto_pose_solver.py` | Pure numerical constraints, solve state, feasibility/quality reports; no bpy imports |
| `auto_pose_adapter.py` | Snapshot evaluated pose, exact FK/rest-offset conversion, final basis staging and twist integration |
| `auto_pose_interaction.py` | Scoped keymap, modal G/R, gesture transaction, cleanup and optional future gizmo integration |
| `tests/auto_pose_acceptance.py` | Background geometry/matrix/contract acceptance |
| `tests/auto_pose_interaction_acceptance.py` | GUI event/undo/Action/gizmo tests |

Reuse `skeleton.resolve_mapping` / canonical identities, `kinematics.two_bone`, `twists.update_matrices`, and motion/export channel policy. `__init__.py` later registers settings/classes and cleanup; `ui.py` later adds a compact Pose-Mode control; `motion_keyframes.py` shares the completed-pose validity guard. Do not add native providers, checkpoint dependencies or another asynchronous AI job type. Original research scripts remain under `tests/auto_pose_research/`, already excluded from release packaging.

## 26. Proposed classes and functions

```python
SemanticSkeleton.from_rig(rig)       # metadata, topology, offset/scale checks
PoseSnapshot.capture(context, rig)   # all channels, frame/Action/identity
PinSet.capture(frame_or_joint, pose)
PinSet.validate(signature)
PoseAdapter.to_solver(snapshot)
PoseAdapter.to_basis(candidate)      # full matrix map, exact offsets
PoseAdapter.validate_fk(candidate, pins, limits)
PoseAdapter.publish(staged_basis)
InfluencePolicy.weights(reference, request, limb_residual, follow_settings)
ConstraintSolver.solve(request, state, budget)
ConstraintSolver.project_rigid_frames(...)
ConstraintSolver.project_limbs_and_limits(...)
ConstraintSolver.project_hard_pins(...)
GestureTransaction.restore()
GestureTransaction.commit()
AutoPoseMove.invoke/modal/cancel/execute
AutoPoseRotate.invoke/modal/cancel/execute
invalidate_sessions(reason)
register_keymaps() / unregister_keymaps()
```

Separate `SolveReport.valid_geometry` from `SolveReport.target_satisfied`. An impossible request can have valid geometry and a deliberately saturated target. A medium reachable request missing by 12 cm is a target-quality failure and must not be relabeled acceptable merely because pins pass.

## 27. Main solver pseudocode

```python
def solve(reference, previous_valid, requested_target, pins, budget):
    validate_reference_and_hard_pin_set()
    state = warm_start(previous_valid)
    local_trial = solve_manipulated_limb(reference, requested_target)
    weights = influence_from_reach_error(reference, local_trial, settings)
    target = continuation_step(previous_valid.target, requested_target)

    for iteration in bounded_iterations(budget):
        propose_active_position_and_orientation(state, target, weights)
        relax_soft_authored_pose_preferences(state, reference, weights)
        project_rigid_pelvis_and_chest_frames(state)
        project_bilateral_lengths_and_attachments_symmetric(state)
        project_preferred_bend_and_joint_limits(state)
        project_spine_and_clavicle_orientation(state)

        # This is part of solving, not just a final output conversion.
        fk = reconstruct_exact_rotation_only_pose(state)
        project_hard_pins_and_feasible_limb_reach(fk, pins, limits)
        state = feed_reconstructed_fk_back_into_state(fk)
        report = measure_actual_fk_residuals(fk, pins, target, limits)

        if report.valid_geometry:
            remember_feasible_candidate(fk, report)
        if report.valid_geometry and report.target_satisfied:
            break
        if stagnating_or_conflicting(report):
            reduce_continuation_step_or_stop()

    best = best_valid_candidate_or(previous_valid)
    update_optional_twist_matrices(best)
    assert verify_actual_fk_and_channel_contract(best)
    return best, residual_report_for_requested_target(best)
```

Pins and rigid structures are enforced through constrained degrees of freedom/projection, not repeated unconditional particle snaps after an incompatible solve. Symmetric sweeps are the initial ordering; compare fixed symmetric Gauss–Seidel with residual-driven ordering and prioritize hard constraints before soft preferences. Test convergence under changing iteration/time budgets before choosing defaults.

## 28. Blender interaction/update pseudocode

```python
def invoke(context, event):
    validate_supported_rig_pose_mode_and_idle_state()
    snapshot = capture_full_transaction()
    model = cached_topology_for(snapshot.rest_signature)
    input_state = frozen_view_pivot_and_mouse_reference(event, snapshot)
    previous_valid = snapshot.pose
    add_modal_handler_and_owned_timer_if_needed()
    return RUNNING_MODAL

def modal(context, event):
    if external_context_or_topology_changed():
        cleanup_without_overwriting_new_external_state()
        return CANCELLED
    if cancel_event(event):
        restore_entire_transaction(snapshot)
        cleanup()
        return CANCELLED
    if transform_input(event):
        requested = intent_from_initial_input(input_state, event)
        candidate, report = solve(model, previous_valid, requested, pins, budget)
        basis = stage_all_basis_and_twists(candidate)
        if validate_actual_fk_and_contract(basis):
            publish_changed_channels_once(basis)
            previous_valid = candidate
            redraw_view_and_show_residual_if_saturated(report)
        return RUNNING_MODAL
    if confirm_event(event):
        finish_final_bounded_solve_and_validate()
        # MVP: no automatic Action edits. Later key all changed channels here.
        cleanup()
        return FINISHED
    return RUNNING_MODAL
```

Use normalized geometric ray/plane/axis input, not the probe's fixed pixel scaling. No `view_layer.update()` inside a depsgraph callback. A read-only handler can invalidate cache/mark input dirty; the modal owns all writes and includes final twist channels in the same undo transaction.

## 29. Staged implementation roadmap

1. **Pure model and conversion foundation.** Extract actual Rigmodo rest offsets/frames and validate semantics. Establish neutral/rolled-rest/world-transform round-trips, exact FK lengths and zero non-Root/Hips translations. Keep the runtime UI untouched.
2. **Geometry-first solver.** Rigid pelvis/chest, arms/legs, exact pins and feasible target continuation. Put FK/pin projection inside every iteration. Fix the recorded medium hand/pelvis target misses. Compare a constrained multi-effector FABRIK or hierarchical DLS implementation if the hybrid fails acceptance. This is the first go/no-go gate.
3. **Limits and body policy.** Semantic bend frames, joint limits, spine/clavicle distribution, normalized progressive follow and head stabilization. Add current-pose rather than bind-pose preferences. Test short/tall and stylized rigs.
4. **Owned interaction.** Scoped opt-in G/R modal with snapshots, geometry-based mouse input, axes/numeric entry and exact cancel/undo. No handler-driven native writes. Verify confirm/cancel/Undo/Redo with actual OS mouse input as well as event simulation.
5. **Rigmodo integration.** Tiny Auto Pose entry in the existing Pose workflow, preferences for defaults, completed-pose capture, twist helpers and safe worker/export exclusion. Add no new armature/mesh objects. Test captured pose through existing motion/export.
6. **Quality and performance.** Avatar articulation review, pin residuals under repeated drags, true event-to-visible latency with mesh/modifier costs, teardown/unregister/load/multi-window tests. Only after this gate consider a production version bump/package.
7. **Optional expansion.** AutoKey/Action slots, gizmos, richer transform parity, control adapters and additional pin/physical policies, each with separate tests.

Research is committed separately from production releases; keep the runtime 0.9.0 package unchanged. The next session can start step 1 using these scripts/measurements, without repeating native-handler feasibility work. It must not interpret a research `passed` flag as satisfying Auto Pose's target-quality gates.

## 30. Concrete stability tests and acceptance gates

| Area | Required cases and gate |
| --- | --- |
| Semantic model | All core names/prefixes; ambiguous identity; Root gauge; optional eyes/jaw/sockets/twists; rest edit invalidation; zero lengths; disconnected offsets; unsupported control rig rejected. |
| Matrix contract | Neutral/posed/rest-roll round-trips; mirrored limbs; quaternion sign; near-180° swing; unit/uniform scale and world transform; nonuniform/shear/negative scale rejected; no rest/hierarchy/weight/mesh changes. |
| Lengths/attachments | Actual FK length error ≤ `1e-5 * height` with tighter relative checks on short links; unchanged parent-local attachments; non-Root/Hips translations and all scales exact within agreed float tolerance. |
| Pins | Two feet, one foot, hand, feet + hand, full pelvis, repeated pin/unpin, active pinned handle, contradicting pins, unreachable leg/arm. Hard position residual ≤ `1e-4 * height`, orientation ≤ 0.1° on the reference test set. Validate reconstructed pose, not particles. |
| Targets | Reachable small/medium hand/pelvis targets ≤ `1e-3 * height`; low nonlocal motion for small edits; increasing follow for large edits; impossible requests saturate without stretching/pin drift/oscillation. Recorded 0.121 m medium miss must fail this gate. |
| Bend and limits | Straight/fully bent elbow/knee, mirrored poles, crossings, overreach, pelvis tilt, asymmetric proportions, joint-lock combinations; no flips or strong-limit violations. |
| Body | Spine distribution, clavicle release, pelvis socket rigidity, head stabilization; current authored pose preserved on enable/no-op; no accumulating drift over 1,000 gestures. |
| Interaction | G/R with mouse, axis/local axis, numeric/negative input, Shift precision, confirm/cancel via all supported keys; zero-delta confirm vs cancel; modifiers and alternate keymaps; supported gizmos later. |
| Undo and lifecycle | One-step full-pose Undo/Redo on confirm; exact full restore and no gesture undo on cancel; F9 only if implemented; toggle, mode exit, rig delete, file load, undo while idle, unregister/reload, focus/multi-window; no stale references/handlers/keymaps. |
| Existing animation | Action/slot/NLA data unchanged with auto-key off; timeline change abort; Capture Pose after Auto Pose passes existing channel restrictions; twist helpers correct. AutoKey-on behavior explicitly rejected until its all-channel/slot/keying-set tests exist. |
| Constraints and settings | Active constraint/driver/Auto IK/mirror rejected or explicitly adapted; no silent removal; PoseBone location/rotation locks preserved; renderer/playback and concurrent Rigmodo jobs blocked. |
| Performance | Small and ≥100k-vertex characters, subdivision, multiple meshes, shape keys, materials; 1,000 input updates; p95 solver+adapter+evaluation ≤ declared 12–16 ms budget; measured ≥30 Hz event-to-visible response on reference hardware, report GPU drawing separately. |
| Unity/motion | Captured procedural pose through existing Kimodo key-pose path and Humanoid/Generic export; Root/Hips policy, original bind/weights/Action intact; no helper objects or unsupported transforms in export. |

Re-run the research probes with the commands below before relying on a different Blender build. Geometry/undo failures must be retained as failures, not hidden by snapping pins, weakening tolerance or keying only the visible handle.

```powershell
# From the Rigmodo source directory; outputs go outside the repository.
$labOut = Join-Path $env:LOCALAPPDATA 'Temp\rigmodo-auto-pose-research'
$blenderExe = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
& $blenderExe --factory-startup --enable-event-simulate --python tests/auto_pose_research/native_transform_lab.py -- "$labOut/native"
& $blenderExe --factory-startup --enable-event-simulate --python tests/auto_pose_research/native_transform_lab.py -- "$labOut/custom" custom
& $blenderExe --background --factory-startup --python-exit-code 1 --python tests/auto_pose_research/solver_lab.py -- "$labOut/solver"
& $blenderExe --background --factory-startup --python-exit-code 1 --python tests/auto_pose_research/rig_adapter_lab.py -- "$labOut/adapter"
# Optional final argument to adapter lab: a private .blend with one bound rig.
```

Research outputs are observations and original prototype code. No external algorithm implementation was copied; upstream Blender source was read separately and kept outside this repo. The optional private avatar is a dependency-evaluation fixture and is not distributed.
