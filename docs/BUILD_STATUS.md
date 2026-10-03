# Foundation build 0.1.0

3 October 2026. Developed directly in `C:\Users\Elin\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\local_character`, as explicitly requested. This is an independent Git repository on `codex/foundation`; no Mesh2Motion application code was changed. The extension is enabled in the connected Blender 5.2 session and preferences were saved. Its sidebar is open; the existing reference armature was not edited or replaced.

## Implemented

- Owned parametric 52-bone humanoid core plus unweighted Root, optional eyes, editable height/A–T arm angle and rough selected-bounds placement. This is a template, not AI joint detection. Creation does not bind or replace selected meshes.
- Explicit prefixed/unprefixed humanoid mappings, including Pinky→Unity Little. Import preservation retains extra and terminal bones rather than collapsing existing rigs into the new default.
- Read-only, selection-scoped preflight: one accepted rig; explicitly selected meshes; required human identities; ambiguous mapping, invalid geometry/transforms, unsupported modifiers/images, missing textures and zero/invalid weights. Export scope excludes actual bone-display helper objects.
- Temporary-scene FBX export with scene/window/view-layer restoration, actual rest geometry, root insertion on the working copy, deterministic four-weight pruning/normalization, preserved shape keys, packed-image copies and a versioned hashed manifest. New bundle directories are committed only after success; existing exports are never overwritten. Source meshes, rigs, poses, weight groups and shape data remain unchanged.
- Explicit Unity companion command with manifest/hash checks, API-resolved human identities, calibration on a disposable clone, four-influence import and Avatar/calibration reporting. No global import hook or recurrent reimport behavior; user changes remain intact until they explicitly invoke configuration again.
- Reproducible acceptance runner creating private temporary fixtures and a fresh Unity project, with Blender script failure reflected in the process exit code. No proprietary addon runtime or AI downloads are required for this build.

## Evidence

The final complete runner passed in `C:\Users\Elin\AppData\Local\Temp\local-character-acceptance-9qp7nbvg`. A compact copy of its report is [acceptance results](acceptance-results-2026-10-03.json). Versions: Blender 5.2.0 LTS and Unity 6000.3.21f1.

| Case | Blender/FBX result | Unity result |
| --- | --- | --- |
| Generated 1.75 m T-pose | 53 bones, 52 mapped identities, one shape key retained; source scene unchanged | Valid Humanoid Avatar; vertices/binds unchanged by calibration; mapped arm muscle moves hand |
| Generated 1.4 m A-pose | Same structural checks at a different proportion/rest pose | Same Avatar/bind/muscle checks; A-pose calibration preserves bind matrices |
| Private Shane GLB | 67 imported bones retained plus Root = 68; three morphs; original GLB hash unchanged | Valid Humanoid Avatar; two skinned meshes, three blendshapes, 54 mapped identities including eyes; binds unchanged |
| Unweighted vertex | Export preflight rejects it | Not exported |
| Five-influence row | Diagnosed; pruning/normalization changes only the working copy | Four-influence policy configured |

Numerical deformation comparison uses a 50-degree forearm rotation on the two generated fixtures, with Blender evaluated LBS as the independent reference and Unity Generic `BakeMesh` as the actual output. A bidirectional point-cloud distance accommodates FBX vertex splitting and reordering. Worst distance is below 0.6 micrometers. This narrow diagnostic verifies this rotation, both proportions, scale and coordinate conversion; it is not a full animation or skin-quality benchmark. The original comparison failure was caused by a missing handedness reflection/sign in the test frame; explicit frame conversion fixed it without changing exporter transforms or relaxing tolerance.

Blender's extension manifest validation passes. The enabled panel was visually inspected in the live session. Packaged archive contents are checked to exclude Git, test fixtures, documentation, private model binaries and the separately distributed Unity companion.

## Remaining work

Milestone 1 is still open: selected-Action/clip FBX export, external animation retargeting/transitions, calibration quality across real proportions and broader import failures remain to be verified. A valid Avatar and one applied muscle pose do not establish production animation readiness. The current export contains no clips.

Next work is the planned local placement/SkinTokens provider evaluation and job protocol, before extensive UI development. No AI model has been installed, run or benchmarked. The near-one-click mesh-to-animation workflow, learned skinning, region locks, seam-aware surface solve, rigid attachments, voxel refinement, twist helpers/driver and Kimodo motion are not implemented yet. Corpus visual labels/family holdouts and controlled ring/finger/hinge fixtures still need establishment.

Other limits: arbitrary Blender shader translation is not implemented; modifier application requires explicit working-copy preparation; nonuniform armature scale/mirrored transforms are rejected; the bounds template assumes upright Z-up meshes facing -Y. User joint corrections can be made in Edit Mode, but future provider rebuilds do not yet exist. The primary distribution is Blender GPL-3.0-or-later plus independently written MIT Unity companion; model/transitive dependency audits remain gates before adding those providers.
