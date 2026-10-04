# Local Character Kimodo key-pose adapter

Independently authored Apache-2.0 entry point against kimodo.cpp revision
5679ff19ba0a522c0b0516e9a9d402fe1af2c027, GGML
8c63e70982c95ceb862e3a1073a2c1beef75d60a. It exposes the existing conditioned
DDIM sampler without editing the pinned sources or replacing kmd-generate.

Build using tools/build_keyframes_windows.py with the existing pinned native
build and VS 2022 ClangCL. Release users install the prebuilt provider archive.
The executable shares its pinned GGML Vulkan/CPU DLLs and existing SOMA F32 /
Llama Q8 weights. No extra model downloads or Python inference dependencies.

Arguments: MOTION TEXT PROMPT FRAMES STEPS SEED OBSERVED MASK HEADING OUTPUT.
OBSERVED and MASK are little-endian float32 [frames,369] SOMA30 feature arrays,
in the upstream representation before normalization; MASK is binary. Only
masked values influence conditioning. This adapter normalizes using model
statistics and performs real constraint/text/unconditional separated CFG.
Output uses the original port's root-position and local-xyzw transport.

The extension prepares full-body position, root and heading constraints plus
hand/foot global orientation constraints. Full-body local rotations are not
all directly constrained by upstream FullBodyConstraintSet. Body movement
between anchors is model output. Blender applies a four-sample local residual
correction and restores exact authored transforms; unsupported finger/helper
channels interpolate artist poses. Raw model residuals remain in job reports.

Models retain their own NVIDIA Open Model / Meta Llama licenses. Adapter
license: Apache-2.0; Blender extension: GPL-3.0-or-later.
