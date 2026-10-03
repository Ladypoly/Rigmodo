# Local Character — foundation 0.1.0

Independent Blender 5.2 extension for the planned local AI character workflow. The current build creates an editable Mixamo-style humanoid and exports already-bound characters to Unity. AI placement, new mesh binding, adaptive refinement, optional twists and Kimodo motion are not implemented in this release.

Enable **Local Character** in Blender Preferences → Add-ons. Open the **Local Character** tab in the 3D View sidebar.

## Editable skeleton

Select upright, Z-up character meshes and choose **Create Editable Humanoid**, or disable bounds fitting and choose a height at the 3D cursor. The template faces Blender -Y. Arm drop selects T/A proportions. Adjust the new armature in Edit Mode; it is separate from existing rigs and does not automatically bind selected meshes. Default: 52 deform bones and an unweighted Root. Eyes are optional; twists are disabled.

## Existing character export

Select only the bound meshes you intend to export. Their armature is resolved through the modifiers; selecting it as well is allowed. Run **Check Selected Character**, choose an absolute export folder and a new character name, then **Export Character to Unity**. Relative folders require a saved blend file. Existing bundle directories are never overwritten.

Export uses temporary copies in a separate scene. It retains the imported bone hierarchy, adds an unweighted Root when absent, prunes copies to four influences and normalizes them. Zero/invalid weights block export. Source weights are unchanged. Non-armature modifiers need an explicit working-copy resolution; this release exports base geometry to preserve shape keys. Nonuniform armature scale and mirrored/singular transforms are rejected. No clips are exported yet. FBX includes referenced texture copies where available; arbitrary Blender shader conversion is not provided.

## Unity companion

Copy all C# files in `unity/Editor` into a Unity project's `Assets/LocalCharacter/Editor` directory. Copy the complete exported bundle into Assets. Select its FBX, then choose **Assets → Local Character → Configure Selected Export for Unity**. The explicit command verifies the FBX hash and manifest, applies human mappings, calibrates a disposable skeleton copy in an isolated preview scene, imports four-influence weights and writes a validation/calibration report. It does not automatically reconfigure unrelated assets or overwrite your choices on every reimport. Re-run the command only when you intend to apply the export profile again.

Unity 6.3 LTS is the primary target. Avatar validity alone does not establish good deformation, a correct T-pose, motion retargeting or runtime root-motion behavior; these require the acceptance tests recorded in the build status.

The same import/deformation checks also passed in the user's live Unity 6000.4.3f1 URP project. `ModelPreview.cs` must be installed alongside the importer: it keeps calibration copies out of your open scenes. The optional live test harness in `tests/` has explicit Tools-menu commands and never invokes the batch exit path in an interactive Editor. See build status for the private validation folder and preview scene.

## Development

The extension is developed directly in Blender's `extensions/user_default/local_character` directory at the user's request. Its Git repository is separate from Mesh2Motion. `docs/`, `tests/` and `unity/` are excluded from the Blender extension ZIP; the companion can be copied separately. Private test avatars and exported binaries are excluded from Git.

Blender code: GPL-3.0-or-later. Independently written Unity companion: MIT, see `unity/LICENSE`. No proprietary ARP/VHD code, source avatar template or AI checkpoint is distributed.

The [implementation plan](docs/unity-humanoid-extension-final-plan.md) and [build status](docs/BUILD_STATUS.md) record decisions, actual checks and remaining work. Run `python tests/run_acceptance.py` with a suitable Python installation to create an isolated Blender/Unity test workspace. Optional `--blender` and `--unity` arguments select executables. Tests require the private Shane avatar at its documented local path and an available Unity editor license. Test avatars stay outside this repository.
