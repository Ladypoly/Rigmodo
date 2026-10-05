# Pose from Image

Select the accepted humanoid armature. In Rigmodo's **Motion** tab, drop one
PNG/JPEG/WebP/BMP/TIFF image onto the sidebar, or click **Choose Image…**. Use
one clearly visible person, with the desired body and hands in the image.
The local worker applies the resulting pose at the captured timeline frame.
Inspect the result, refine it using Auto Pose, then **Capture Pose** for Kimodo
or **Insert Pose Key** to author animation. Applying the image alone does not
insert keys or replace an Action. An existing Action evaluates again on a frame
change, reload or render, so capture or key the pose before those operations if
you want to retain it. Undo restores the previous pose.

## Installation

The optional provider has its own Python 3.11/CUDA environment outside Blender.
In Extension Settings → Setup → Pose from Image, open **Model Access and
License** and request access to `facebook/sam-3d-body-dinov3`. After approval,
authenticate Hugging Face locally or download that model's `model.ckpt`,
`model_config.yaml` and `assets/mhr_model.pt` into the chosen checkpoint folder.
Then click **Install Image Pose Provider**. The installer uses an existing local
Hugging Face login when downloads are needed; it does not submit access requests,
accept gated agreements, collect tokens in Blender, or upload images.

The NVIDIA GPU needs a compatible CUDA driver. Python, PyTorch and sources are
installed separately, with hidden child processes. SAM follows its pinned
configuration's bfloat16 backbone and uses the portable official TorchScript MHR
model. On an RTX 4090, the tested full-body/hand request took 13.85 seconds
including startup and integrity checks, with 3.38 GiB peak Torch allocation.
Body-only took 12.37 seconds and 3.36 GiB. These are one-image measurements,
not total device VRAM usage or proof on a physical 16 GB card. Source/checkpoint pins and model hashes
are in `sam_pose_protocol.py`; source and checkpoint verification runs in the
worker before loading. DINO source is local and pinned, preventing torch.hub
from fetching mutable code during inference. Detector, SAM segmentation and
MoGe camera estimation are omitted: this version treats the full image as one
person crop. Image orientation follows EXIF, RGB input is bounded to 2048 pixels,
and input file size/pixel count are limited. Prefer images cropped to one person.

## Pose transfer

The worker exports named MHR joint global rotations and a neutral calibration
evaluated with the same inferred shape/scale. It emits neither a mesh nor an
armature. SAM's joint rotations retain unflipped MHR Y-up coordinates even though
its exported joint positions flip Y/Z; the protocol explicitly uses MHR Y-up.
Retargeting converts that frame to Blender Z-up, collapses MHR's extra spine,
wrist-twist and ankle articulation through their accumulated rotations, and
calibrates neutral arm/finger directions against the character's own bone rolls
and A/T bind pose. Accepted bone lengths, Root transform and hip location remain
unchanged. Optional twist helpers are recomputed; other optional bones retain
their authored channels. **Defaults → Infer hand pose** can preserve the fingers.

No source translations, model shape/scale or perspective depth are applied.
This is a pose transfer, not a reconstruction of the person's ground position.
Different proportions can produce foot penetration or mismatched hand contacts;
use Auto Pose afterward. One image cannot resolve hidden joints/depth reliably.
Face/expression animation, multi-person selection, masks, image landmark prompts
and video capture are outside this version. Constrained/control rigs are rejected
using the existing accepted-humanoid validation.

## Transactions and UI

FileHandler accepts image drops only in the active **Rigmodo** sidebar's Motion
step, with a selected armature in Object/Pose Mode. It does not claim image drops
in the viewport, image editor or other sidebar tabs. Blender's built-in reference
image handler also polls sidebar drops. A reversible, scoped adapter makes that
stock handler yield only the active Rigmodo Motion sidebar with a selected
armature, allowing direct drop-to-pose. Its original behavior elsewhere stays
intact, and unregister restores the original method. If a third-party handler
also claims this region, Blender may still offer its native choice menu.
The same import operator
supports the file picker. Job cancellation terminates owned processes, and file
load, Undo, Redo or extension unregister cancel pending work. Rest/world/frame,
pose channels, armature identity and Action assignment are fingerprinted before
launch; a changed target rejects completion without overwriting the artist's pose.
Results and inputs are hash-bound to the original request, validated completely,
retargeted before writing, and applied by a separate Undo-owning operator.

## License and validation limits

Rigmodo's independently authored protocol, UI and retargeter remain GPL-3.0-or-later.
SAM code/checkpoints use Meta's SAM License, with usage restrictions; they are an
optional separately licensed provider, not bundled GPL assets or unrestricted
OSI-open-source models. DINO source/license is retained in its external folder.

Approved pinned checkpoints are installed on this development machine. Real SAM
inference passes for the upstream dance example in body/hand and body-only modes,
with 52 valid joint rotations applied to the existing 6,598-vertex avatar.
Geometry, rest joints, Root placement, object counts and Action assignment stay
intact. A separate real-inference GUI test passes native file-drop dispatch,
asynchronous application, whole-pose Undo/Redo and Kimodo capture. Visual review
matches the example's raised arm, lifted knee and torso lean; occluded fingers and
exact contacts still need artist review. One demonstration is not a statistical
pose-accuracy benchmark.

Numerical calibration/transaction acceptance continues to use the public
Apache-2.0 MHR model with authored parameters. The original GUI cancellation and
stale-target tests use a clearly identified simulated worker; those receipts do
not claim neural prediction. See the dated image-pose acceptance receipt for
separate real and simulated evidence. Downloads used ephemeral authentication;
no token is stored in Blender, source, job requests or a Hugging Face login.

Primary sources: [SAM source](https://github.com/facebookresearch/sam-3d-body),
[installation/access](https://github.com/facebookresearch/sam-3d-body/blob/main/INSTALL.md),
[SAM license](https://github.com/facebookresearch/sam-3d-body/blob/main/LICENSE),
[MHR](https://github.com/facebookresearch/MHR),
[Blender FileHandler](https://docs.blender.org/api/5.0/bpy.types.FileHandler.html).
