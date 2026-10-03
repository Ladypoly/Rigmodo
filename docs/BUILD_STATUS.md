# Foundation build 0.2.0

3 October 2026. Developed directly in `C:\Users\Elin\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\local_character`, as explicitly requested. This is an independent Git repository on `codex/foundation`; no Mesh2Motion application code was changed. The extension is enabled in the connected Blender 5.2 session and preferences were saved. Its sidebar is open; the existing reference armature was not edited or replaced.

## Implemented

- Owned parametric 52-bone humanoid core plus unweighted Root, optional eyes, editable height/A–T arm angle and rough selected-bounds placement. This is a template, not AI joint detection. Creation does not bind or replace selected meshes.
- Explicit prefixed/unprefixed humanoid mappings, including Pinky→Unity Little. Import preservation retains extra and terminal bones rather than collapsing existing rigs into the new default.
- Read-only, selection-scoped preflight: one accepted rig; explicitly selected meshes; required human identities; ambiguous mapping, invalid geometry/transforms, unsupported modifiers/images, missing textures and zero/invalid weights. Export scope excludes actual bone-display helper objects.
- Temporary-scene FBX export with scene/window/view-layer restoration, actual rest geometry, root insertion on the working copy, deterministic four-weight pruning/normalization, preserved shape keys, packed-image copies and a versioned hashed manifest. New bundle directories are committed only after success; existing exports are never overwritten. Source meshes, rigs, poses, weight groups and shape data remain unchanged.
- Explicit Unity companion command with manifest/hash checks, API-resolved human identities, calibration on a disposable clone, four-influence import and Avatar/calibration reporting. No global import hook or recurrent reimport behavior; user changes remain intact until they explicitly invoke configuration again.
- Reproducible acceptance runner creating private temporary fixtures and a fresh Unity project, with Blender script failure reflected in the process exit code. No proprietary addon runtime or AI downloads are required for this build.

## Evidence

The latest complete runner passed in `C:\Users\Elin\AppData\Local\Temp\local-character-acceptance-oaosqpe0` after the live-editor isolation changes. A compact copy of its report is [acceptance results](acceptance-results-2026-10-03.json). Versions: Blender 5.2.0 LTS and Unity 6000.3.21f1.

| Case | Blender/FBX result | Unity result |
| --- | --- | --- |
| Generated 1.75 m T-pose | 53 bones, 52 mapped identities, one shape key retained; source scene unchanged | Valid Humanoid Avatar; vertices/binds unchanged by calibration; mapped arm muscle moves hand |
| Generated 1.4 m A-pose | Same structural checks at a different proportion/rest pose | Same Avatar/bind/muscle checks; A-pose calibration preserves bind matrices |
| Private Shane GLB | 67 imported bones retained plus Root = 68; three morphs; original GLB hash unchanged | Valid Humanoid Avatar; two skinned meshes, three blendshapes, 54 mapped identities including eyes; binds unchanged |
| Unweighted vertex | Export preflight rejects it | Not exported |
| Five-influence row | Diagnosed; pruning/normalization changes only the working copy | Four-influence policy configured |

Numerical deformation comparison uses a 50-degree forearm rotation on the two generated fixtures, with Blender evaluated LBS as the independent reference and Unity Generic `BakeMesh` as the actual output. A bidirectional point-cloud distance accommodates FBX vertex splitting and reordering. Worst distance is below 0.6 micrometers. This narrow diagnostic verifies this rotation, both proportions, scale and coordinate conversion; it is not a full animation or skin-quality benchmark. The original comparison failure was caused by a missing handedness reflection/sign in the test frame; explicit frame conversion fixed it without changing exporter transforms or relaxing tolerance.

Blender's extension manifest validation passes. The enabled panel was visually inspected in the live session. Packaged archive contents are checked to exclude Git, test fixtures, documentation, private model binaries and the separately distributed Unity companion.

## Live Unity project verification

The user additionally authorized testing in their open MCP-connected project. Creator Works MCP selected `R:\UNITY\Banter\SQ-CreatorSDK`, running Unity `6000.4.3f1` with URP 17.4.0. The previous default MCP project was stale; the active project selection is session-local and did not rewrite the launcher configuration.

All three existing exported fixtures were imported into the new `Assets/LocalCharacterValidation` folder. The live acceptance command passed Avatar, bind, blendshape, meter-scale, muscle-pose and Generic LBS checks with the same error bounds as Unity 6.3. Imported materials reported supported `Universal Render Pipeline/Lit` shaders. See [live acceptance results](acceptance-live-unity-2026-10-03.json).

Calibration and pose/deformation checks now use `ModelPreview`, which instantiates into disposable Editor preview scenes. The batch entry point refuses to quit a non-batch Editor. Live validation compares open-scene handles, active state, dirty flags and root counts before/after. `SampleScene` had unsaved changes after the project's asset/script refresh; those changes were neither saved nor discarded during validation. Its original scene file, package inventory and monitored graphics/build settings match their pre-test hashes.

