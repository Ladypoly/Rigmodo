# Local Character 0.7.0: implemented scope and evidence

4 October 2026. Independent repository at the user-authorized Blender extension path, branch `codex/foundation`. Mesh2Motion application code is unchanged. See [README](../README.md) and [final architecture](unity-humanoid-extension-final-plan.md). The working release includes the complete local humanoid path: geometry-only placement → learned binding → regional refinement → optional twists → local motion → Unity bundle.

## Simplified workflow release

0.7.0 adds parent-conditioned MIA prediction, conservative closed-section finger fitting and an orbitable hand-guide editor under Rig options. Refine Hands clones the accepted rig and changes only digit rest joints. Real GPU tests on a private capture of the user's current avatar preserve source data, body rest matrices, exact locked joints and paint; edited guides constrain all three dimensions. Duplicate application, stale guide changes and modified job constraints fail before allocating objects. On this difficult glove mesh, four automatic finger corrections have distal-section support; six digits remain flagged for manual review. This is a practical improvement, not a claim of anatomical ground truth or universal automatic hand fitting.

Closed cylindrical digits, open sections, competing concentric accessory shells, chain continuity, exact locks and exact guides have separate geometric acceptance. Current compact release evidence is `release-verification-0.7.0-2026-10-04.json`. The UI release records below remain historical evidence for 0.6.0.

An independent bare-hand Shane placement run passed in 3.38 seconds. Its new proposal also passed actual SkinTokens binding (50.83 seconds), AUTO refinement, FBX export and a fresh Unity 6.3 import/skin comparison. The final extracted extension ZIP passed actual conditional MIA inference, copying and guide/stale/lock guards. These structural and geometric checks do not establish anatomical accuracy for every hand pose. Live MIA fitting took about four seconds and reserved roughly 0.91 GiB of CUDA allocator memory on RTX 4090; this is not total process/device memory.

0.6.0 replaces the expanded control dashboard with four quiet tabs: Rig, Skin, Motion, Export. Rig offers Automatic or Landmarks; the front editor guides five clicks, mirrors pairs, supports dragging/undo/cancel and restores the prior view. Eight joint anchors constrain front X/Z while retaining learned depth. Runtime paths, setup, device/search/solver defaults, source visibility and recovery moved into actual extension Preferences with one-time legacy migration.

Skin Avatar runs learned binding, AUTO regional correction and deformation probes as one action, without rerigging, motion or export. Advanced skinning reveals geometric alternatives and region tools. The focused weight panel uses Blender's native painting mode, with a ready Paint brush, bone choice, weight/strength/size and Pose Mode testing. Full custom brush/workspace replacement is outside this UI release. Original/derived duplicates are rejected; successful individual steps hide originals according to Preferences while keeping their geometry intact.

| New check | Result |
| --- | --- |
| Preferences and all workflow/settings draws | Real installed RNA registration/migration and all tabs pass; no runtime fields in workflow panel |
| Guided placement application | Cached actual MIA output; eight front anchors exact, AI depth retained, locks set; stale guides rejected before object allocation |
| Live front editor | Five click groups, eight mirrored points, drag/undo, cancel, restored view/display and removed handlers; user avatar unchanged |
| Native editors | Actual weight mode/essential Paint brush, bone-group change, joint editing, pose testing and character-selection helper pass on private Shane geometry |
| Automatic Skin Avatar | Actual SkinTokens → AUTO → deformation guard, **69.71 s** on RTX 4090; accepted joints/source exact; no placement/motion/export; workflow options retained |
| Baseline regression | Blender/Unity suite all pass: `local-character-acceptance-3bp3b080` |

Compact current evidence is in `release-verification-2026-10-04.json`; the 0.5.0 record remains in `release-verification-2026-10-03.json`. The following provider/geometry/motion acceptance remains applicable from that earlier release unless a newer check is identified.

## Implemented

