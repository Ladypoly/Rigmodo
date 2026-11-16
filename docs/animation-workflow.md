# Rigmodo animation workflow — 0.19.0

Open the normal **Rigmodo** tab in Blender’s 3D View sidebar (`N`). The main steps are **Rig · Skin · Motion**. Motion contains **Create · Retarget · Library**. Provider installation, paths, sampling defaults and recovery controls live in **Extension Settings** (the cog).

## Create reusable motions

Choose a clearly named system:

| Tab | Input | Needs a scene rig? |
| --- | --- | --- |
| Kimodo | Text, optionally timeline pose keys | Only for pose guidance |
| MotionBricks | Two or more ordinary timeline pose keys | A pose rig; use **New pose rig** if needed |
| Video to Motion | Existing videos, or a configured ComfyUI video workflow | No |
| UniMate | Creature skeleton and a short text prompt | The creature skeleton |

**Generate to library** / **Capture to library** saves reusable motions, thumbnails and native Action assets under `R:\AI\MotionLibrary\Rigmodo`. Creation does not apply an Action to a target avatar. Kimodo and video capture work in an empty scene. Local generation and capture run in owned child processes; inference models are not loaded into the interactive Blender process.

For MotionBricks or guided Kimodo, choose **Use selected** or create a pose rig, click **Edit pose keys**, pose bones and insert normal Blender keys in the active Action, then **Finish pose editing**. Kimodo uses Timeline Start plus Seconds. MotionBricks uses the keyed interval and supports sparse guides 0.5–2 seconds apart. Source Actions remain unchanged. The saved motion starts at time zero, so a guide authored at frame 100 is reusable on other timelines. Exact artist anchors survive source finishing. Conflicting first/last keyed poses are rejected before generating a loop.

UniMate infers facing and joint labels from names and rest geometry. Review ambiguous anatomy; the facing override is under Advanced. The source preserves inferred anatomical labels for creature reuse. The released model supports 15–60 samples at 30 Hz and 5–71 joints including virtual end tips. Creature clips need a matching supported skeleton.

### Video batches and ComfyUI

In **Video to Motion → Video files**, choose a single video or **Batch capture videos…**. Whole-video capture accepts up to 60 seconds per file, with at most 200 files in one batch. Turn off **Capture whole video** for a selected interval. Clips process sequentially; failed files are reported without discarding completed clips. Identical captured results are reused. Each capture process exits between files, releasing its GPU allocations.

**Video to Motion → ComfyUI** generates a reference video, then captures it to the library. Use an image from disk, or render the selected character into a disposable reference scene. An avatar is optional. Configure the existing local ComfyUI endpoint and either its built-in H3 profile or a custom API-format workflow in Settings. Bind inputs with JSON such as `{"prompt":"12.text","image":"20.image","output_prefix":"90.filename_prefix"}`; specify the output node when a workflow returns several videos. Existing ComfyUI checkpoints are reused in place.

Captured motion and raw provider output remain in the job folder under `R:\AI\Rigmodo\Jobs`. Creation and capture failures do not require retargeting again; finished library motions are independent of the generator and original video. Completed batch clips survive cancellation. Use Refresh if a cancelled batch added clips before stopping.

## Retarget to one or many characters

1. In **Retarget**, search and tick source motions. With no boxes ticked, the highlighted row is the active source. **Preview source** uses a disposable skeleton; Stop removes it and restores selection, frame, preview range and playback intent.
2. Choose a **Character**, or enable **Use all selected characters** to apply each source to each selected rig. Selecting bound meshes also identifies their rigs.
3. Choose source playback, Loop, or Play once; optionally enable In place. Click **Retarget motions**. Each target gets its own editable Actions; source clips, rest bones, proportions, meshes and weights remain intact.

**Motion adjustments** contains speed, mirror and humanoid arm spacing. Trim is available for a single source; a multi-source batch uses complete clips. **Retarget options** contains automatic foot placement, ground height, reviewed bone mapping and contact overrides. The current-animation selector supports previewing, deleting and saving created Actions. An existing scene rig/Action can be retargeted under **Scene animation / image pose**.

