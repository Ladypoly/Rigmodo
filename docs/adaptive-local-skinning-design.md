# A standalone Blender extension for local rigging, adaptive skinning and motion

Research date: 3 October 2026. Hardware target: consumer NVIDIA GPU, 16–24 GB VRAM. This design supersedes the earlier recommendation to integrate the installed Auto-Rig Pro and Voxel Heat Diffusion add-ons.

The concrete implementation decisions, based on the subsequently inspected Blender armature and the user's Unity target, are in [Final Unity humanoid extension plan](./unity-humanoid-extension-final-plan.md). That plan selects a Mixamo-style 52-bone core plus a motion root and optional modules.

The final plan now also specifies a private local avatar corpus and independent imported-rig, blind-placement and fixed-rig-weight evaluations. An isolated Blender audit found 512 edge components in the CardboardBoy hand mesh. This requires seam-aware transient surface adjacency with explicit original-vertex correspondence; disconnected render vertices are not automatically independent moving parts, and proximity alone cannot safely reconnect them. The [corpus manifest](./reference/avatar-test-corpus.json) and [Blender audit](./reference/avatar-blender-audit-2026-10-03.json) record observations, not successful AI or deformation benchmarks.

## Decision and scope

Build a focused Blender extension that creates a portable game skeleton, predicts weights locally, corrects difficult regions with open geometric methods, retargets local motion and exports the result. ARP and the installed Voxel Heat Diffusion package are reference baselines only. Neither is a required runtime, a source of redistributed proprietary binaries or the foundation of the extension.

The central design decision is **classify intended movement before selecting a weight solver**. A finger, its ring and a mechanical finger plate can occupy almost the same space while requiring three different treatments. Selecting one algorithm for each bone is too coarse. Selection belongs at the mesh region/component and vertex–bone relationship level, followed by a constrained solve across adjoining soft regions.

Use AI as the primary proposal for organic skinning. Use deterministic attachment for rigid parts, and surface or volume methods to repair specific failures. This preserves an AI-first workflow without forcing a statistical predictor to solve cases where exact attachment is both simpler and more reliable.

This document combines inspected source, primary research and proposed engineering. Proposed routing rules, quality thresholds and interfaces are not implemented or benchmarked. No AI checkpoints were installed. Existing Blender add-ons and the active Blender scene were not modified. The earlier report contains separate tiny-mesh smoke tests of the installed geometric solvers; those do not establish character quality. [Earlier project and installed-source investigation](./local-ai-rigging-and-skinning-research.md).

## 1. Separate the four problems

| Problem | What must be inferred | Failure that weights alone cannot repair |
| --- | --- | --- |
| Joint placement | Articulation centers, bone frames, bend axes and hierarchy | Elbow or robot hinge rotates around the wrong point |
| Movement classification | Soft tissue, rigid attachment, articulated part, cloth or flexible accessory | Ring is treated as skin; robot plate bends |
| Weight assignment | Which bones influence which vertices, and their transitions | Neighboring finger or leg contributes to the wrong surface |
| Runtime deformation and motion | LBS/DQS, helper joints, retargeting, contact and secondary motion | Twist collapse, foot sliding, skirt collisions or a piston without a suitable motion mechanism |

A model that looks correct at rest can fail all four tests. The extension should diagnose them separately. If placement is wrong, offer joint correction before repeatedly recomputing weights. If a rigid part is assigned to the wrong bone, change its attachment rather than increase smoothing.

## 2. Open components worth evaluating

These are candidates, not an assertion that one released model already provides production quality on every geometry type.

