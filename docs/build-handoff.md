# Compact build handoff

Updated after the foundation build on 3 October 2026. Read this first after chat compaction, then the [final plan](./unity-humanoid-extension-final-plan.md). Current code and detailed [build status](C:/Users/Elin/AppData/Roaming/Blender%20Foundation/Blender/5.2/extensions/user_default/local_character/docs/BUILD_STATUS.md) are in the user-requested Blender extension directory. The foundation is enabled; local AI providers are not implemented yet.

## Objective and fixed decisions

Build an independent local Blender extension that replaces Auto-Rig Pro and proprietary Voxel Heat Diffusion for game characters. Target Blender 5.2 LTS, Unity 6.3 LTS and NVIDIA 16–24 GB VRAM. Main flow: select character → Build Character → generate/choose motion → export to Unity. Provide focused joint/region corrections and preserve them across rebuilds.

- Generate a Mixamo-style 52-bone deform core, including three bones per finger, plus an unweighted `Root` above `Hips`: 53 default export bones. Stable semantic IDs, unprefixed names, import adapters for `mixamorig:`. Unity `Pinky` mapping uses its `Little` identities.
- Optional eyes, jaw and sockets. Twist bones are off by default. First twist module adds two forearm leaf helpers without changing core parentage. Helpers need tested quaternion/rest-frame evaluation in Blender and Unity; basic Humanoid needs no custom runtime.
- Actual A/T bind pose stays authoritative. Record separate Unity T-pose calibration. An A-pose-to-valid-Avatar path that preserves bind geometry is an early gate.
- Humanoid placement fits the fixed template. Evaluate original MIA for proposals; independent marker fitting is the fallback. Accepted/user-locked joints are authoritative. UniRig/free hierarchy is a later creature option.
- SkinTokens is the first organic weight provider. Compare official inference against the native C++ port before selecting the Windows backend. Preserve original vertices, materials and morph correspondence; do not accept model-side joint quantization as a silent skeleton edit.
- Route by movement region, not just bone: organic AI; exact rigid attachments; digit-restricted surface refinement; local volume/geodesic alternatives. Preserve locks, enforce finite nonnegative normalized weights and prune to four export influences with deformation rechecking.
- Surface refinement needs seam-aware transient adjacency: imported UV splits can fragment a hand into hundreds of islands. Do not connect touching fingers or layers using distance alone.
- Kimodo/SOMA-RP motion is retargeted to the accepted rig with root/contact/loop handling and editable hand presets. No guarantee of generated finger animation or creature motion.
- Export selected character FBX, selected clip FBXs, textures and a versioned character JSON manifest. Use Blender's exporter, no mandatory proprietary FBX SDK. Explicit root retained, no synthetic leaf bones, no export-all-Actions behavior.
- A scoped Unity editor companion configures explicit Humanoid mapping/calibration and validates opted-in bundles. Keep user overrides, prevent reimport loops. Generic is the exact baked/mechanical option. Validate Generic vertex deformation separately from Humanoid retargeted motion.
- Keep Mesh2Motion application code unchanged. The user explicitly changed the implementation location to `C:\Users\Elin\AppData\Roaming\Blender Foundation\Blender\5.2\extensions\user_default\local_character`. Its independent Git repository uses branch `codex/foundation`.

## Authorized assets and reference

The user authorizes local imports from `R:\BLENDER\ReadyPlayerMe`, `R:\BLENDER\BANTER_Avatars` and `R:\BLENDER\Altspace_Avatars`. Test in isolated working copies; preserve originals and the unsaved live Blender scene. Local testing permission does not establish training or redistribution rights. Keep private binaries outside Git/release packages.

Inventory: 623 model files including revisions, LODs and alternate formats. [Corpus manifest](./reference/avatar-test-corpus.json): 14 concrete candidates with paths, hashes, family IDs and GLB metadata. [Background Blender audit](./reference/avatar-blender-audit-2026-10-03.json): six successful imports/opens, no source saves. Family/holdout assignment awaits visual triage; avoid LOD/revision/cross-folder leakage.

Start with `BANTER_Avatars\Shane.glb` for the imported-rig path and individual male/female stylized body meshes from `Altspace_Avatars\Humanoid\human_base_meshes_bundle.blend` for placement/proportion coverage. The bundle has no armatures, 44 mesh objects, nonunit scales and invalid mask-driver warnings: extract selected bodies with an explicit modifier policy. `Bloom\Bloom2.fbx` has 78 prefixed bones and several LOD meshes; its GLB has 65 joints, so formats are not interchangeable. `CardboardBoy\CardboardBoy_02.glb` has 18 head morph targets and 512 hand edge components. `Guest\Guest_29.blend` has 59 bones, 60 meshes and four Actions. Robot-named files still need mechanical segmentation review.

Keep three test modes separate: preserve imported rig/weights; blind mesh-only placement with references withheld; fixed accepted rig with source weights withheld. Existing rigs are comparisons, not infallible ground truth. Build synthetic ring, close/touching-finger, seam, layer and mechanical-hinge fixtures because the real corpus has not verified all those cases.

The live Blender MCP inspection found only `Armature`, 67 bones, no mesh, no Actions, identity pose transforms, unit object scale and no saved blend path. Its rest arms descend approximately 59.37 degrees. The [reference snapshot](./reference/blender-humanoid-armature-2026-10-03.json) contains rest matrices and the 52 core / 2 eye / 13 terminal grouping. All source bones are flagged deform; absence of a mesh prevents claiming terminals have zero weights. Generate our own parametric template from the semantic design rather than assume redistribution rights to the scene asset.

## Actual implementation state

