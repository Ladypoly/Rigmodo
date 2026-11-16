# Mocap and retargeting research review — 2026-11-16

Reviewed `Rigmodo_Video_Mocap_Retargeting_Research_2026-11-16.md` against the installed Rigmodo working branch and the upstream projects' published documentation/licenses. This is a review and recommended sequence, not a claim that video providers have been installed or benchmarked.

## Decision

Keep the proposed separation between motion-first and video-first workflows. When Kimodo already supplies 3D motion, retain it as the source; a generated video is useful visual reference, but reconstructing the known motion from those pixels introduces unnecessary ambiguity.

Build on the existing isolated jobs, direct-bone Actions, source preservation, and export conventions. Add focused mapping/contact stages before introducing another orchestration framework. The new local library and retargeter provide a practical trusted-3D input for testing those stages.

## Corrections to the current-state audit

The research inspected an older main-branch state. The working extension has three workflow tabs, **Rig / Skin / Motion**; export is in preferences. UniMate creature animation, creature facing/joint annotation, MotionBricks, the scene Action manager, one-shot playback, and the shared model folder already exist. The local library now adds native Asset Browser browsing, batch import, and a basic humanoid retargeter. These should be integration points, not reimplemented features.

That retargeter transfers recognized humanoid roles, calibrates arm rest poses, scales root movement, and preserves target bone lengths. It does not solve anonymous skeleton semantics, arbitrary spine differences, unreliable capture, foot sliding, or hand-object contact. Do not describe it as the research's generic automatic retargeter.

## Recommended implementation order

1. **Rig mapping and a visible calibration review.** Start with name/profile mapping, then hierarchy, rest geometry, side and forward evidence. Report confidence and require correction when ambiguous. Twists, helper bones, missing fingers, multiple roots, mirrored rigs, A/T poses, and different spine chains need explicit policies. [Rig Bridge](https://github.com/qw424886884/rig-bridge) is a useful GPL reference; structural inference is not proof that every role is correct.
2. **Contact QA and correction on trusted 3D clips.** Measure foot speed during planted intervals, penetration, joint-limit violations, root discontinuities, and artist-key drift. Compare the existing two-bone solver with a small temporal/contact pass. [BVH Motion Retargeter](https://github.com/BacteriaJun/BVH-Motion-Retargeter) is MIT, but its documented contacts are manually confirmed; it is not an automatic contact detector. [Toyxyz's retargeter](https://github.com/toyxyz/toyxyz-blender-retargeter) is another proportion-aware reference. Avoid promising physical simulation or automatic palm support from those tools.
3. **One lightweight video-capture vertical slice.** Import a video, choose a subject/range, retain timestamps and detection confidence, preview on the existing rig, then bake a new Action. [MediaToPose](https://github.com/KitsuMate/MediaToPose) offers a practical MediaPipe/SAM-style route. Start with one person and a reasonably static camera; occluded depth, root travel, fingers, and motion blur remain uncertain. Track identity and failure intervals explicitly.
4. **Benchmark GEM-X as a second provider.** Its [official documentation](https://github.com/NVlabs/GEM-X) distinguishes temporal body-motion inference from hand pose inference with optional tracking/smoothing. Native SOMA77 needs an adapter; code, geometry, weights, and dependencies have separate license considerations. Use an isolated runtime rather than upgrading Rigmodo's existing provider environment in place.
5. **Optional research providers and creatures last.** [ExMR's license](https://github.com/twehrbein/ExMR/blob/main/LICENSE) limits use to educational/research/nonprofit purposes. [FlowHMR](https://github.com/flowhmr/flowhmr) reports a specific physical-trackability metric; it is not a universal motion-accuracy result, and its simulation stack is a substantial Linux dependency. Benchmark capture and simulation separately before promising native Windows support. Generic creature recovery is still experimental, even if the input skeleton is supplied.

## Data contract and acceptance criteria

Extend the library's arbitrary-skeleton sampled-motion format with explicit units, handedness, axes, root/world/camera spaces, timestamps, per-joint confidence, contact probabilities, subject identity, and source/license provenance. Keep original provider outputs so normalization can be corrected without rerunning inference. Avoid forcing hands or arbitrary rigs through the current SOMA30 body format.

Test short clips covering straight walking, turns, stairs, seated motion, hand contact, occlusion, camera motion, different limb proportions, twist bones, and incomplete rigs. Compare source/target contacts and preserve artist constraints. Measure actual wall time, peak GPU and system memory, installation footprint, and cancellation on this Windows machine; the 16 GB tier needs its own test. Retain export round trips and scene-preservation checks. Mark unresolvable intervals instead of silently smoothing them into convincing but wrong motion.

For generated footage, temporal plausibility does not guarantee a physically consistent 3D skeleton. Multiple people, camera cuts, interacting props, severe self-occlusion, and nonhuman anatomy should be declared outside the first release's supported path.

## License point that remains relevant to private use

The published [MiniMax H3 Community License](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) excludes the EU from its defined applicable territory and invites separate authorization. Private use alone does not resolve that territorial restriction. Keep video generation model-agnostic and check the exact selected checkpoint's terms. No H3 provider was installed during this work.

The recommendation is to start with mapping and measurable contact correction, then a single local capture provider. Full provider quality, VRAM use, authenticated services, and heavy simulation pipelines were not tested as part of this review.