- Mixamo-style 52 deform bones plus unweighted Root; editable parametric alternative and original MIA geometry-only proposals; exact joint locks and owned-paint preservation across core reproposals.
- Pinned Windows/Vulkan SkinTokens learned binding with branch-preserving transport, correspondence/joint/output validation, copy-only application, protected rows and locked columns. Persistent rigid policies also survive direct AI reapplication.
- AUTO AI-body/digit-surface routing, verified seam links, explicit rigid regions, intrinsic surface-distance initial binding, conservative volume heat/surface fallback, and explicit rigid-mesh-component proposals.
- Optional two-helper forearm twists, matching Blender/Unity evaluation, baked Generic helpers, separate Humanoid playback prefab; artist-placed eyes/jaw/nondeform sockets.
- Kimodo/SOMA-30 local motion, A/T calibration, per-hand/finger controls, heading/planar Root travel, vertical Hips motion, in-place mode, flat-ground contacts, editable endpoint loop blending.
- Selected-Action/slot export and Unity Humanoid/Generic companion. Generated Humanoid `.anim` has explicit Root curves to preserve travel. Source frames, poses, Actions, geometry, paint, materials and morphs are preserved.
- Rig/Skin/Motion/Export workflow and landmark editor, global Preferences, individual correction controls and optional complete orchestration, phase records, undo-owned copy creation, stale-result guards, hidden owned workers, cancellation and independent provider setup.
- Failure-derived deformation probes stop automation before motion/export, retain correction copies and offer readonly rechecks/expert override. Imported-joint reuse adds missing Root without replacing accepted anatomy, including unbound meshes awaiting AI skinning.
- Separate Windows native/source archive and checkpoint/runtime locks. Heavy provider verification is off Blender's UI thread; native EXE/DLL inventory and hashes match the packaged release.

## Actual acceptance

Primary software: Blender 5.2.0 LTS and Unity 6000.3.21f1. Earlier isolated/live checks also passed Unity 6000.4.3f1. New motion/geometry tests used isolated scenes/projects. The latest Unity companion was installed in the previously owned live validation folder with a script backup; compilation passed, both open dirty scenes retained their active/dirty/root-count state, and monitored original scene/package/settings hashes remained unchanged. Neither scene was saved/discarded.

| Check | Result / private evidence |
| --- | --- |
| Full baseline: A/T characters, imported rig, selected Action, source preservation | Final all pass: `local-character-acceptance-ll8iyr05` |
| Extracted release archive | Registration/default provider discovery, manual template, actual geometric worker binding, copy preservation and deformation diagnostics pass from the extracted ZIP: `local-character-archive-release` |
| Fresh provider extraction / isolated runtime | 1,965 native/source/license files, eight models, twelve runtime wheels; tokenizer/Torch downloaded, larger checkpoints verified/seeded; owned parent+child cancellation: `local-character-install-veal6fz8` |
| Actual inference from fresh cache | MIA → SkinTokens → AUTO → twists → Kimodo → FBX, 55 bones, source unchanged; **137.49 s**: `local-character-fresh-inference` |
| Fresh AI workflow on RPM Camera: **visual failure** | Actual MIA/SkinTokens/Kimodo, 9,994 vertices, 53 bones, 135.69 s. Export parity passed (Generic 4.66 µm), but both apps reproduce catastrophic deformation. **Overall failed**, retained as failure evidence: `local-character-rpm-release` |
| Deformation gate / imported Root reuse | Failed Camera is blocked after refinement before motion/export; copies retained, source unchanged. Shane 67→68 bones, joint endpoints and Root-adaptation paint exact; rest-matrix rounding max 3.28e-7. Unbound adaptation and incompatible-reuse rejection pass: `local-character-deformation-release` |
| Final fresh AI humanoid | Hazmat female, **2,792 vertices**, 53 bones, all three actual providers **135.76 s**, source unchanged; posed frames 1/25/49 inspected. Unity both profiles pass, Generic LBS **2.14 µm**, Human Root travel **3.195884 m**: `local-character-hazmat-release`, `local-character-motion-unity-vdo054if` |
| Camera recovery with imported rig/paint | 66 bones including new Root, accepted imported anatomy/paint, cached real Kimodo motion; gross tearing absent in sampled poses. Unity both profiles pass, Generic LBS **2.24 µm**. Tripod hinges still require mechanical-region review: `local-character-camera-recovery`, `local-character-motion-unity-vzas0bzq` |
| Blind joint placement / imported comparison | Geometry-only input; normalization/hand sampling preserved; mean held-out imported-head difference **18.41 mm**, not anatomical error ground truth |
| Harder held-out avatars | Fresh MIA/SkinTokens on Cardboard Boy **11,452 vertices** and T-800 **17,962 vertices**; source geometry/morphs retained; existing generated motion arrays reused: `local-character-corpus-final` |
| Conservative real-volume routing | Cardboard open/nonmanifold and T-800 overlapping/open shells correctly reported surface fallback; this does not claim successful full-volume binding on either avatar |
| Mechanical proposals | **50 components / 8,842 vertices** exact rigid; ambiguous rows/source unchanged; policies survive cached real neural-result reapplication: `local-character-rigid-release` |
| Protected painted reproposal / optional modules | Paint and lock flags exact, locked toe exact, core rest unchanged after eyes/jaw/socket; distinct point/fist hands: `local-character-controls-final` |
| Real-avatar Unity motion (eight bundles) | Humanoid/Generic all pass: `local-character-motion-unity-jxyi7p_v` |
| Generic LBS | Cardboard **2.63 µm**, T-800 **3.12 µm** max point-cloud discrepancy. Fresh/optional Shane **16.86 µm** against a measured rest-precision allowance **90.23 µm**; corresponding rest-frame anisotropy **24.16 ppm**. The allowance is a conservative diagnostic estimate, not a proven universal bound; older simple fixtures retain 10 µm tolerance |
| Human Root travel | Fresh/optional **3.418765 m**, Cardboard **3.824556 m**, T-800 **3.951922 m**, preserved within submicrometer-scale numeric differences in these tests |
| Controlled 90° turn | Actor Root turns when enabled; body world pose retained, no double turn; four Generic/Humanoid cases pass: `local-character-motion-unity-pwl8sd3z` |
| Jump / ground-root policy | Generic LBS **1.25 µm**; Human hips rise **0.368478 m**, actor ground height stays unchanged: `local-character-motion-unity-f0xtiqv0` |
| Twists | Core rest unchanged, paint constraints exact, 55 bones, baked/runtime helper difference **0°** on controlled roll fixture; Generic LBS **0.65 µm**: `local-character-motion-unity-fi0xov42` |
| External Human transition / prefab | Cardboard walk → controlled turn on fresh twist rig; max hand step **70.25 mm**, Root step **59.33 mm**, helper step **8.21°**; saved prefab references valid; scene state preserved. Diagnostic bounds are continuity checks, not animation-quality scores |
| Contacts / endpoint loops | A/T and uniform scales 1/2 pass; stable-contact ankle step **4.776 mm → 0.481 µm**, no unreachable test frames; max pelvis lowering **17.40 mm** at scale 1; endpoint pose matches and source Action/Root travel preserved: `local-character-contact-release` |
| Geometry controls | Closed cylinder uses 1,872 volume cells/48 seeds; open cylinder falls back; close digits stay isolated; ring one-hot; protected/locked paint exact; overlapping shell rejection: `local-character-geometry-release` |

