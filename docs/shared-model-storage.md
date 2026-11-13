# Shared model storage · 0.16.0

Preferences → Setup → **Shared model storage** selects one persistent directory for all managed Rigmodo weights. On this machine it is **`R:\AI\Models\Rigmodo`**. Fresh provider setup initializes the selected root automatically. Runtime interpreters, CUDA packages, native executables, source and job data stay in `%LOCALAPPDATA%/LocalCharacter`; models alone move.

**Use Shared Model Folder** copies or hardlinks files, verifies SHA-256, and switches the global configuration atomically only after all copies are complete. It then removes only matching owned cache files. Existing different target files stop the operation; external/shared source files are retained. Interrupted copies leave the original paths active; once a completed switch is committed, interruption of cleanup can leave redundant copies but the complete model store remains usable. Retry completes cleanup. A later folder change uses the same verified procedure. Runtime/provider cache nesting is rejected.

The active root is recorded in `%LOCALAPPDATA%/LocalCharacter/model-storage.json` and reused by standalone workers and all installers. Blender-relative or explicitly external custom model locations retain their overrides. Managed default paths resolve to the shared root even for older callers. Missing/unmounted storage does not silently download another model set onto C:. The UniRig file is hardlinked on R: to preserve existing ComfyUI access without duplicating the checkpoint. No directory junctions or administrator-only file symlinks are needed.

Actual migration: 47 model/support files verified. 17,223,622,414 bytes copied from C:; UniRig reused through a same-volume hardlink. After backend validation, matching old managed copies were removed. C: gained about 17.2 GB. MIA, native SkinTokens, Kimodo, UniMate and MotionBricks ran using the shared weights; SAM checkpoint/config/source verification passed. No source character data is changed by storage migration.

## Installed weight sizes

Decimal GB; excludes Python/CUDA runtimes, source, binaries, temporary jobs and small configuration/tokenizer sidecars. These are disk sizes, not simultaneous VRAM requirements.

| File | Size |
|---|---:|
| `kimodo/Llama-3-Kimodo-Q8_0.gguf` | 8.142 GB |
| `kimodo/models/kimodo-soma-rp-v1.1-f32.gguf` | 1.133 GB |
| `kimodo/tokenizer.gguf` | 0.007 GB |
| `mia/joints.pth` | 0.526 GB |
| `mia/joints_coarse.pth` | 0.425 GB |
| `motionbricks/mmm_v6_soma_fp32.onnx` | 0.758 GB |
| `sam-3d-body/assets/mhr_model.pt` | 0.696 GB |
| `sam-3d-body/model.ckpt` | 2.109 GB |
| `skintokens/F16/mesh-encoder.gguf` | 0.058 GB |
| `skintokens/F16/skin-vae.gguf` | 0.244 GB |
| `skintokens/F16/tokenrig.gguf` | 0.949 GB |
| `unimate/text_encoder/model.safetensors` | 0.990 GB |
| `unimate/weights/unimate_uniml3d_f60_v3/checkpoints/checkpoint_step_150000.pt` | 1.186 GB |
| `unirig/skeleton.safetensors` | 1.441 GB |
| **Total** | **18.663 GB (17.38 GiB)** |
