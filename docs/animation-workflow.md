# Rigmodo animation workflow — 0.20.0

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

Choose **Engine → ExMR · body and hands** for the optional RGB MoCap backend, or **GEM-X** for the existing capture runtime. Both work independently of a target avatar and feed the same reusable-motion/retargeting workflow. The engine applies to uploaded videos and ComfyUI-generated videos.

ExMR setup is external: use a Git checkout of [RGB MoCap](https://github.com/toyxyz/toyxyz_RGBMocap/tree/42844135d0612c7e574fd43f6c42414f5fce1219) at the pinned revision and run its supported `install.cmd`, then use its model manager to download ExMR dependencies and import your registered `SMPLX_NEUTRAL.npz` and `MANO_RIGHT.pkl`. Set **Extension Settings → RGB MoCap folder**. The local test installation uses `R:\AI\Rigmodo\Providers\RGBMocap`, with `models` linked to `R:\AI\Models\Rigmodo\RGBMocap`; existing byte-identical SAM weights are shared. The adapter validates its revision, uses the provider's separated private runtimes and never installs Torch into Blender. Registered models and upstream research/model terms remain separate from Rigmodo's license. No model weights are bundled.

ExMR runs subject tracking, temporal body/hand inference with global smoothing, source foot correction, and the provider's Mixamo-style skeleton export. Rigmodo imports that BVH in isolated Blender through its existing importer. The raw provider project, source diagnostics and corrected capture remain in the job. The target contact pass then adapts the motion to the target's proportions. Global provider smoothing is recorded to avoid filtering the same capture twice.

Stage counters come from completed provider work. Estimated time is **for the current stage**, and appears only after measurable progress; model loading/one-pass stages may have no percentage. Cancellation terminates the owned worker tree. GPU workers exit after processing rather than remaining resident.

In **Video to Motion → Video files**, choose a single video or **Batch capture videos…**. Whole-video capture accepts up to 60 seconds per file, with at most 200 files in one batch. Turn off **Capture whole video** for a selected interval. Clips process sequentially; failed files are reported without discarding completed clips. Identical captured results are reused. Each capture process exits between files, releasing its GPU allocations.

**Video to Motion → ComfyUI** generates a reference video, then captures it to the library. Use an image from disk, or render the selected character into a disposable reference scene. An avatar is optional. Configure the existing local ComfyUI endpoint and either its built-in H3 profile or a custom API-format workflow in Settings. Bind inputs with JSON such as `{"prompt":"12.text","image":"20.image","output_prefix":"90.filename_prefix"}`; specify the output node when a workflow returns several videos. Existing ComfyUI checkpoints are reused in place.

Captured motion and raw provider output remain in the job folder under `R:\AI\Rigmodo\Jobs`. Creation and capture failures do not require retargeting again; finished library motions are independent of the generator and original video. Completed batch clips survive cancellation. Use Refresh if a cancelled batch added clips before stopping.

## Retarget to one or many characters

1. In **Retarget**, use **Load from library…** to select external Asset Browser motions, then **Use for retargeting**. Newly generated/imported motions are loaded explicitly as well; opening Retarget never loads the full catalog. The × button unloads working sources without deleting library files. Search and tick those source motions. With no boxes ticked, the highlighted row is the active source. **Preview source** uses a disposable skeleton; Stop removes it and restores selection, frame, preview range and playback intent.
2. Choose a **Character**, or enable **Use all selected characters** to apply each source to each selected rig. Selecting bound meshes also identifies their rigs.
3. Choose source playback, Loop, or Play once; optionally enable In place. Click **Retarget motions**. Each target gets its own editable Actions; source clips, rest bones, proportions, meshes and weights remain intact.

**Motion adjustments** contains speed, mirror, humanoid arm spacing and **Stabilize video motion**. Stabilization filters local capture channels before target foot correction and preserves the raw source. ExMR global-smoothed captures skip this additional filter. Trim is available for a single source; a multi-source batch uses complete clips. **Retarget options** contains automatic foot placement, ground height, reviewed bone mapping and contact overrides. The current-animation selector supports previewing, deleting and saving created Actions. An existing scene rig/Action can be retargeted under **Scene animation / image pose**.

Mapping recognizes common game-rig names and supports saved role overrides and different spine counts. Geometry/hierarchy suggestions require review. Unsupported constraints, drivers and mirrored/nonuniform scales produce preparation instructions rather than modifying the rig.

Automatic contacts combine learned confidence, sole clearance, speed and interval continuity. Quiet stances level heel and forefoot together and relax the toe joint to its rest orientation; rolling support and airborne phases remain separate. Contacts reaching the first or last clip sample have full support. Reapplying correction retains learned contact probabilities. The solver uses bounded pelvis correction and leg IK while retaining jump flight. Confident support can estimate slow vertical capture drift; airborne overrides and low-confidence gaps retain flight. A consistent heel/forefoot support point is retained through each plant to avoid marker-switch pops. It assumes a flat floor, default world Z=0. Set ground height and heel/forefoot markers for unusual shoes. Explicit Planted, Sliding or Airborne intervals override automatic choices; later overlapping intervals take priority. Review reported unreachable contacts. Terrain and moving platforms are not supported.

### Live foot indicators and optional refinement

**Retarget options → Show foot contacts** draws floor discs and labels: green for planted, amber for rolling/sliding, gray dashed for airborne, red for a missed expected floor contact or penetration. These are view-only markers based on the evaluated foot pose and calibrated sole points; they do not simulate contact or add objects. Blender’s Overlay toggle hides them. The static overlay draws at most 160 vertices per foot and runs no inference.

Select a character animation, open **Motion adjustments**, then **Refine current clip with MotionBricks…**. Start with Strength 0.35 and Guide spacing 0.5 seconds. Clips must be 0.5 seconds to just under 30 seconds, on an accepted unconstrained humanoid deform rig. At most 32 guide poses are sampled, with gaps adjusted to the model’s 0.5–2 second range. Existing local MotionBricks weights are reused; no extra checkpoint is needed.

The isolated worker samples sparse source poses, generates body transitions and filters the generated local body channels with a centered 100 ms Gaussian. Strength blends those transitions into the source. Source Root transforms, local translations, Hips rotation, finger motion and planted-leg poses are retained. Source support intervals become editable contact overrides, with existing artist overrides taking priority. Target foot placement and optional loop finishing run afterward. A separate **· MotionBricks** Action appears; the source Action, rig, mesh and weights remain unchanged. Editing the source while inference runs rejects application rather than overwriting those edits.

This is pose-guided resynthesis, not a physics solver: it does not enforce balance, collisions, prop grip or terrain contact. It can alter gesture detail, and a clean capture may look better without it. In the mummy fixture, unfiltered resynthesis increased jitter; filtering and retaining support removed that regression in the high-frequency jerk proxy, while the acceleration proxy remained slightly higher than the source. Review both clips rather than treating the result as automatically more realistic. Flat floor support still requires a reachable leg chain.

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

Video capture currently supports one visible humanoid in a continuous shot. Cuts are rejected; crop or trim first. GEM-X rejects ambiguous multi-person detections. ExMR uses the upstream primary track and cannot disambiguate several actors through this adapter, so supply a single clearly visible person. Creature video capture, terrain contacts and control-rig solving are outside the current capture scope. ExMR infers fingers; small, occluded or stylized hands still need review. GEM-X does not provide the same dedicated hand-refinement path. Prop tracking, two-hand staff constraints and collision solving are not automatic; attach rigid accessories deliberately and review grips. Review inferred depth, anatomy, collisions and contact quality before export.

### ExMR acceptance on the supplied mummy

On 2026-11-16, the supplied eight-second MiniMax video produced 240 samples at 30 Hz, with all 30 finger joints articulating. Capture, library save and target retargeting completed in about 64 seconds on the RTX 4090; peak PyTorch allocation was 5.68 GiB. Native-to-BVH joint-position error was below one micrometre. Target foot correction reported 393 contact samples and zero unreachable samples. These are measured solver/integration results, not ground-truth accuracy guarantees.

The stylized subject caused 86 detector gaps; the provider interpolated their boxes and inferred every frame. The UI retains a capture-review warning. Native Blender playback passed, and the final review copy contains the skinned body, game rig and a rigid staff attachment. The staff was calibrated upright at frame 1; its two-hand grip still needs manual polish. Video world heading can differ from Blender Front, so the review uses the camera-facing Back view. The original video and model were not overwritten. See [the acceptance record](rgbmocap-acceptance-2026-11-16.json).

### Actual physics refinement experiment

The local ProtoMotions/MuJoCo mummy test completed, but was not promoted to an addon control: its controller changed the fast staff strike substantially and raw target foot placement regressed. The original and experimental comparison remain available. See the [measured experiment and limitations](protomotions-mummy-experiment.md).
