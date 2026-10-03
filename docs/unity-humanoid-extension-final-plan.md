# Local Character: final architecture and implemented humanoid scope

Decision/evidence date: 3 October 2026. Blender 5.2 LTS, Windows x64, Unity 6.3 LTS (`6000.3.21f1`), NVIDIA 16–24 GB target. Implemented release: **0.5.0**. Independent extension repository; Mesh2Motion application code remains unchanged. See [README](../README.md) for operation and [build status](BUILD_STATUS.md) for measured acceptance and limits.

## Skeleton and placement

Default: 52 Mixamo-style body/finger deform bones plus an unweighted `Root` above `Hips`. Body: Hips, Spine, Spine1, Spine2, Neck, Head. Each side: Shoulder → Arm → ForeArm → Hand, five three-joint fingers, and UpLeg → Leg → Foot → ToeBase. `Pinky` maps to Unity's `Little` identity. Names are unprefixed; imported semantic identities accept namespace prefixes. Generated motion requires structural Root named `Root` without a prefix.

The inspected live reference has 67 deform bones, including fourth finger/end bones and two eyes, with arms in an approximately 59.37° A-bind pose. It remains untouched; [reference snapshot](reference/blender-humanoid-armature-2026-10-03.json) records it. Newly generated defaults omit terminal extras; existing weighted rigs retain their hierarchy in the imported-rig export path. No private reference coordinates are distributed as a template.

Original MIA proposes fixed semantic heads/tails from mesh geometry only. Its verified model code runs outside Blender in isolated Python 3.11/CUDA. Both normalization stages and exact clipped-triangle hand sampling are retained. Independent CPU farthest-point sampling avoids a compiler-dependent CUDA extension; numerical equivalence to the original kernel is unmeasured. The owned parametric skeleton is the editable manual alternative. Upright orientation and separated A/T limbs are input assumptions, not automatic guarantees.

Accept/Edit Mode corrections are authoritative. Joint locks preserve exact heads/tails across reproposals. Core reproposals preserve owned paint/masks; extra deform modules block core replacement to prevent paint loss. Automatic anatomical validation cannot establish ground truth from mesh geometry alone. The UI supports stopping after placement before binding when correction is needed.

Reuse adapts a missing structural Root on an independent copy instead of falling back to learned anatomy. Imported endpoints/paint are retained; Blender may reconstruct rest matrices with float rounding (Shane measured maximum 3.28e-7 matrix difference, zero endpoint movement). Incompatible full humanoid rigs require explicit preparation or disabling reuse.

## Binding and movement regions

SkinTokens is the primary organic provider, conditioned on accepted joints in depth-first branch order. Original weights are withheld. Output validation requires unchanged vertices/triangles, joint heads/parents and correspondence, finite nonnegative normalized learned weights. Native joint quantization never silently replaces the Blender rig.

Routing priority: protected paint/locked influences, explicit region policies, accepted rigid-component proposals, digit-restricted surface refinement, AI body weights. AUTO preserves unlabeled body rows exactly. Verified edge seams may reconnect render splits while preserving vertex IDs; matching position alone does not connect fingers or garment layers. Finger labels combine weight evidence with accepted rest-joint proximity. Ambiguous geometry stays reviewable.

| Geometry / intent | Implemented response |
| --- | --- |
| Organic torso/limbs | AI weights, selective surface correction when requested |
| Close fingers | Accepted digit identity, restricted influences, actual surface adjacency |
| Ring, plate, tool, mechanical hinge | Artist chooses attachment bone; exact one-bone region |
| Robot assembled from rigid parts | Explicit rigid-mesh mode; confident connected components suggest one AI-backed parent, ambiguous parts retain paint |
| UV/render seams | Temporary verified adjacency; ambiguous seams remain separate |
| Unweighted mesh / AI fallback | Intrinsic graph-distance binding plus anchored graph heat |
| Closed volume | Bounded sparse interior heat; digits/thin unresolved details use surface distance |
| Open/nonmanifold/overlapping volume | Reported surface-distance fallback |
| Layered garments | Preserve distinct layers; require explicit region choice where attachment is ambiguous |

Rigid proposals become persistent policies and survive AI reapplication immediately. They are not automatic material classification: the artist explicitly declares a mesh rigid. Latest region policies win; protection and locked columns remain authoritative. Conflicting constraints fail. Independent geometric solvers do not claim cotangent/BBW/proprietary VHD equivalence. General self-intersection proof, cloth physics and multi-layer collision resolution are outside scope.

Independent rest-weight LBS probes rotate elbows, knees, index bases and head by 60 degrees. Optional helper swing follows its source. Tiny seam edges are excluded. A probe with at least 0.5% of edges stretched over 5 times, or a 99th percentile above 3 times, stops the workflow before motion/export; lesser extremes warn. These failure-derived thresholds are diagnostics, not universal anatomical criteria. Above 250,000 selected vertices the review requests a smaller scope or explicit expert override. Reports persist with the workflow and review rig; completed copies remain available. Manual correction and readonly rechecking are supported. Smoothly wrong placement, collisions and mechanically incorrect bending can escape this test.

## Optional modules

