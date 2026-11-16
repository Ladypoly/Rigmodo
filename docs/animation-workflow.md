# Rigmodo animation workflow — 0.18.0

Open **Rigmodo** in the 3D View header or sidebar. Select the character and click **Use Selection**. This pins its rig and mesh scope, so selecting a floor, light, or another object does not redirect an animation job.

The main steps are **Rig · Skin · Animate**. Animate contains **Create · Browse · Edit**. Provider paths, model setup, ComfyUI profiles and recovery tools stay in Extension Settings. Existing rigging, skinning, image posing, key poses, creature generation and the native motion library remain available.

## Create

- **Description → 3D motion:** Kimodo on an accepted Rigmodo humanoid, or UniMate on a creature. Ordinary timeline pose keys can guide humanoid generation. The result is applied to the original character; keeping separate review copies is an optional preference.
- **Description → Video to motion:** send a configured API workflow to an already running ComfyUI, retrieve its exact video output, then capture, retarget and finish an Action. Use a disk reference image or **Use Character Image**. The latter renders in a disposable scene without adding cameras or floors to the character scene.
- **Video:** choose a continuous full-body humanoid clip, its start time and duration. GEM-X runs in a separate local environment. Capture creates a reusable skeleton and contact confidence independently of the target avatar.
- **Pose keys:** insert ordinary keys and generate transitions with MotionBricks. Artist anchors and their timeline start are retained. Loop endpoint poses must agree; incompatible anchors produce a clear error.
- **Animation:** select a source rig and Action, or an FBX, BVH, GLB, glTF or Blender file. Files import in an isolated Blender process with automatic scripts disabled. Multi-animation files go through the motion library so the artist can choose the clip.

Use **Loop** for cycles and leave it disabled for attacks, deaths and other one-shots. **In place** removes net horizontal travel while retaining vertical movement and body sway. Generation uses physical timestamps rather than assuming the scene runs at 30 fps. The H3 profile displays its actual output duration.

## Edit and automatic foot contacts

**Open Motion Editor** creates a focused 3D View plus source-video or animation editor. Its header offers **Finish Editing**; invoking it through the interface also supports Escape. Closing restores the previous selection, mode and frame and joins only the area Rigmodo created. The rig, Action and intentional edits remain. Cyan viewport points mark the estimated heel and forefoot.

Bone mapping recognizes common game-rig names and supports explicit saved role overrides. Hierarchy/geometry suggestions require review; the proposed assignments are visible before acceptance. Different central spine counts are interpolated along the spine. Rest bones, weights and proportions remain fixed. Constraints, drivers and unsupported mirrored/nonuniform scale are rejected with preparation instructions.

Automatic contacts combine learned probabilities, sole clearance, foot speed and interval continuity. The solver aligns one estimated floor, applies bounded pelvis correction and two-bone leg IK, and retains jump flight. It works on flat ground; world Z=0 is the default, with a ground-height override. In-place clips retain their treadmill-style foot travel. Explicit planted intervals can lock a chosen support point instead.

Expand **Contact correction** to inspect intervals and mark a range as **Planted**, **Sliding** or **Airborne**. Later overlapping overrides take priority. Reset overrides when needed, then run **Correct Foot Contacts** to create another Action. Use **Heel at Cursor** and **Forefoot at Cursor** to calibrate the markers for unusual shoes. Unreachable contacts are reported; inspect them rather than assuming the ankle height measures sole clearance.

## Loops

Loop finishing bakes an editable copy, preserves intended root travel, matches boundary channels and runs contacts over three neighboring cycles before extracting the middle period. Loop diagnostics record position, rotation and velocity disagreement. Clips with a significant residual seam are flagged. A duplicate endpoint is stored while playback uses the existing period metadata.

Video loops offer three advanced methods:

1. **Use whole clip:** finish the selected interval in 3D.
2. **Find repeated cycle:** conservatively compare captured pose, orientation and velocity to choose a repeat. If no convincing cycle exists, request manual trimming or a different method.
3. **Generate closing bridge:** experimental ComfyUI H3 first/last image guidance connecting the clip's end to its beginning. The original video is retained. This does not use the handoff's unlicensed SPEED interpolation model.

New generated H3 loops use matching first/last reference images. Matching images alone are not considered proof of a valid 3D loop. The 24 fps H3 profile uses 17k+5 frames in its trained 124–362 frame range; for example 124 frames are 5.17 seconds, not exactly 5 seconds.

