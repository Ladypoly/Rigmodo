# Local motion library

Rigmodo stores motions in `R:\AI\MotionLibrary\Rigmodo` by default. Change the folder in the extension preferences. Models remain in the separate shared model folder.

## Browse and apply

1. Select your character's armature. Open **Motion → Animations → Motion Library**.
2. Blender's Asset Browser opens with **Rigmodo Motions** selected. Use its catalogs and search to find a clip. Each thumbnail shows three sampled poses; it is a static thumbnail, not an animated GIF.
3. Select a motion and click **Apply Motion** or the **Play** icon in the browser header. The right-hand **Rigmodo** panel also offers these controls and a **Character** selector.
4. Adjust speed, trim in seconds, mirror, in-place movement, looping, and humanoid arm spacing. Confirm **Apply Motion** to create an editable Action on the character.

Use Rigmodo's **Apply / Adjust** for full-clip retargeting. Blender's ordinary pose-library operations may apply only one pose; dragging an Action onto an editor does not run Rigmodo's retargeter. Full clips are stored as genuine Action assets and can also be appended normally onto a matching skeleton.

Preview temporarily replaces the active Action. **Restore Previous Animation** or cancelling the adjustment dialog restores the previous Action and frame. Applying retains the previous Action. Neither applying nor previewing creates a new mesh or armature in your scene.

Humanoid retargeting supports recognized Mixamo-style and Mesh2Motion humanoid bone names, with rest-pose calibration and limb-length scaling. Anonymous skeleton mapping and contact-aware IK are not part of this release. Creature motion reuse requires a matching skeleton. Importing Spider motions does not make them compatible with an unrelated Scorpion rig.

Loop controls playback/export intent. It cannot make an arbitrary trimmed motion seamless; use the existing loop cleanup when needed. Attack and death clips default to one-shot playback.

## Add motions

- **Import Files** accepts multiple FBX, GLB, glTF, or Blender files. **Import Folder** optionally includes subfolders. Import runs in a separate Blender process with automatic Python execution disabled. Repeated files and identical motions are skipped.
- Enable **Mixamo downloads** only for files downloaded from Mixamo; source rights are never inferred from bone names. Other imported files retain user-provided provenance.
- **Save Current Animation** stores the selected armature's active Action, including Rigmodo-generated motions. Enter a name and optional search tags. The original scene is not saved or replaced.
- **Get CC0 Motions** downloads the pinned Mesh2Motion starter assets and verifies each source file's size and Git blob hash. The current source set produces 325 animated clips across nine character families; a static Shark pose is skipped. These assets are CC0: <https://github.com/Mesh2Motion/mesh2motion-app/blob/main/LICENSE-CC0.MD>.

Assets and catalog changes appear after the worker finishes. If needed use Blender's **Library → Refresh**. You can create additional native catalogs in Blender; Rigmodo preserves existing catalog entries. Rename the editor or close the split through Blender's ordinary area controls when finished.

## Optional Mixamo batch downloader

The separate tool is installed under `Tools\MixamoDownloader` and saves to `Downloads\Mixamo` inside the library. It uses pinned MIT source from <https://github.com/underfusion/mixamo-downloader> and its own Electron runtime. Node.js 22 or newer is required for setup. Choose **Mixamo Downloader**, log in directly to Adobe, select the appropriate character/rig, and download. Then use **Import Folder** in Rigmodo.

This is an unofficial tool. Adobe's current terms restrict scraping and unauthorized interfaces, and account access may change. No Adobe credentials or downloaded motions are included in Rigmodo's repository. The no-login renderer has been tested; authenticated batch downloading has not been tested in this release. Mixamo assets remain subject to Adobe's terms and must not be redistributed as a standalone motion collection.

## Storage and recovery

`catalog.json` indexes validated `clips/<id>/motion.npz` files and previews. `Assets/<id>.blend` holds complete Action assets for Blender's native browser. `Sources` retains starter-source provenance; `Downloads` contains your downloads. This derived Action representation supports native browsing; the sampled source matrices remain available for proportion-aware retargeting. No AI models are copied into this library.

Imports commit one clip at a time under a cross-process catalog lock. Cancelling keeps completed clips. Failed/incomplete assets are not offered as valid motions. Keep the entire library together when moving it, then update the extension preference and reopen Motion Library. Scene Action deletion does not delete your library source files.