Two forearm twist helpers are off by default. Helpers are sibling leaves under the respective upper arm with the forearm's exact rest frame; core parentage remains unchanged. A reduced axial quaternion twist is combined with full swing. Graded proximal weight transfer excludes digits, explicit rigid regions, protected rows and locked influences. Blender generated/exported Generic Actions bake helpers; manual pose updates are explicit. Arbitrary Unity Humanoid playback uses an opt-in LateUpdate component after Animator evaluation, with an explicit playback-prefab creation command. Custom IK ordering and optimized transform exposure remain the integrator's responsibility.

Eyes/jaw/socket modules are artist-placed at the 3D cursor on new character copies. Eyes/jaw map to Unity slots and initially have zero influence for explicit painting/rigid assignment. Sockets are nondeforming. AI face-joint detection, facial animation and collision/contact-aware grasp synthesis are not promised.

## Motion and export

Pinned Kimodo/SOMA-30 native inference uses local F32 motion and Q8 text weights. Accepted A/T rest calibration, neck collapse, quaternion continuity and keyed basis scale/location produce editable Actions at scene FPS. Generation is deterministic for recorded parameters but does not promise arbitrary prompt semantics. No generated fingers; open/relaxed/fist/point/grip plus individual curl controls supply editable local-axis poses.

Root stores first-relative planar travel and optional heading, enabled by default. Hips stores vertical sway/jump height. In-place removes planar travel. Flat-ground contact correction uses analytic two-bone IK and bounded pelvis lowering; unreachable contacts are reported. Loop finishing copies the Action and blends the endpoint, preserving Root travel. It is not a contact-phase/velocity-aware cycle optimizer.

Export writes a new bundle containing character FBX, selected direct bone Action/slot FBX, textures where available, and versioned JSON manifests. It preserves source scene/rest/paint/morphs and samples in an isolated temporary scene. Export-only four-influence pruning and a tested 0.001 floor match Unity import behavior. No NLA/all-Actions export. Existing bundles are never overwritten. Base geometry is deliberate: modifiers/constraints/drivers, object-transform animation, negative/nonuniform rig scales, shape-key animation and arbitrary shader translation require preparation or a separate future capability.

The explicit Unity companion checks hashes, matching source Avatar and hierarchy/rest signature, applies semantic mapping and calibrates a disposable T-pose. It keeps transform hierarchy and disables compression/optimization for validated initial import. Generic preserves baked motion. Generated Humanoid clips need the companion's editable `.anim` with explicit MotionT/MotionQ curves to avoid body-projection travel drift. Basic Humanoid needs no runtime component. Import/reconfiguration does not overwrite an already edited generated clip.

## Runtime and installation

One local job runs at a time per extension instance. Heavy inference, large provider hashes and heat solve run in owned hidden processes. Windows Job Objects cancel installer descendants; Escape cancels inference. Each phase applies through a short undo operator to independent copies. Scene/source-pointer/digest checks reject stale application. Loading a project into another process requires a fresh request; existing finished copies remain ordinary editable Blender data. Completed phases survive cancellation and only successful workflows hide their source/intermediate copies.

A separate provider archive contains verified native binaries, corresponding source and dependency notices. Explicit setup downloads eight pinned model files and twelve pinned runtime wheels with size/SHA checks and resumable transport. No compilers, SDKs, cloud account, SMPL-X training assets or proprietary runtime are required. Python 3.11/NVIDIA driver remain prerequisites. Allow approximately 30 GB initial free disk space.

Blender code is GPL-3.0-or-later; the independent Unity companion is MIT. Source/model licenses retain their own terms. The Kimodo text encoder uses Meta Llama 3 terms and SOMA weights use NVIDIA's Open Model License, so the complete weight stack is not unrestricted OSI open source. License texts/model notices are preserved. Private test data are local-only, not training or redistribution assets.

## Acceptance and boundaries

The implemented path has real local inference, fresh-cache installation/inference, independent Blender/Unity LBS and root-motion checks, A/T and uniform-scale contact tests, close-finger/ring/rigid geometry tests, paint/joint persistence, stale/corrupt/duplicate rejection, cancellation, optional modules and external-avatar transition/twist/prefab checks. Three private avatar families include normal Shane, fragmented Cardboard Boy and mechanical T-800. Imported references are comparisons, not ground truth. Quantitative passes do not replace deformation/joint review.

Final additional coverage: Hazmat female passes actual MIA/SkinTokens/Kimodo, sampled posed visual review, and both Unity profiles. Camera/tripod fresh AI placement fails visually despite accurate Blender/Unity parity; the new gate reproduces and blocks this failure. Imported-joint/paint reuse removes its gross tearing and passes both Unity profiles, but mechanical hinge semantics still need artist review. This failure is retained in release evidence, not relabeled as a successful automatic rig.

An RTX 4090 24 GB was tested; a 16 GB card was unavailable. A sampled device peak includes the desktop and other apps, not a precise inference allocation. Original/native model parity and comprehensive correction-time benchmarks remain unmeasured. These limit claims about quality/hardware, not access to the implemented local workflow. Later independent work: creature/UniRig provider, free cloth/secondary motion, facial synthesis, generalized grasp/contact constraints, terrain contacts and phase-aware loop optimization.

Supporting research: [local AI options](local-ai-rigging-and-skinning-research.md), [adaptive skinning challenges](adaptive-local-skinning-design.md), [private corpus inventory](reference/avatar-test-corpus.json), and [isolated Blender geometry audit](reference/avatar-blender-audit-2026-10-03.json).
