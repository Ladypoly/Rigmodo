# Local Character — foundation 0.3.0

Independent Blender 5.2 extension for a local AI character workflow. This build creates an editable Mixamo-style humanoid, proposes learned skin weights for an accepted rig, and exports characters and selected animations to Unity. AI joint placement, adaptive refinement, optional twists and Kimodo motion remain pending.

Enable **Local Character** in Blender Preferences → Add-ons. Open the **Local Character** tab in the 3D View sidebar.

## Editable skeleton

Select upright, Z-up character meshes and choose **Create Editable Humanoid**, or disable bounds fitting and choose a height at the 3D cursor. The template faces Blender -Y. Arm drop selects T/A proportions. Adjust the new armature in Edit Mode; it is separate from existing rigs and does not automatically bind selected meshes. Default: 52 deform bones and an unweighted Root. Eyes are optional; twists are disabled.

## Existing character export

Select only the bound meshes you intend to export. Their armature is resolved through the modifiers; selecting it as well is allowed. Run **Check Selected Character**, choose an absolute export folder and a new character name, then **Export Character to Unity**. Relative folders require a saved blend file. Existing bundle directories are never overwritten.

Export uses temporary copies in a separate scene. It retains the imported bone hierarchy, adds an unweighted Root when absent, prunes copies to four influences and normalizes them. Influences below the tested Unity importer floor of 0.001 are removed on export copies, retaining each vertex's strongest bone and renormalizing; preflight warns and the manifest records this policy. Zero/invalid weights block export. Source weights are unchanged. Non-armature modifiers need an explicit working-copy resolution; this release exports base geometry to preserve shape keys. Nonuniform armature scale and mirrored/singular transforms are rejected. FBX includes referenced texture copies where available; arbitrary Blender shader conversion is not provided.

## Local AI skinning (experimental)

Select an accepted armature and the meshes to bind. Existing weights are optional and are withheld from inference. Under **Local AI providers**, choose **AI Skin to New Copy**. The prepared local SkinTokens worker runs in a separate process using Vulkan on this machine's RTX 4090. Escape cancels it. Completion creates a new collection containing separate armature and mesh-data copies with learned weights; originals stay in place. Hide one collection when comparing their deformation. Review joints and poses before export.

The adapter preserves accepted joints and original vertex IDs, including UV seam splits. It applies only validated weights to Blender copies, preserving UVs, materials and shape keys. Original geometry/joint/weight edits during inference invalidate the result. Finished jobs can be reapplied in the same Blender session after undo/removal of their previous copies. Jobs and worker logs remain under `%LOCALAPPDATA%/LocalCharacter/jobs`; the last job path is available in scene settings. Loading a file into a new Blender process invalidates its old source pointers; prepare a fresh job.

Default worker/models are already installed locally for this development session. The ZIP contains no checkpoints or native binaries. [Provider setup and evidence](docs/skin-tokens-provider.md) describe the pinned F16 models, isolated Windows build, reproducible helper and current limits. In private fixed-rig tests, 52/67 joints on 7,234 vertices took about 65/84 seconds. Body results passed the reviewed diagnostic poses; finger-tip artifacts remain. This is one avatar, not a broad quality benchmark. No automatic rigid/digit/seam/voxel routing is available yet.

Use an unconstrained deform rig, Object Mode, positive transforms and resolved visible non-armature modifiers on working copies. The initial path supports one deform root and 1–256 deform bones. Structural nondeform parents stay in the Blender rig but are excluded from neural conditioning. Armature modifier masks and envelopes require explicit preparation. CPU mode exists but has not been benchmarked.

## Selected animation

Assign a direct bone Action to the armature and enable **Include armature's selected Action** before exporting. The character FBX stays in its actual rest pose; a separate `Animations/<Action>.fbx` contains only that Action's selected armature slot. Other Actions, other slots and NLA strips are excluded. The range comes from that slot's keys, or the Action's explicit artist range; export samples every frame at the scene frame rate. Optional **Loop clip in Unity** marks looping without repairing discontinuities.

Direct bone translation, rotation and scale are supported. Bone/object constraints, drivers, object-transform animation and custom-property channels need baking to a separate deform rig first. Unkeyed bones use rest transforms. Shape-key animation is not included. Export preserves bone travel; separate in-place conversion, contact correction and animation generation remain future work.

## Unity companion

Copy all C# files in `unity/Editor` into a Unity project's `Assets/LocalCharacter/Editor` directory. Copy the complete exported bundle into Assets. Configure the character FBX first, then each animation FBX with **Assets → Local Character → Configure Selected Export for Unity**. The explicit command verifies the FBX hash and manifest, applies human mappings, calibrates a disposable skeleton copy in an isolated preview scene, imports four-influence weights and writes a validation/calibration report. It does not automatically reconfigure unrelated assets or overwrite your choices on every reimport. Re-run the command only when you intend to apply the export profile again.

Unity 6.3 LTS is the primary target. Avatar validity alone does not establish good deformation, a correct T-pose, motion retargeting or runtime root-motion behavior; these require the acceptance tests recorded in the build status.

The same import/deformation checks also passed in the user's live Unity 6000.4.3f1 URP project. `ModelPreview.cs` must be installed alongside the importer: it keeps calibration copies out of your open scenes. The optional live test harness in `tests/` has explicit Tools-menu commands and never invokes the batch exit path in an interactive Editor. See build status for the private validation folder and preview scene.

## Development

The extension is developed directly in Blender's `extensions/user_default/local_character` directory at the user's request. Its Git repository is separate from Mesh2Motion. `docs/`, `tests/`, `tools/` and `unity/` are excluded from the Blender extension ZIP; the companion can be copied separately. Private test avatars and exported binaries are excluded from Git.

Blender code: GPL-3.0-or-later. Independently written Unity companion: MIT, see `unity/LICENSE`. No proprietary ARP/VHD code, source avatar template or AI checkpoint is distributed.

The [implementation plan](docs/unity-humanoid-extension-final-plan.md) and [build status](docs/BUILD_STATUS.md) record decisions, actual checks and remaining work. Run `python tests/run_acceptance.py` with a suitable Python installation to create an isolated Blender/Unity test workspace. Optional `--blender` and `--unity` arguments select executables. Tests require the private Shane avatar at its documented local path and an available Unity editor license. Test avatars stay outside this repository.