Foundation 0.1.0 exists and is enabled as `bl_ext.user_default.local_character`. The live Local Character sidebar is open; preferences were saved. The existing live armature was not changed. Modules implement the owned parametric skeleton, prefixed/unprefixed mappings, selected-mesh preflight, isolated-copy FBX export, four-weight pruning/normalization, packed texture copies and preserved shape keys. Unity's explicit menu companion verifies the manifest and configures/calibrates a valid Avatar without global import hooks.

The complete acceptance runner passed in `C:\Users\Elin\AppData\Local\Temp\local-character-acceptance-9qp7nbvg`. Two synthetic T/A characters at 1.75/1.4 m and the private Shane avatar pass Blender/FBX and Unity 6000.3.21f1 checks. Unity calibration preserves vertices and bind matrices exactly. A 50-degree forearm rotation matches Blender LBS in Unity Generic within 0.6 micrometers on the synthetic cases; mapped Humanoid muscle poses move each character's hand. Invalid weights are rejected and pruning changes only copies. The initial deformation-test mismatch was the test's missing handedness conversion, fixed without altering exporter geometry or relaxing tolerance. Manifest validation and packaging pass; package excludes private assets/tests/docs/Git. See the extension's `docs/acceptance-results-2026-10-03.json`.

No AI checkpoint download/inference, new mesh binding, seam/rigid/voxel solve, clip export, twist driver or Kimodo integration exists. Milestone 1 remains open for selected clips/external animation and broader quality checks. Source Mesh2Motion application code is unchanged; its checkout remains on `main` at reference commit `79f3f61`, with untracked research documents.

Additional live acceptance passed through Creator Works MCP in `R:\UNITY\Banter\SQ-CreatorSDK` (Unity 6000.4.3f1, URP 17.4.0). The new `Assets/LocalCharacterValidation` contains the companion, isolated Editor test assembly, three imported fixtures, reports, prefabs and `Scenes/LocalCharacterPreview.unity`. The preview is open additively; the user's dirty SampleScene remains loaded with 32 roots. Original scene/package/graphics/build-setting hashes are unchanged. Unity calibration now uses `ModelPreview.cs` in disposable preview scenes; ship it with the importer. Fresh Unity 6.3 regression also passes in `local-character-acceptance-hce04b9d`. Extension build status and `docs/acceptance-live-unity-2026-10-03.json` record live evidence; private models/screenshots are not distributed.

Model memory/latency figures in research are upstream evidence, not measurements on this machine. Original MIA's full checkpoint/backbone terms and native inference quality/Windows operation remain engineering gates. No additional user preference is required to start the foundation.

## First implementation sequence

1. Reuse the existing extension repository and read its build status. No applicable `AGENTS.md` was found during creation; check again if the environment changes. Do not recreate the extension or replace user assets.
2. Finish the remaining export proof: selected Actions/clip FBX, external Humanoid animation, broader calibration cases and import failure recovery. Basic skeleton, mapping, preflight, FBX/manifest and Unity companion already exist.
3. Establish visual corpus labels, clean unrigged body fixtures, family holdouts and controlled finger/ring/hinge tests. The current routine runner uses synthetic T/A fixtures and Shane; no broad real-character skin-quality claim has been made.
4. Implement the isolated job protocol and evaluate original-MIA placement and official/native SkinTokens before extensive UI. Separate cold/warm timings, VRAM/RAM, placement correction effort and fixed-rig deformation quality. Choose the backend from measurements and dependency terms.
5. Add regional rigid/digit/seam refinement, then optional twists, then Kimodo/root/contact/loop finishing, then volume alternatives and production packaging. Final-plan exit gates remain authoritative.

## Runtime and tool facts

- Blender executable: `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`. Use isolated `--background --factory-startup --disable-autoexec` for batch fixtures; never replace the connected unsaved scene for bulk testing.
- Python available: `C:\Users\Elin\miniconda3\python.exe`. Blender embeds Python 3.13; heavy ML workers use separately pinned environments.
- Primary Unity installed editor: `C:\Program Files\Unity\Hub\Editor\6000.3.21f1\Editor\Unity.exe`; verify executable when first used. Secondary compatibility editor: `2022.3.62f1`.
- Blender connector skill: `C:\Users\Elin\.codex\plugins\cache\elin-local\codex-blender-connector\0.1.0\skills\blender-connector\SKILL.md`. Inspect with summary tools first; Python operations assign a JSON-serializable `result`; inspect after scene changes.
- No dedicated chat-compaction tool was exposed. This handoff is the durable compact context. Official OpenAI guidance documents `/compact` in the Remote slash-command menu, with availability depending on host/app/account; check the current app's menu rather than claim it was invoked. [Official command guidance](https://developers.openai.com/blog/mastering-codex-remote-for-engineering).

## Dependency boundaries

Use open source and commercially usable local open weights, with full transitive terms recorded before distribution. Exclude installed proprietary VHD binaries, RigAnything's noncommercial release, Puppeteer/PartField's research-only chain and default MIA v2/Hunyuan territorial restrictions relevant to Europe. Avoid making TetGen or proprietary FBX tools mandatory. SkinTokens official MIT and its native Apache-2.0 port are candidates, not verified integrations. Kimodo code/model and text-encoder licenses need separate inventory. Surface-heat and robust-laplacian options are open candidates; robust numerics alone do not solve wrong topology or movement semantics.

Full supporting evidence: [local-model/source research](./local-ai-rigging-and-skinning-research.md) and [adaptive geometry design](./adaptive-local-skinning-design.md). Do not re-research settled choices unless new evidence or an implementation failure warrants it. Do not claim inference, license clearance or Unity acceptance that has not been tested.