Mapping recognizes common game-rig names and supports saved role overrides and different spine counts. Geometry/hierarchy suggestions require review. Unsupported constraints, drivers and mirrored/nonuniform scales produce preparation instructions rather than modifying the rig.

Automatic contacts combine learned confidence, sole clearance, speed and interval continuity. The solver uses bounded pelvis correction and leg IK while retaining jump flight. It assumes a flat floor, default world Z=0. Set ground height and heel/forefoot markers for unusual shoes. Explicit Planted, Sliding or Airborne intervals override automatic choices; later overlapping intervals take priority. Review reported unreachable contacts. Terrain and moving platforms are not supported.

## Library and native Asset Browser

**Library** provides the searchable source list, batch file/folder import, saving a character Action, and **Open Asset Browser**. Imported FBX/BVH/GLB/glTF/Blender animations become reusable sources. Native thumbnails/catalogs remain supported. Select one or multiple Rigmodo assets and click **Use for retargeting**; then choose targets in the Rigmodo sidebar. Asset previews require no target avatar.

The existing library is preserved. **Get CC0 Motions** and the optional user-authenticated Mixamo downloader remain in the Asset Browser’s Rigmodo panel. Authenticated Mixamo downloading is unverified. See [the library guide](local-motion-library.md) for provenance and license details.

## Loops and one-shots

Leave Loop disabled for attacks and deaths. Loop finishing creates editable periodic motion while preserving intended Root travel. Retargeting can keep the source’s playback intent or override it. Contact finishing solves neighboring cycles before extracting the middle period; diagnostics retain position, rotation and velocity disagreement. Repeating playback omits the duplicate endpoint.

Video loops offer whole-clip finishing, conservative repeated-cycle selection, or an experimental ComfyUI closing bridge under Advanced. Failed cycle detection requests trimming rather than inventing a repeat. A 3D endpoint match cannot guarantee visually perfect motion, contacts or collision-free transitions. Generated closing-bridge sampling remains untested.

## GPU memory and shared ComfyUI

Rigmodo’s native/capture workers exit after their stage or on cancellation. For ComfyUI, completed owned prompts request idle model unloading before capture, including closing-bridge jobs and failure paths. Queue state and latest prompt/client ownership are checked before cleanup. Cancellation removes only known queued Rigmodo prompts; an already running shared-server job finishes externally and its result is ignored. No global interrupt or queue clearing is sent. A watcher releases the owned cache once it is idle. Because ComfyUI offers no atomic queue-and-free API, a concurrent submission can still race the final check.

**Extension Settings → Video / ComfyUI → Release ComfyUI GPU Memory** manually unloads idle server models and skips busy queues. Other clients’ automatic cleanup ownership is respected. Models load again for the next generation.

## Validation and limits

Real inference passed for unconditioned Kimodo, ordinary-key MotionBricks, video batches without an avatar, ComfyUI video-to-library capture, and UniMate on the saved original Scorpion. MotionBricks guide quaternion error was zero in the acceptance fixture. Two differently sized humanoids received separate Actions, periodic contacts and loop finishing. Native sidebar renders cover all four systems and all three motion stages; rig/skin/landmark/weight UI regression checks passed. Existing Action assets and character/keyed-motion regression checks passed.

The RTX 4090 is the tested GPU. Earlier GEM-X measurements reached 3.42 GiB of PyTorch allocation for the short fixture, excluding other applications, ONNX/driver allocation and startup. No 16 GB hardware guarantee follows from this. H3 graph schemas and the real ComfyUI API path are checked; new H3 sampling was not run. H3 remains an optional externally licensed workflow; see its [published model license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE).

Video capture currently supports one visible humanoid in a continuous shot. Cuts and ambiguous multiple people are rejected; crop or trim first. Creature video capture, terrain contacts, control-rig solving and reliable animated fingers are outside the current capture scope. Review inferred depth, anatomy, collisions and contact quality before export.