A separately saved `Assets/LocalCharacterValidation/Scenes/LocalCharacterPreview.unity` and three prefabs provide visible inspection fixtures. The preview is open additively; `SampleScene` remains loaded with its unsaved changes and 32 roots. Preview rendering chooses a layer unused by other open scenes, without changing layer definitions or other scene objects. The camera faces the avatars and was inspected through an actual MCP Game-camera capture. Private screenshots and model binaries remain outside version control/distribution.

No Unity project settings, build-scene list or package dependencies were edited. Only the dedicated validation asset folder was added; its Editor assembly is isolated from runtime builds. The selected-clip continuation below adds actual animation playback checks; AI binding quality remains untested.

## Selected-Action continuation

Foundation 0.2.0 adds an opt-in selected-Action export alongside the character FBX. The animation FBX contains only the armature's selected slot, sampled each frame at scene FPS. The range excludes other slots unless the Action has an explicit artist range. Source pose, frame, Action/slot, NLA, scene, weights and morph data are preserved. A selected Action starting at frame 7 was exercised while another slot spanned -50 to 100 and an unrelated NLA Action was present. Unsupported object-transform channels fail before staging.

Each animation sidecar records its matching character file hash, hierarchy/rest signature, source path, selected frame range, FPS, loop flag and bone-motion policy. The Unity companion requires a configured matching source Avatar and imports one named take. It preserves hierarchy on both character and animation importers. This is essential because Unity otherwise collapses the single parent in animation-only FBXs, breaking Generic binding paths; see [Unity's preserveHierarchy API](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/ModelImporter-preserveHierarchy.html). Initial clip compression is disabled: Unity's default compression caused a 1.5 mm midpoint deviation in the diagnostic. Users can make an explicit compression choice afterward.

The complete fresh runner passes Blender 5.2.0 and Unity 6000.3.21f1. Generic clip sampling at start/mid/end matches independent Blender evaluated geometry within 0.6 micrometers, including forearm and finger motion. Root travel is 0.30000001 m, without loss or doubling. The exported Humanoid clip was played through an isolated PlayableGraph on the 1.75 m T-pose, 1.4 m A-pose and private Shane avatars. Hands move and proximal finger rotations change about 23.9 degrees. Enabled root motion produces 0.30, 0.24 and 0.32911 m respectively, matching Unity's target/source humanScale ratio within 0.1 mm. These checks cover the diagnostic clip; they do not establish walk contacts, transition quality or arbitrary source motions.

The same clip, retargeting and root checks passed in the live Unity 6000.4.3f1 URP project. Two new animation fixture bundles were added under the owned validation folder. Editor test compilation has no errors or warnings. Open scene handles, dirty states, active scene and root counts are identical before/after validation. Asset/script refresh also marked the owned preview dirty; no user scene was saved or discarded. Original monitored scene/package/settings hashes remain unchanged.

The installed Blender panel now includes the selected-Action and loop options. Reusable Unity code includes `AnimationImporter.cs`, `LocalCharacterImporter.cs` and `ModelPreview.cs`; all three are shipped in the companion archive. Acceptance harnesses and private model binaries remain excluded from both distributions.

## Remaining work

Milestone 1 now has selected Action/slot export and actual Humanoid retargeted playback evidence. Broader calibration cases, external animation adapters, transitions, contact/loop finishing, in-place conversion and import failure recovery remain to be completed before a production animation-readiness claim.

Next work is the planned local placement/SkinTokens provider evaluation and job protocol, before extensive UI development. No AI model has been installed, run or benchmarked. The near-one-click mesh-to-animation workflow, learned skinning, region locks, seam-aware surface solve, rigid attachments, voxel refinement, twist helpers/driver and Kimodo motion are not implemented yet. Corpus visual labels/family holdouts and controlled ring/finger/hinge fixtures still need establishment.

Other limits: arbitrary Blender shader translation is not implemented; modifier application requires explicit working-copy preparation; nonuniform armature scale/mirrored transforms are rejected; the bounds template assumes upright Z-up meshes facing -Y. User joint corrections can be made in Edit Mode, but future provider rebuilds do not yet exist. The primary distribution is Blender GPL-3.0-or-later plus independently written MIT Unity companion; model/transitive dependency audits remain gates before adding those providers.

Provider preparation observation: the local GPU is an RTX 4090 with 24,564 MiB reported VRAM. An existing clean `C:\Tools\AI\skin-tokens.cpp` checkout is at `46dbfecda3d9c2dcd87301c9f1127e1f437ed0ed`; it contains no checkpoints or built CLI, and its GGML submodule is not initialized. This was inspected read-only. Native Windows/Vulkan setup and official/native comparison remain untested.
