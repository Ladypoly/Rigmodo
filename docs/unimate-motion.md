# Creature Motion · UniMate

Rigmodo 0.15.0 adds local text animation for an existing creature deform rig. It does not replace or rerun joint placement or skinning. Humanoids keep their Kimodo workflow and timeline key poses.

## Use

1. Open Extension Settings → Setup → **Creature Motion · UniMate** and press **Install Creature Motion**. The existing MIA Python 3.11/CUDA runtime must be installed. Setup creates a separate inference venv, shares MIA's Torch through a `.pth` file, and downloads about 2.18 GB of new model/text-encoder files. It does not duplicate CUDA Torch or download the 88 GB dataset. Source, model revisions and SHA-256 hashes are pinned in `unimate-lock.json`. No Hugging Face token is required.
2. Choose **Creature**, then **Motion**, and select the rig. Its visible bound meshes are included; an explicit mesh selection narrows the scope.
3. Enter a short English training-style prompt: `An object walks forward.`, `An object attacks forward.`, or `An object moves its tail.` Select 15–60 frames at 30 fps, optionally **In place**, then **Generate Motion**.
4. Review the new character copy and its Action. **Preview Motion** sets playback bounds. The original rig, mesh data, weights and Action remain intact. Source hiding follows the existing preference. No source is purged.
5. Under **Motion options**, correct world-space facing (+X, −X, +Y, −Y). Joint labels are per-bone anatomical descriptions; empty labels use cleaned bone names. This is particularly relevant to generic `Creature_###` bones. Labels and facing persist with the rig. The selected Scorpion faces +X. These settings condition motion; they do not move joints.

Setup needs internet. Generation runs in an isolated worker with Hugging Face offline mode, local T5 encoding and no cloud calls. Shared processing feedback and Cancel/Escape own the worker process tree. Interrupted complete outputs can be applied under Preferences → Recovery while the original Blender process and captured source still exist.

## Skeleton and Action mapping

Single connected, local, unconstrained deform hierarchies are accepted, including imported custom rigs. Positive uniform object scale and rotation are supported. Nonuniform/mirrored/sheared rig transforms, animation drivers, active NLA and unusual inheritance are rejected with a correction message. Rest data is sampled regardless of the current pose.

An unweighted structural root with one child is excluded from model conditioning and remains in the Blender hierarchy. Virtual terminal tips allow leaf rotations without adding Blender bones. The 71-joint budget includes those tips; oversized rigs are rejected rather than silently losing joints. Anatomical joints are not renamed. Model topology, normalized rest positions, clean labels and a local English caption form the condition. No remote LLM annotates it.

The pinned upstream EMA model and flow sampler generate one 60-frame window; shorter requests crop it. UniMate's child-slot parent rotation encoding is recovered through FK, conjugated out of the canonical frame, and converted to Blender pose bases using each bone's own rest orientation. Only the anatomical root translates; bone lengths and skin weights stay fixed. Generated sample times map to the scene FPS without changing it. Generic FBX export bakes at the scene FPS.

Request/output seals, finite shape and rotation checks, source object identity, skeleton/label/skin fingerprint and source Action keys are checked before allocating copies. Failed application removes its owned output. Changed source geometry, weights, joints, labels, Action, scene units or FPS require a new request. Camera navigation and timeline scrubbing do not alter the rest input.

## Limits and evidence

This is an early released motion model, not an insect locomotion solver. Prompt following, contact, sliding, collision avoidance and anatomy can fail. Numbered or mislabeled bones and incorrect facing reduce reliability. The Scorpion's existing imperfect UniRig tail still needs joint correction; text motion cannot repair that rest skeleton. It may need manual Action/skin cleanup.

This integration provides single-prompt short clips. UniMate keyframe in-betweening, long-window expansion, selective motion editing and automatic creature foot IK are not exposed. Kimodo's human-only key-pose toggle is not shown for creatures. No claims of universal automatic bone semantics are made.

Actual RTX 4090 test: the 51-deform-bone Scorpion (52 Blender bones including Root; 64 model joints including virtual tips) generated 60 frames in 12.96 s, with 466,751,488 bytes of peak Torch allocation. This excludes Blender and CUDA driver/context memory. An unlabelled real GUI run also completed. Cancellation left no new objects or draw handlers. Source rig/mesh/Action and humanoid MIA/landmark UI checks passed. Neural FK → Blender joint error was 1.52e-7 m; exported/reimported FBX animation error at scene sample frames was 4.55e-7 m. Unity Editor import was not repeated. See the dated acceptance receipt.

## Licenses

UniMate source and the Blender reference adapter are MIT; Rigmodo is GPL-3.0-or-later. The separately downloaded released UniMate weights are **CC BY-NC 4.0**, appropriate to this project's private noncommercial use. FLAN-T5 is Apache-2.0. Setup retains upstream licenses and the model card. Nothing in the extension relicenses those weights. No training dataset is required or redistributed.

Sources: [UniMate](https://github.com/Friedrich-M/UniMate), [released model/license](https://huggingface.co/Linzhan/UniMate), [Blender reference](https://github.com/nopeburger/UniMate-B3D).
