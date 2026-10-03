# Local Character

Independent Blender 5.2 extension for local humanoid joint placement, AI skinning, regional correction, generated motion and Unity export. No ARP, proprietary Voxel Heat Diffusion, Mesh2Motion or cloud account is required.

## Start

Enable Local Character in Preferences and open its 3D View sidebar tab. Select one character's meshes in Object Mode, upright Z-up and facing Blender -Y, preferably in an A/T pose with separated fingers. Enter a motion description and press **Build Character**. The sequential workflow runs MIA joint placement, SkinTokens binding, finger correction, optional twists and Kimodo motion. Automatic export is optional: choose an absolute folder and a new character name. **Preview Selected Motion** sets the playback range.

Default rig: 52 Mixamo-style deform bones and an unweighted `Root`. Corrected accepted joints are reused by default. An imported humanoid missing Root receives it on a copy while preserving its accepted joints and paint. Incompatible accepted rigs explain the required preparation; they never silently become AI proposals. Disable **Reuse accepted joints** for a fresh geometry-only proposal. **Rebuild AI weights** reruns binding while retaining protected paint and locked weights. Results use independent armature/mesh-data copies. Originals/intermediates are hidden only after success and remain recoverable. Escape cancels the worker and retains completed phases. Source edits during inference invalidate application.

Open **Joint, skinning and export controls** for individual operations. Review joint proposals in Edit Mode; **Lock joints** preserves selected heads/tails through later proposals. Owned core-rig paint survives a joint reproposal, but the resulting deformation needs review. Extra deform modules prevent replacement by a core-only proposal. Bind/refine the core before adding twists.

The workflow probes edge stretching before motion/export. Severe findings pause automation and retain selected correction copies. Correct joints or region weights, then use individual motion/export controls or rebuild with reuse enabled and AI rebinding disabled. **Check Deformation** repeats the diagnostic. **Allow severe deformation findings** is an explicit expert override. The guard catches extreme tearing, not every misplaced joint, collision or mechanical bend; inspect actual poses. A camera/tripod avatar failed fresh humanoid AI placement despite correct export parity, but preserving its imported rig removed the gross tearing. Its mechanical hinges still require explicit rigid-region review.

## Provider setup

Providers are installed on this development machine. Fresh Windows x64 installation requires Blender 5.2, a suitable NVIDIA driver and **Python 3.11 x64**. Install the extension ZIP; in its controls select Python 3.11 and the matching `local_character-windows-providers.zip`, then **Install Local Providers**. Setup verifies native binaries/source, downloads pinned checkpoints and creates an isolated CUDA PyTorch environment without changing base Python. The prebuilt runtime needs no compiler, Vulkan SDK or proprietary add-on.

Allow about **30 GB free disk space** for 11.48 GB of checkpoints, the 3.27 GB Torch wheel, expanded runtime, jobs and exports. Interrupted downloads resume and are hash-checked. Setup uses network access; subsequent inference is local. Cache: `%LOCALAPPDATA%/LocalCharacter/providers`; job records/logs: `%LOCALAPPDATA%/LocalCharacter/jobs`. New Blender processes require fresh requests because source pointers change. Remove old completed job folders manually when their review records are no longer needed.

The actual fresh-cache three-provider avatar workflow passed on RTX 4090 24 GB in about 137 seconds. A separate sampled run observed total device usage peaking at 11,923 MiB, including other applications. This suggests consumer headroom but is not a measured 16 GB hardware guarantee. Reduce skin search beams if memory is tight. CPU SkinTokens exists but is unbenchmarked; MIA requires CUDA and packaged Kimodo uses Vulkan.

## Regional skinning

**Auto regions** retains AI body weights, restricts confident digits against neighboring fingers and refines their surface graph. Verified boundary seams may temporarily link render-vertex splits; position alone never joins touching fingers or garment layers. Ambiguous seams stay separate. Disable seam linking when its movement assumptions are inappropriate.

**Surface heat** refines valid existing weights. **Surface distance binding** also binds unweighted geometry. **Volume heat with surface details** checks welded topology/occupancy before bounded interior diffusion; digits use surface distance. Open/nonmanifold surfaces, inconsistent winding, overlapping closed shells and unresolved details fall back with a report. These independent graph solvers are not proprietary VHD, cotangent heat or BBW implementations. Geometric limits: 150,000 vertices/600,000 edges per mesh and bounded 24–64 grid resolution. General self-intersection detection and cloth simulation are absent.