## Library and storage

**Browse** opens Blender's Asset Browser. The Animation menu provides **Save to Library**, **New Empty Animation**, and **Delete Animation**; the search control chooses an existing compatible Action. Shared or linked Actions are protected from deletion. Library previews restore the previous animation and remove only their owned temporary Actions.

Library files retain contact samples and capture provenance, so reapplying motion does not require the model or source video. Jobs and raw provider output remain under `R:\AI\Rigmodo\Jobs`; reusable motion remains under `R:\AI\MotionLibrary\Rigmodo`. Capture weights are under `R:\AI\Models\Rigmodo\gemx`, with a separate runtime at `R:\AI\Rigmodo\Runtime\VideoCapture`. Existing ComfyUI weights are reused in place.

Capture results are cached by source content and capture configuration. **Retry Last Video Job** resumes an unchanged character's failed job and reuses an already generated video. It does not regenerate that video because capture failed. Queue cancellation removes only Rigmodo's known queued prompt IDs. A shared running ComfyUI step is allowed to finish externally; downstream capture/application is cancelled. No global interrupt is sent and another client's queue is never cleared.

## Setup and tested boundaries

In Extension Settings, install or verify **Video Capture**, set FFmpeg/FFprobe, and check ComfyUI at the configured endpoint (default `http://127.0.0.1:8288`). Setup pins source, dependencies and checkpoint hashes. The capture environment does not replace existing rigging, skinning or generation runtimes. Custom ComfyUI workflows must be exported in API format; bind fields using JSON such as `{"prompt":"12.text","image":"20.image","output_prefix":"90.filename_prefix"}` and specify the output node when several videos are returned.

The real two-second avatar capture produced 60 samples at 30 Hz in 26.44 seconds on an RTX 4090, with a 3.42 GiB peak PyTorch allocation. This excludes other applications, driver/ONNX allocation and startup time. A CPU MediaPipe Lite detection baseline processed the 48 source frames in 0.61 seconds, but that was a 33-point detection benchmark, not an equivalent temporal world-motion/contact pipeline. GEM-X is the current quality-path default; no 16 GB hardware claim follows from this test.

Actual video capture, ComfyUI upload/output tracking using a lightweight workflow, library persistence, contacts, looping, exact artist keys and Blender FBX round trips passed. An isolated Unity 6000.3.21f1 project created a valid Humanoid Avatar and played the captured clip as both Generic and Humanoid; the Generic loop seam was zero in that fixture. H3 graph/model schemas were checked against the real server; new H3 sampling and a generated closing bridge were not run in this delivery.

Initial capture supports one visible humanoid in a continuous shot. Likely cuts and ambiguous multiple people are rejected; crop or trim the intended subject before retrying. Diagnostics flag missing tracks and low-confidence ranges. Terrain, moving platforms, control-rig solving, multiple-person selection and creature video capture are not included. GEM-X temporal body capture does not imply reliable animated fingers. Review inferred depth, motion fidelity and contacts on each character.

H3 is an optional externally configured workflow, not a bundled open-source dependency. Its [published community license](https://huggingface.co/MiniMaxAI/MiniMax-H3/blob/main/LICENSE) excludes the EU and other territories from its ordinary grant and describes separate licensing. Private use does not remove those terms. A different permitted ComfyUI workflow can use the same connector.

## RetopoFlow findings

The installed RetopoFlow 3.4.11 uses a modal 3D View session, custom GPU/UI drawing, input routing and explicit Blender UI restoration. Its CookieCutter framework draws an HTML/CSS-like document through viewport callbacks; it is not a new Python-registered native Blender editor type. See the [entry lifecycle](https://github.com/CGCookie/retopoflow/blob/master/retopoflow/retopoflow.py) and [UI implementation](https://github.com/CGCookie/retopoflow/blob/master/retopoflow/rf/rf_ui.py).

Rigmodo follows the useful interaction pattern: a small everyday interface and focused editing sessions, with a clear exit and restored context. Existing landmark/hand editors, native weight painting and Auto Pose remain the rig/skin/pose tools; Motion Editor adds source preview, contacts and sole overlays. This delivery reuses native Blender widgets, timeline and Asset Browser instead of importing RetopoFlow's full UI/undo framework or its non-code assets. A larger custom rig/skin tool palette remains a separate interface iteration.
