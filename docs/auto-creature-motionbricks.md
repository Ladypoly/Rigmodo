# Automatic creature motion and humanoid MotionBricks · 0.16.0

## Creatures

Generate Motion now infers anatomical labels before preparing a UniMate request. It uses bone-name semantics, parent/child chains, bilateral branch pairs and rest-space geometry. Numeric suffixes, L/R conventions, object rotation and curled tail chains are handled. The rest skeleton, original bone names, skin weights and Action are retained. Labels are metadata.

**Facing direction → Automatic** is the default for new rigs and uses a continuous horizontal vector, including rigs rotated between cardinal axes. Existing explicit facing choices remain overrides. **Detect Facing & Joints** re-runs detection and selects Automatic. Independently authored labels take priority; previous automatic labels refresh when the rig changes. Notes under Motion options call out generic/unclassified labels. A radially symmetric or otherwise ambiguous facing stops generation and asks for an explicit direction. This is conservative inference, not a universal semantic model: wings, fins, tentacles and unusual skeletons can need corrected labels. No additional AI weight download is required.

Fresh original Tripo Scorpion: all 44 Blender bones were labelled from unnamed rest data, +X facing inferred, and actual UniMate generated 60 frames in 18.12 seconds on an RTX 4090. The 56 model joints include virtual tips. Manual per-bone labels, source geometry, joints, weights and Action are preserved. Named rotated-rig and ambiguous radial cases also pass. Source legacy direction enum values keep their old meanings; Automatic is appended rather than inserted.

## Humanoid Method → Key poses · MotionBricks

1. Install **Humanoid Key Poses · MotionBricks** in Preferences → Setup. The provider shares the existing MIA CUDA libraries and adds ONNX Runtime in its own venv.
2. Select an accepted Mixamo-style deform armature. In a sparse guide Action, insert at least two ordinary bone pose keys, 0.5–2 seconds apart. Multiple guides chain into a sequence of up to 30 seconds. Root/Hips translations are supported; other bones use rotations with unit scale.
3. Choose **Motion → Method → Key poses · MotionBricks**, then **Generate Motion**. No prompt is consumed. Key times set duration automatically; the model's short transitions are retimed to those intervals.
4. Review the new editable character/Action copy. Original guide Actions and source paint remain on the original character. Return to that sparse guide Action to revise poses; a generated, densely sampled Action is not a sparse guide Action.

The released SOMA-30 FP32 ONNX model is pinned by revision/size/SHA-256. Context/target features use the documented hips-derived heading, +X alignment, root constraints and position/6D rotation layout. Each transition trims three boundary frames at either end, applies the official-style local endpoint residual correction, restores world placement, and retimes by SLERP. Four recent generated poses condition the next transition. The shared human retargeter and timeline overlay preserve exact artist anchors, fingers and optional modules. Hands have no newly synthesized finger articulation. Existing contact/heading options still apply; physical contacts and collision-free motion are not guaranteed.

This is pose-driven offline authoring. It does not install the Newton viewer, TensorRT, a locomotion controller, Smart Primitive editors or sample clips. MotionBricks' released models are SOMA humans and the G1 robot, so this integration is humanoid-only; creatures retain UniMate. Kimodo text generation and its Use Key Poses toggle remain available. The Preferences-only complete workflow continues to use Kimodo for its text-motion stage.

Actual tests: two transitions / three anchors / 61 samples at 30 fps, scene FPS 24, in 2.89 seconds on RTX 4090. A complete private Ready Player Me character preserves artist anchors within 2.39e-7 matrix error and exports character/animation FBX. Real modal generation, armature-only scope and worker cancellation leave no source changes or overlay handlers. Request tampering is rejected before scene allocation. Unity Editor import was not repeated.

## Editable loops

**Motion options → Make Loop Copy / Blend Loop Endpoint** creates a separate Action, retains the unlooped Action with a fake user, and closes body rotations/locations. The seam matches both endpoint poses and the incoming/outgoing one-frame angular and linear velocities. The correction blends toward the starting pose's tangent. In-place clips close their root, including weighted Tripo roots. Traveling structural root displacement stays available for locomotion; it is not a closed world-space path.

The synthetic seam check and an actual auto-labelled Tripo animation pass (world joint seam error 2.98e-8 m). A mathematically continuous seam does not establish a convincing gait: phase, foot sliding, contacts, collisions and motion intent still require review. Choose a suitable cycle and blend width; an arbitrary attack or landing is not automatically a natural repeating motion.

Sources: [MotionBricks](https://github.com/NVlabs/motionbricks), [SOMA model contract](https://github.com/NVlabs/motionbricks/blob/main/docs/soma_model.md), [ONNX inference](https://github.com/NVlabs/motionbricks/blob/main/docs/onnx_inference.md), [UniMate](https://github.com/Friedrich-M/UniMate).

Authored loop Actions can set `lc_loop_period_frames`. Preview excludes the duplicate endpoint so playback does not pause for one frame at the seam; the complete Action range remains available for FBX export. Ordinary Actions retain their original preview range.