For robots, explicitly enable **Treat meshes as rigid character parts**, or select **Rigid mesh parts** during refinement. Confident connected parts receive one AI-suggested bone; ambiguous parts retain paint. Accepted assignments become persistent policies. This requires an artist declaration of rigidity: geometry alone cannot determine intended movement. For a ring, plate or wrong proposal, select vertices in Edit Mode, return to Object Mode, choose **Rigid attachment**, pick the bone and **Mark Selected Region**. Latest policies win. Clear selected policies to revise a region.

**Protect** freezes normalized selected weight rows; Blender weight-group locks freeze existing bone columns. Conflicting rigid/locked assignments fail rather than change artist decisions. UVs, materials, vertex correspondence and morphs remain intact. Export prunes temporary copies to four influences and Unity's tested 0.001 floor; source paint stays editable.

## Bones and motion

Twists are off by default. Two forearm leaf helpers preserve core hierarchy/rest and receive graded forearm paint, excluding protected, locked, rigid and digit regions. Generic clips bake helpers; arbitrary Unity Humanoid playback uses the opt-in companion twist component. **Update Twist Pose** explicitly updates a manual Blender pose.

For eyes, jaw and attachment sockets, put the 3D cursor at the pivot and choose **Add at Cursor to New Copy**. Eyes/jaw map to Unity slots and start unweighted for painting/rigid assignment; sockets are nondeforming. Facial joints are artist-placed, not body-AI predictions.

Kimodo supplies body motion, not animated fingers. Shared curl or individual per-hand/per-finger controls offer open, relaxed, fist, point and grip poses. These use local bone axes, not contact-aware grasp solving. Actions preserve accepted A/T bind and scene FPS. In-place mode removes planar travel; turning goes to Root by default. Jump height stays on Hips while Root follows the ground plane so game physics can own actor height. Foot correction assumes flat ground and reports unreachable contacts. Loop finishing copies the Action and blends its endpoint while retaining Root travel; inspect phase and foot velocity before using it as a seamless cycle.

## Unity

Copy both `unity/Editor` and `unity/Runtime` into `Assets/LocalCharacter`, or extract the companion ZIP there. Keep one companion installation per project; update an existing installation instead of adding duplicate classes. Copy the entire export bundle into Assets. Select the character FBX and run **Assets → Local Character → Configure Selected Export for Unity**, then configure its animation FBX. The explicit command validates hashes, hierarchy/rest compatibility, mapping, disposable T-pose calibration and clip timing. It preserves the bind and does not reconfigure unrelated imports automatically.

For generated Humanoid motion, use the **editable `.anim` created by the companion**. Explicit motion curves preserve the exported Root trajectory; Unity's embedded Humanoid FBX body projection can drift. Reconfiguration preserves `.anim` edits. Enable Animator root motion for traveling playback; use in-place clips for controller locomotion. **Create Humanoid Playback Prefab with Twists** creates a new opt-in prefab. Keep transform optimization disabled. IK/scripts running after the twist component must arrange their own execution order. Generic supports exact baked playback/mechanical hierarchy; basic Humanoid needs no custom runtime.

Export includes only the selected direct bone Action/slot in `Animations`; other Actions and NLA are excluded. Object animation, drivers, constraints, visible non-armature modifiers and nonuniform/mirrored/singular transforms require working-copy preparation. Base shape keys survive, but shape-key animation and arbitrary Blender shader translation are unsupported. Available textures are copied. Existing bundles are never overwritten.

## Evidence and licenses

See [build status](docs/BUILD_STATUS.md) and [implementation plan](docs/unity-humanoid-extension-final-plan.md) for actual tests. Imported rigs are comparisons, not anatomical ground truth. Native ports passed practical acceptance without an official-reference parity claim. Creature generation, secondary cloth and advanced facial animation are outside this humanoid release.

Extension: GPL-3.0-or-later. Independent Unity companion: MIT. Native/model licenses remain separate in provider notices. MIA/3DShape2VecSet code and SkinTokens weights use MIT; the selected MIA model card specifies Apache-2.0. SOMA weights use NVIDIA's Open Model License; Kimodo's text encoder uses **Meta Llama 3 terms**, not unrestricted OSI terms. See `NOTICE`. No proprietary ARP/VHD code, private avatars or checkpoints are shipped in either the extension or native-source ZIP.
