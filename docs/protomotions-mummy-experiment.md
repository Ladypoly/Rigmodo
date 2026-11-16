# ProtoMotions / MuJoCo mummy experiment

On 2026-11-16, the pretrained anatomical SOMA tracker completed the full mummy capture in local CPU MuJoCo. The result does **not** meet Rigmodo’s integration gate: preserve the acting detail and provide a useful improvement on the target character. No production control was added. Rigmodo remains at 0.21.0.

## What ran

ProtoMotions revision `13de0cccd06f53ce5c9cf9ec7d1932c7da73610f`, anatomical SOMA FSQ checkpoint SHA-256 `c13e56e85494f8c93fe9eed5b07cadef7281c2eb1188231755f858e1d0f340f0`, Python 3.11.9, CPU PyTorch 2.8.0 and MuJoCo 3.17.0. Weights and complete licensing sidecars live under `R:\AI\Models\Rigmodo\protomotions\anatomic_soma_bones_fsq`. The 114,675,901-byte checkpoint was verified against its pinned Git LFS pointer and published provenance. Upstream’s model-license checker passed.

The Windows launcher needed a single-device Lightning strategy and eager PyTorch execution instead of distributed Gloo and Inductor compilation. These changes affect execution, not physics or the policy. The source checkout and trained weights were not patched. Separate CPU environments hold the simulator and the upstream PyRoki/JAX retargeter.

The bundled ten-clip baseline completed with 100% evaluation success and 4.45 cm mean body-position error, reproducing the upstream mini-pack result. This is tracking error, not capture accuracy or a guarantee for arbitrary avatars.

## Mummy pipeline and controls

The input was the original corrected capture `Mummy Staff`, before MotionBricks. A copy was sampled to SOMA pose deltas, fitted to anatomical SOMA’s hinge joints using the upstream whole-clip solver, tracked in MuJoCo, then retargeted to the original mummy skeleton. Dense source finger channels were retained. The 240-sample, 30 Hz motion ran uninterrupted: zero fall/tracking terminations, no resets and no external root forces. Physics ran at 960 Hz. The runner’s setup and rollout timer measured 4.53 seconds; first-time installation, import and reference fitting are additional costs. The first 94-iteration whole-clip fit took about 41.5 seconds, including compilation in that solver timer.

A no-physics transport round trip had under 0.01 mm maximum body-position error. Anatomical fitting alone changed hand positions by at most 1.7 cm left and 1.2 cm right. Thus the much larger strike changes are not explained by the transport code. Native Blender playback and all 193 displayed frames were checked. Mesh, rest joints, skin weights, staff object placement and the external working source list were preserved.

## Results

| Measurement | Original capture | Physics raw | Physics + Rigmodo contacts |
| --- | ---: | ---: | ---: |
| Maximum stationary sole error on the evaluated mummy | 1.19 mm | 24.90 mm | 1.36 mm |
| Mean absolute stationary sole error | 0.306 mm | 7.580 mm | 0.155 mm |
| Upper-body rotation third-difference RMS | 0.00404 | 0.00581 | 0.00581 |

The rotation statistic is an unnormalized high-frequency matrix-change proxy, not a perceptual jitter score. It gives no evidence of a smoother target result here. Hand positions differ from the original by up to 26.9 cm left and 30.9 cm right during the fast strike around 5.3 seconds. Visual comparison shows a noticeable change to the strike’s timing and staff trajectory.

On the **canonical simulated proxy**, maximum self-penetration fell from 29.10 mm to 2.70 mm, and frames exceeding 5 mm fell from 21 to zero. These are compliant contact depths, not a zero-intersection guarantee. Maximum simulated floor penetration was 7.42 mm. This result cannot be transferred directly into a claim about the mummy’s render mesh.

The target-mesh check found zero cross-region surface intersections in both original and refined clips for torso/forearm, torso/hand and opposing thighs. A deliberately intersecting forearm produced 32 triangle pairs, validating the check’s positive control. This check excludes rest overlaps and two-ring neighbors and does not detect complete containment or every body-region pair. It demonstrates no target-mesh collision improvement on this fixture.

## Decision and retained artifacts

Keep this as a research comparison rather than exposing a known fidelity regression as a one-click upgrade. A useful production pass still needs stronger motion/hand-contact preservation, character-aware geometry and validation after retargeting. Staff dynamics and two-hand constraints were not part of this humanoid-body test. No other policy was substituted and no training was run.

The live scene contains the original `Mummy Staff`, the existing MotionBricks variant and a separate `Mummy Staff · Physics test`. The original is selected. Hidden raw physics data remains available for review. The scene still has three objects and one loaded external source motion.

All model inputs, outputs, logs, pinned runtime lists and the nine experiment scripts are retained in `R:\AI\Rigmodo\Jobs\Acceptance\Mummy-ProtoMotions`. Open `Mummy-Physics-Comparison.blend` there to compare Actions. The scripts record the exact local experiment, not a supported portable provider installer. Public Git history includes only this note and the compact [measured record](protomotions-mummy-experiment-2026-11-16.json); private avatars, media, checkpoints and runtime binaries are excluded.

Upstream references: [model card](https://github.com/NVlabs/ProtoMotions/blob/13de0cccd06f53ce5c9cf9ec7d1932c7da73610f/data/pretrained_models/motion_tracker/anatomic_soma_bones_fsq/MODEL_CARD.md), [MuJoCo setup](https://nvlabs.github.io/ProtoMotions/getting_started/installation.html).