Five actual avatar types and controlled fixtures are limited coverage, including the deliberately retained Camera AI failure. Cardboard/T-800/Hazmat and recovered Camera posed views were inspected; mechanical surfaces still need accepted part semantics and joint review. Normalized valid weights, valid Avatar and close Generic export parity do not prove optimal anatomical placement or perfect skin quality. Strain probes catch extreme tearing; threshold selection is based on these fixtures and can miss smoothly wrong joints, collisions or unwanted rigid-part bending.

Earlier acceptance additionally covers corrupt weights/constraint output, stale mesh/joints/paint, duplicate application, unsupported animation rejection, source texture/morph preservation, exact rigid pairwise distances, seam/digit exclusions and cancellation. Compact machine-readable evidence is retained under `docs/`; private models, weights, exported geometry and renders remain outside Git/distributions.

## Resource and license limits

Test GPU: RTX 4090 24 GB. A sampled complete workflow observed global device usage baseline **8,264 MiB**, peak **11,923 MiB** and owned-process-tree RSS peak **2,443,714,560 bytes**. Global GPU figures include the desktop/other apps and sampling can miss peaks; they are not exact provider VRAM or a physical 16 GB test. MIA separately reported ~979 MB reserved PyTorch allocator memory, also not global peak. Consumer hardware remains a target with explicit evidence limits.

Native-port versus official-reference inference parity and MIA CPU-FPS kernel equivalence are unmeasured. SkinTokens CPU speed is unbenchmarked. Contact correction assumes flat ground; endpoint looping lacks phase/velocity optimization. No advanced facial synthesis, creatures, free cloth or automatic material-rigidity truth. Blender shader translation, object/shape-key animation, modifier baking and arbitrary constrained rigs remain preparation boundaries.

Code/model licenses remain distinct. Blender extension GPL; independent Unity companion MIT; provider source and model notices retained. Kimodo text weights use Meta Llama 3 terms and SOMA weights use NVIDIA's Open Model License. The full weight stack is not unrestricted OSI open source. No proprietary ARP/VHD code, private avatars or checkpoint payloads are distributed.

Release packaging, extension validation, isolated regression and live reload checks are recorded in `release-verification-2026-10-04.json`.