| Component | Evidence and license | Intended use and outstanding checks |
| --- | --- | --- |
| **SkinTokens / TokenRig** | Official code and checkpoint card are MIT-labelled; existing-skeleton CLI; upstream specifies at least 14 GB NVIDIA VRAM | First AI skinning reference on 16–24 GB. Check exact bone preservation, fingers, disconnected accessories, original vertex correspondence and export quality. [Code](https://github.com/VAST-AI-Research/SkinTokens), [weights](https://huggingface.co/VAST-AI/SkinTokens) |
| **skin-tokens.cpp** | Apache 2.0 native port, upstream weights separately licensed; CPU/Vulkan; C API and supplied-skeleton binding | Strong native-worker candidate. Current source documents component parity fixtures and SOMA-to-Mixamo retargeting. Measure Windows build, memory, latency and real assets independently. Numerical parity is not a character-quality benchmark. [Source and status](https://github.com/localai-org/skin-tokens.cpp) |
| **QtMeshEditor SkinTokens adapter** | MIT project; ONNX graphs/model card; native predictor and geometric binding source | Additional Windows-oriented reference. Inspect/adapt isolated modules, not the whole editor. Its sampled-point transfer and conversion need independent parity and close-surface checks. [Model provenance](https://github.com/fernandotonon/QtMeshEditor/blob/master/THIRD_PARTY_AI_MODELS.md), [predictor](https://github.com/fernandotonon/QtMeshEditor/blob/master/src/SkinTokensPredictor.cpp) |
| **UniRig** | MIT code/model-card labels; documented generation minimum of 8 GB CUDA VRAM | General skeleton proposals and a second released skinning baseline. Creature capability does not guarantee a fixed human hierarchy. [Release](https://github.com/VAST-AI-Research/UniRig) |
| **Original Make It Animatable** | MIT application code; released humanoid prediction paths | Evaluate fixed human joint placement separately. Pin the original version and its backbone/checkpoints. The v2 Hunyuan3D 2.1 dependency has additional territorial terms, so v2 is not the default for this EU-based workflow. [Project](https://github.com/jasongzy/Make-It-Animatable), [v2 backbone terms](https://huggingface.co/tencent/Hunyuan3D-2.1/blob/main/LICENSE) |
| **Intrinsic surface Laplacian** | MIT robust-laplacians Python wrapper and geometry-central core | CPU surface refinement on triangles, including difficult connectivity. Numerical robustness does not identify anatomical boundaries or undo an incorrect weld. [Implementation](https://github.com/nmwsharp/robust-laplacians-py), [core license](https://github.com/nmwsharp/geometry-central/blob/master/LICENSE) |
| **Bounded biharmonic weights / constrained harmonic weights** | Established bind-time optimization; relevant libigl BBW source is MPL 2.0 | Shape-aware geometric option and refinement reference. Inspect each chosen module; tetrahedralization is a separate dependency. A surface or voxel domain avoids requiring TetGen. [Research](https://igl.ethz.ch/projects/bbw/), [BBW implementation](https://github.com/libigl/libigl/blob/main/include/igl/bbw.h) |
| **MIT Surface Heat Diffuse Skinning** | Public C++ implementation, MIT notices | Benchmarkable geometric baseline. Uses a voxel grid for visibility/seeding, then diffusion over triangle-neighbor vertices. It is not a grid-free method. [Source](https://github.com/meshonline/Surface-Heat-Diffuse-Skinning/blob/master/src/main.cpp) |
| **Open voxel/geodesic implementation** | QtMeshEditor MIT source includes native GeodesicVoxelBind and postprocessing | Useful implementation reference, with per-region resolution and topology checks added. The inspected implementation caps resolution at 256; its global grid is not our complete solution to fingers. [Binding source](https://github.com/fernandotonon/QtMeshEditor/blob/master/src/GeodesicVoxelBind.cpp) |
| **Dem Bones core / SSDR** | BSD-labelled EA license with additional marks/logo notices; C++ core | Optional fitting of game-compatible LBS weights to independently improved pose examples. Use a data adapter around the core; bundled command-line tools require the proprietary FBX SDK and should not become a mandatory dependency. [Implementation and dependencies](https://github.com/electronicarts/dem-bones), [license](https://github.com/electronicarts/dem-bones/blob/master/LICENSE.md) |
| **Kimodo / kimodo.cpp** | Apache 2.0 code; SOMA checkpoint under NVIDIA Open Model terms; text encoder also has Meta Llama terms | Optional local humanoid motion generation, followed by explicit retargeting. Open weights do not mean all model terms are MIT/Apache. Keep model licensing visible in setup. [Official release](https://github.com/nv-tlabs/kimodo), [native port](https://github.com/localai-org/kimodo.cpp) |

**Puppeteer correction:** its Apache wrapper and checkpoint labels are insufficient for this product. The released skinning instructions require PartField; PartField's code license restricts use to noncommercial research and education, except for NVIDIA and affiliates. Exclude that released dependency chain from the production default. Substituting an encoder is a new compatibility/training project, not a drop-in license fix. [Required dependency](https://github.com/Seed3D/Puppeteer/blob/main/skinning/README.md), [PartField section 3.3](https://github.com/nv-tlabs/PartField/blob/main/LICENSE).

Also exclude the installed proprietary VHD executable and research-only RigAnything from the shipped pipeline. Maintain an inventory covering source modules, checkpoints, encoders, converted bundles and redistributed assets. GPL, MPL and permissive components can all be open source; their distribution obligations differ. Repository labels are a starting point, not a complete audit of every embedded dependency.

## 3. What different geometry requires

The following matrix is a proposed policy derived from the failure mechanisms. It needs validation on a licensed test corpus.

| Geometry | Main failure | Preferred treatment | Useful correction |
| --- | --- | --- | --- |
| Ordinary organic torso and limbs | Wrong anatomical transition; arm/torso or left/right bleed | AI weights, anatomically plausible support | Constrained surface refinement; volume candidate if containment is reliable |
| Close fingers and toes | Coarse voxels join digits; Euclidean neighbors cross branches | AI proposal plus digit identity and intrinsic surface connectivity | Local high-resolution voxel/geodesic candidate; allowed-bone exclusions with palm transition |
| Rings, rigid bangles, buckles and ornaments | Disconnected component lacks diffusion anchors; soft blending changes shape | Infer attachment, then one bone with weight 1 throughout each rigid part | Explicit attachment picker and bend preview |
| Robot plates and mechanical digits | Smooth gradients bend metal; wrong hinge pivot | Rigid part segmentation and exact attachment | Hinge center/axis editor; separately classify flexible joint covers |
| Armor over a soft body | Body weights bend plates; spatial transfer chooses wrong underlying limb | Soft body AI, rigid plates attached by semantic region | Attachment motion tests; separate straps or flexible padding |
| Tight clothing, gloves and shoes | Body inaccessible; thickness and seams confuse direct binding | AI or transfer from an accepted body with correspondence restrictions | Surface smoothing and pinned boundaries; shoes may have both rigid and soft zones |
| Skirts, coats and loose sleeves | Nearby legs contaminate fabric; bone weights cannot reproduce free drape | Restricted transfer plus surface solve; optional dedicated cloth bones | Engine cloth/secondary-motion profile, with clear export expectations |
| Capes, hair cards, ribbons and thin wings | Little/no interior volume; folds are close spatially | Surface domain, deliberate attachment seeds and chains | Soft boundary pins; optional secondary-motion bones |
| Eyes, teeth and mouth interiors | Head/jaw ambiguity; eyes deform rather than rotate | Explicit head/jaw/eye attachment semantics | Simple bone or region overrides; facial animation is a separate feature |
| Creature wings, webbing, tails and tentacles | Generic human priors; broad membranes need several anchors | Appropriate creature skeleton plus AI proposal | Surface constraints across membrane anchors; chain-aware volume refinement |
| UV/hard-normal seams and duplicated vertices | Same physical surface acquires inconsistent weights | Correspondence-aware seam consistency | Match only equivalent surface vertices; retain required mechanical splits |
| Generated triangle soups, overlaps and nonmanifold geometry | Bad connectivity, missing interior, wrong spatial matches | Detection/solver proxy with explicit component semantics | Robust surface numerics or tolerant volume candidate; flag ambiguous topology |
| Very low-poly joints | Too few vertices to form a smooth bend | Appropriate placement and weights within topology limits | Suggest added deformation loops or optional helpers; weights cannot invent geometry |

### Fingers: voxel resolution is a conditional problem

Voxel methods are not inherently incapable of skinning fingers. Their domain can lose the gap between adjacent digits. Autodesk explicitly documents that coarse voxelization can connect nearby body regions and create incorrect influences. Geodesic voxel binding computes interior-path distances; heat diffusion computes a field from sources. Both depend on the correctness of their domain, but they are different algorithms. [Official resolution guidance](https://help.autodesk.com/cloudhelp/2017/ENU/Maya/files/GUID-CF2C698A-44BB-4CA0-BCB9-DB36500DA812.htm).

An illustrative calculation: on a 2 m character, 128 cells along the longest axis give cells about **15.6 mm** wide; 512 gives **3.91 mm**, and 1024 gives **1.95 mm**. A 2 mm gap is poorly resolved even by the last case. A conservative four-cell gap criterion would imply 0.5 mm cells and 4,000 cells along that full axis. A hypothetical dense cubic grid would contain 64 billion cells. Actual character bounding boxes and sparse storage change memory substantially; this is a scaling illustration, not an estimate of the installed solver's allocation.

A 200 mm hand region with 512 cells instead has 0.391 mm cells. This makes local refinement much more practical. Four cells is a proposed conservative heuristic, not a guarantee: rasterization, diagonal connectivity, leakage, thin surfaces and grid alignment still matter.

The default repair should use actual triangle connectivity and digit identity. Permit the correct phalange chain, and parent/palm influences near the finger root; reject unrelated digits. Do not apply a blanket rule that forbids every neighboring-chain influence on the palm. Avoid constructing surface edges simply by spatial k-nearest neighbors: that recreates the problem between close digits or folded surfaces.

Surface diffusion can still travel from one finger to another through the palm, and incorrect sources can seed the wrong digit. Its domain alone does not provide anatomy. If the input truly welds fingers together, flag or cut the solver proxy's false connection; a numerically robust Laplacian cannot know the weld is unintended.

Cropping a hand is appropriate for a geometric solve. It is not automatically appropriate for AI inference: a full-character model may be out of distribution on a cropped hand. Keep the global AI context unless a hand-specific model or crop mode has been validated.

### Rings: solve attachment, then preserve rigidity

A ring is often a separate closed component. Surface diffusion on the finger cannot cross to it without a source or correspondence. Conversely, nearest-surface transfer can pick the adjacent finger, or inherit several phalange weights and squash the ring.

Proposed attachment evidence: the ring's center/axis and hole enclosing a finger segment; accepted finger labels; nearby body correspondences restricted to that finger; and agreement of donor weights over the entire component. Bounding-box size or a metallic material alone is weak evidence. A noncircular ornament may require a different attachment heuristic.

Once attached, every ring vertex gets 100% weight to the chosen bone. Skin nearby flesh independently. With a rigid bone transform, this preserves distances inside the ring exactly. This guarantee assumes no inherited nonuniform scale/shear distorts the bone transform.

Constant blended weights do **not** make LBS rigid. In a simple planar example, blending identity and a 90-degree rotation with equal weights scales in-plane edge lengths by `cos(45°) = 0.7071`: about **29.3% shrinkage**. One-bone attachment gives no such shrinkage. This analytical example explains why “smooth the whole ring uniformly” is the wrong repair.

A ring crossing a knuckle remains ambiguous: attaching it to one segment may preserve shape but intersect the other when bent. Offer the attachment choice and show the bend. No static mesh can always reveal the artist's intended fit, looseness or collision behavior.

### Robots: precision starts with the pivot

Treat robot plates, limb housings and rigid finger segments as parts, with one-bone attachment each. Treat rubber bellows, cables and flexible covers separately. A robot can use a humanoid semantic skeleton for motion compatibility, but its joint axes and pivots must match its mechanism.

Potential pivot evidence includes cylindrical bearings, repeated circular boundaries, opposing part gaps and mechanical symmetry. These are hypotheses. Hidden bearings, stylized forms and fused generated meshes need correction handles. A perfect weight map rotating around a misplaced pivot still produces wrong motion.

One Blender object can contain many rigid islands, and one connected mesh can contain both rigid and flexible regions. Object boundaries, materials and connected components are useful features rather than definitive classifications. A shared vertex cannot follow two different rigid transforms simultaneously. If separate moving plates are welded, true articulation may require splitting the mesh at the boundary; identify this limitation rather than disguising it with a soft blend.

Pistons, linkages and sliding joints may require a few additional deform bones or baked constraint motion. A biped skeleton alone cannot express every mechanism. Keep those helpers explicit and purposeful; do not generate a full animator control rig by default. During retargeting, project motion onto accepted hinge axes and joint limits where appropriate, then check contacts again: unconstrained human rotations can violate a robot's mechanism even when its weights are exact.

### Clothing and accessories: restrict correspondence

For tight clothing, barycentric transfer from an accepted body surface can provide a useful initialization. Filter correspondences by anatomical region, component and distance; use orientation where helpful rather than assuming all shells have identical normal direction. Nearest-point transfer by itself can cross thighs, choose the torso for a sleeve, or choose the wrong finger for a glove. Normal agreement also fails on turned/inverted panels, so it must not be the sole criterion.

If no underlying body exists, the visible garment may not reveal the true shoulder or hip. Use the humanoid placement prior, expose uncertain joint depth, then solve the garment surface. A cape or skirt's attachment weights are not a cloth simulation. An ordinary exported skeletal animation cannot reproduce all free cloth motion, collisions or hair motion without additional runtime support or bones.

Belts illustrate why classification matters: a flexible belt may follow body weights, a rigid buckle should attach as a unit, and a dangling strap needs a chain or secondary motion. All can be close to the same pelvis bone.

### AI-specific failure mechanisms

Small accessories and narrow digits may be weakly represented in global surface samples. A sampled predictor can miss a small part even while predicting the body well. Preserve these components in preprocessing and use full-resolution attachment/repair rules afterward. Oversampling hands can help only if the model's conditioning and sampling assumptions remain valid.

Raw predicted weights can be anatomically implausible, too diffuse, or inconsistent across duplicated vertices. AI logits, sampling variability and disagreement between providers are possible diagnostic signals, but none automatically means calibrated confidence. High weight entropy is normal in a smooth joint transition; it is not sufficient evidence of bad skinning.

A native port's component parity fixtures test implementation fidelity. They do not prove robustness on our meshes, and autoregressive numerical differences can change later token choices. Compare complete deformation results as well as intermediate tensors.

## 4. The proposed adaptive algorithm

### Stage A: snapshot and analyze

Capture mesh geometry, object transforms, bone rest transforms, semantic mapping, original vertex IDs, materials and explicit user tags. Maintain a mapping for every mesh independently. Analyze triangle connectivity, connected components, boundary edges, normals, thickness evidence, gaps between nearby surfaces and candidate attachments.

Use a separate detection/inference proxy where necessary. Preserve original topology, UVs, materials and shape keys in the user asset. Do not remesh the exported asset simply because a model prefers manifold input. Keep explicit correspondences back to the original mesh. Evaluated modifiers that change topology require a defined conversion or mapping policy.

### Stage B: classify movement

Use this precedence: **explicit user settings and locks → accepted existing metadata → validated semantic/model evidence → geometric heuristics**. Assign region states such as `soft`, `rigid attached`, `articulated rigid`, `thin flexible`, and `uncertain`. Geometry segmentation and movement segmentation are related but not identical.

Record why each proposal was made, its allowed bone set, and which evidence is missing. A simple deterministic classifier is the first version. Train a learned selector only after collecting lawful, licensed examples and correction labels; a general local language model is unnecessary for numerical weight routing.

### Stage C: obtain the AI proposal

Run SkinTokens on the accepted skeleton as the initial organic weight proposal. Remap by explicit bone IDs and validate conditioning/output correspondence. Quantized joint coordinates used inside a model must not silently replace the accepted joint centers in the exported skeleton.

Give rigid regions exact attachment weights independently. Keep the raw AI proposal available for comparison and undo. Separate changed weights from unchanged protected weights.

### Stage D: diagnose regions and generate only necessary candidates

Flag impossible support, cross-digit/cross-limb influence, zero-weight components, missed thin pieces, seam disagreement and rigid strain. For an uncertain soft region, generate an intrinsic surface candidate or a local voxel candidate if the volume/gap checks support it. For an accessory, generate attachment candidates rather than diffuse weights over every bone.

Volume suitability requires usable occupancy, relevant bones connected to suitable seed cells, resolved local gaps, and no unintended bridges. Open or nonmanifold geometry does not automatically rule volume out; nor does using flood fill automatically make every open mesh valid. Inspect the generated domain.

Surface suitability requires meaningful adjacency and reliable source/boundary assignments. A disconnected shell needs its own seeds or correspondence. Prefer triangle-domain Laplacians to unrestricted point-cloud neighborhoods on close surfaces.

### Stage E: solve adjoining soft regions together

Do not splice independently normalized bone columns. Changing one bone affects the budget available to every other bone at that vertex. Combine provider proposals with region-dependent fidelity and geometric constraints, then solve and normalize consistently.

A useful proposed objective is:

```text
minimize over W:
  sum_v lambda_v * ||W[v] - W_AI[v]||^2
  + mu * trace(W^T L W)
  + optional nu * sum_pose ||LBS_pose(W) - Y_target_pose||^2

subject to:
  W[v,b] >= 0; sum_b W[v,b] = 1
  W[v,b] = 0 for disallowed vertex-bone relationships
  accepted user weights and boundary values remain fixed
  rigid regions have a preselected one-hot attachment
```

Here `L` is a positive semidefinite surface/domain operator with barriers at intended movement boundaries. A biharmonic variant uses a mass-aware squared operator rather than the first-order surface energy. Bounds and row-sum constraints must be handled together; blindly smoothing and normalizing can violate locked entries or reintroduce forbidden influences. For partially locked rows, allocate only their residual weight mass. Detect contradictory locks instead of silently renormalizing them.

The optional pose target term needs independently improved target shapes: artist-approved examples, a suitable cage/shape-preserving deformation, or licensed reference animation. Fitting to poses generated by the same bad LBS weights does not create new information. Dem Bones is a candidate for this later stage, not a magical single-rest-mesh weight predictor.

Rigid attachment choices are discrete decisions made before the continuous solve. Blending several weight maps can still produce a poor deformation, so validate the combined result, not merely the individual candidates.

After refinement, apply the export profile's influence limit, re-normalize while respecting locks, and re-evaluate poses. Four influences is a useful compatibility default, not a universal engine limit. If pruning destroys an accepted region, warn or change its allocation within the selected profile.

### Stage F: test movement and stop when evidence is adequate

Use a small reproducible pose suite: individually curl fingers; bend elbows/knees; raise arms; twist forearms; squat; spread legs; move jaw/eyes when supported; articulate creature chains or robot hinges. Add the actual requested motion later.

Evaluate forbidden influence leakage, rigid edge-length change, seam disagreement, excessive triangle distortion, collapse and relevant collisions. Measures must be movement-specific: soft tissue is allowed to deform, and some surface contact is intentional. On rigid parts, exact attachment already supplies a stronger guarantee than optimizing a generic smoothness score.

Compare against accepted poses or original proposals where available. Rest geometry alone cannot tell us the ideal elbow crease, and low strain is not universally the correct organic deformation. Route ambiguous failures to a focused review rather than claim a quality score proves the skinning is correct.

Only recompute flagged regions and their transition collars. Cache snapshots and intermediate geometry by revision; invalidate when topology, placement, rest transforms or relevant constraints change. Cap candidate retries and report a failed provider. The user must retain a usable local geometric path when AI is unavailable.

## 5. Export limitations that must shape the design

LBS can shrink or collapse on twists; DQS changes the runtime deformation and may produce different bulging. Better weights cannot eliminate every limitation of a chosen deformation representation. Autodesk documents the LBS/DQS distinction separately from bind methods. [Skinning-method guidance](https://help.autodesk.com/cloudhelp/2017/ENU/Maya/files/GUID-CF2C698A-44BB-4CA0-BCB9-DB36500DA812.htm).

Preview the actual selected game export behavior. Blender Preserve Volume, corrective modifiers and procedural constraints should not make the result appear better than the exported rig will behave. Optional twist joints, helper bones or exported corrective morphs need an explicit profile and round-trip verification. A few necessary deform bones are compatible with a simple rig; hundreds of animation controls are unnecessary for this workflow.

Direct Delta Mush is a different deformation mechanism, not merely a better weight map. It is valuable as a research/reference target, but cannot be assumed to survive an ordinary skeleton-and-weight export. An advanced offline fitting stage may approximate improved deformation in LBS and should report residual error. [Author's research page](https://binh.graphics/papers/2019s-DDM/), [EA's implementation context](https://www.ea.com/seed/news/ddm-compression-with-continuous-examples).

Normalize/bake transforms consistently, handle mirrored or negatively scaled objects, retain bind matrices, and verify vertex/bone remapping across multi-mesh exports. Never use “the rig appears at rest” as the only export acceptance test.

## 6. Replace ARP with a compact placement workflow

Create a versioned humanoid semantic definition and construct its deform armature directly. Provide a compact body preset, optional articulated hands, optional facial/attachment bones, and optional twist bones. A strict Mixamo-compatible export profile can have its expected hierarchy; a smaller game preset can map to it semantically. Renaming alone cannot reconcile different parents, rest axes and joint counts.

For humans, evaluate original MIA semantic joint proposals and constrained fitting to the fixed definition. Geometric refinement should resolve depth, bend planes, bone lengths and symmetry without letting bulky clothing drag the skeleton to the center of the outer silhouette. The existing ARP source investigation supports this general division between landmark detection, depth correction and reference fitting; its proprietary implementation is not needed.

For creatures, evaluate UniRig or TokenRig proposals and use a compatible template when an existing animation family is selected. Arbitrary generated hierarchies need review and mapping. General generation is not evidence of reliable joint identity for every limb, finger or wing.

Joint placement quality remains a separate acceptance gate, especially shoulders, hips, thumb bases and mechanical pivots. If released predictors are not reliable enough, the extension can still provide fast marker/template correction while the placement provider improves. That is a complete independent workflow, but not evidence that unrestricted one-click placement has been solved.

## 7. Almost one click, with focused correction

The ordinary path is: **select character → choose game rig/profile and motion prompt → Build & Animate → preview → export**. Model setup is a one-time local preparation step. With high-confidence results, the extension progresses through placement, AI weights, attachment correction, pose checks and retargeting automatically.

When a region is ambiguous, expose a small attention list: “ring attachment,” “left elbow depth,” or “flexible/rigid knee cover.” Selecting an item focuses the viewport and offers the relevant correction. Avoid making users choose a global solver before seeing evidence.

Useful controls are: move/lock a joint; mark soft/rigid; choose attachment bone; exclude a bone; protect selected weights; adjust a transition; refine a selected region with AI/surface/voxel; compare before/after; and restore a previous result. Advanced solver settings can exist separately. Store intentional overrides so rebuilding preserves decisions.

Keep a normal Blender armature, vertex groups and Actions as the result. Optional editing helpers may be temporary. Export only the selected deform skeleton and baked animation/profile data. Every result application should be one undoable operation and reject stale scene revisions.

Kimodo produces humanoid motion, not skinning and not general creature animation. Retarget by semantic identity and rest frames; handle root scale, foot contact and hand differences explicitly. The current skin-tokens.cpp source includes SOMA30-to-Mixamo52 mapping/check tools worth examining, which reduces duplicated work but still needs our target-skeleton validation. [Native mapping implementation/status](https://github.com/localai-org/skin-tokens.cpp).

## 8. Consumer hardware and packaging

Use a small Blender client plus an external local worker. This avoids heavy CUDA packages inside Blender's embedded Python and allows either a native executable or a pinned inference environment. Queue GPU stages rather than assume SkinTokens and Kimodo can coexist in VRAM. Free one provider before loading another.

| Hardware | Initial policy |
| --- | --- |
| NVIDIA 16 GB | Fits SkinTokens' stated minimum in principle, but Blender viewport and actual workload consume headroom. Validate a reference job; use native/managed isolated execution and sequential motion generation. |
| NVIDIA 24 GB | Preferred development/evaluation tier for more headroom; still measure peaks and cold/warm loading. |
| CPU fallback | Surface refinement, part attachment and smaller voxel jobs. Native SkinTokens has a CPU path, but acceptable character latency is not established here. |

No new latency or memory guarantee is claimed. Measure model load, geometry preparation, inference, transfer, repair and export separately, plus peak VRAM and host RAM. Native ports may simplify Windows distribution; they are not automatically faster or equivalent on every GPU.

Keep local job manifests with mesh/rig revisions, ordered bone IDs, original vertex mapping, model/version/hash, seed, constraints and export profile. Validate finite weights, indices, fresh output and unchanged input revisions before touching Blender. Use private per-job directories and an explicit bounded process/API; no cloud service is required.

For the first prototype, compare official SkinTokens with the native port on identical accepted rigs. Treat QtMeshEditor's ONNX adapter as a third packaging experiment rather than skip the reference comparison. Its model card describes 8-nearest-sample inverse-distance transfer; that step needs our component/semantic restrictions around fingers and layered surfaces. Its separate UniRig converter previously had a reported NaN-output failure, demonstrating why converted bundles need complete end-to-end checks. That issue does not establish that the SkinTokens graphs have the same fault. [Converted model contract](https://huggingface.co/fernandotonon/QtMeshEditor-skintokens-onnx), [UniRig conversion issue](https://github.com/fernandotonon/QtMeshEditor/issues/1025).

## 9. Benchmark that can prove this works

Use licensed meshes covering ordinary humans, stylized proportions, close/touching fingers, rings, gloves, multiple clothing shells, armor, eyes/jaw, separated robot parts, fused robot surfaces, cables, skirts/hair cards, thin creature membranes, tails, bad topology and UV seam duplicates. Include challenging combinations, not only one example of each material.

Compare on the **same accepted skeleton**: raw AI; AI plus adaptive correction; surface-only; volume/geodesic-only; Blender automatic weights; and existing installed tools as external baselines. Compare placement providers separately. Include port-versus-reference comparisons and the cost of corrections rather than only average weight error.

| Acceptance area | What to record |
| --- | --- |
| Basic correctness | Finite/nonnegative weights; normalized rows; valid bone IDs; no rest displacement; exact locks; selected influence limit |
| Finger separation | Forbidden digit weight mass away from palm boundaries; unintended displacement when another finger alone moves |
| Rigid attachments | Maximum normalized edge-length change and correct attachment under bends; zero within floating-point tolerance under rigid one-bone transforms |
| Organic deformation | Accepted/reference pose error where available, joint-specific visual rating and manual correction time |
| Thin/disconnected geometry | Coverage, valid seeds/attachments, wrong-surface transfer count and component-specific failures |
| Export fidelity | Reloaded rig and deformed vertices agree with selected runtime preview; materials/topology/animation preserved |
| Usability | Uninterrupted completion rate, focused correction count, failure recovery, undo/cancellation and stale-result rejection |
| Consumer performance | Cold/warm wall time, peak VRAM/RAM, high-poly scaling, viewport coexistence and repeatability |

Without ground truth, use accepted artist judgments and measurable failure checks; do not invent a ground-truth weight map or turn a heuristic into a confidence percentage. Four-influence pruning and simplified inference proxies must be evaluated after transfer/export, not only at their intermediate resolution.

## 10. Implementation order

1. **Independent foundation:** compact deform armature, humanoid semantics, snapshot/correspondence format, correction handles, protected weights and engine-consistent preview/export. Add marker fitting so the extension is usable without ARP.
2. **AI-first baseline:** official SkinTokens skin-only adapter and native-port comparison on accepted rigs. Record licensing inventory, quality, memory and Windows packaging. Do not promise unrestricted one-click results before this measurement.
3. **Hard cases first:** rigid component attachment, per-digit allowed influences, reliable surface refinement, seam consistency and pose diagnostics. These directly address rings, fingers and robots without requiring another trained model.
4. **Volume refinement:** open voxel/geodesic provider, locally cropped/adaptive domains, explicit occupancy diagnostics and cross-region transition constraints. Benchmark the MIT surface-heat baseline as a distinct method.
5. **Automatic placement and motion:** benchmark fixed-human proposals, add creature generation as a separate profile, then Kimodo/native motion with validated retargeting and export. Keep those evaluations separate from weight quality.
6. **Later optimization:** pose-target fitting, optional twist/secondary bones, cloth integration and a learned selector only when evidence shows the rules are insufficient.

The first shippable target should be T/A-pose game humanoids with articulated hands, rigid accessories and layered clothing, plus a defined robot mode. Broader creatures, arbitrary posed input, facial performance and free cloth introduce separate problems. The architecture supports them without claiming one released model already solves them all.

## Evidence and reproducibility notes

Source facts above were checked against author repositories, model cards, source implementations and official geometry documentation. The matrix, regional policy, optimization formulation, UI and milestones are proposed design. The voxel sizing and equal-weight rotation examples were calculated directly in Python; they are analytical illustrations rather than asset benchmarks.

Additional source snapshots checked for this focused investigation:

| Source | Revision / evidence |
| --- | --- |
| QtMeshEditor | `259d9823d55433d1d5301efe00549f666dc79443`; `SkinTokensPredictor.cpp`, `GeodesicVoxelBind.cpp`, `SkinWeightsPost.cpp`, conversion script and MIT `License` |
| skin-tokens.cpp | `37b28284d0015c4e61e2657072f3b0f5166af207`; supplied-skeleton path, C API, documented parity fixtures and SOMA mapping |
| Surface Heat Diffuse Skinning | `578fed63590d2034fcc6b0981f3c87265777d184`; `src/main.cpp`: triangle-neighbor assembly around lines 465–481; diffusion around 1227–1286; voxel-assisted bone visibility/seeding |
| robust-laplacians-py | `668a4ff0174682c7c2c3be957c45e2fdb0e68589`; mesh-domain API, dependency descriptions and MIT license |
| libigl | `include/igl/bbw.h` MPL notice, active-set solver interface, constraints and normalization contract |
| PartField / Puppeteer | PartField section 3.3 and Puppeteer skinning checkpoint dependency instructions |

Outstanding decisions require experiments: exact GPU inference, fixed-template placement reliability, skinning quality on close fingers and accessories, native Windows packaging, model conversion equivalence and full dependency licensing. The research establishes a credible architecture and shortlist; it does not establish that the replacement extension is already implemented or that one-click quality has been demonstrated.
