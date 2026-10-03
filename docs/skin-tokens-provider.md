# SkinTokens local provider — experimental 0.3.0

3 October 2026. Actual Windows/Vulkan inference is implemented and exercised on the RTX 4090. This is a fixed accepted-skeleton weight provider, not automatic joint placement or the complete ARP/VHD replacement. Its output is a reviewable copy.

## Exact dependencies and boundaries

| Component | Pin | Published terms / role |
| --- | --- | --- |
| [skin-tokens.cpp](https://github.com/localai-org/skin-tokens.cpp) | `46dbfecda3d9c2dcd87301c9f1127e1f437ed0ed` | Apache-2.0; native CLI worker |
| [GGML](https://github.com/ggml-org/ggml) | `8c63e70982c95ceb862e3a1073a2c1beef75d60a` | MIT; CPU/Vulkan inference |
| [SkinTokens GGUF](https://huggingface.co/LocalAI-io/SkinTokens-GGUF) | `2c55d38ffe01871c6956103926cc4a40bd7acc8a` | MIT-labelled F16 conversions; three files, 1,250,390,624 bytes |
| [Original SkinTokens](https://github.com/VAST-AI-Research/SkinTokens) | `273b691d35989d71cd17ff2895fdc735097b92d1` | MIT; original reference code, inspected only |
| [Source weights](https://huggingface.co/VAST-AI/SkinTokens) | `79736cad0fd84de384d5eede659b4ebd24effe33` | MIT-labelled original checkpoints; not loaded here |
| nlohmann/json 3.11.3 | `9cca280a4d0ccf0c08f47a99aa71d1b0e52f8d03` | MIT; native JSON headers |
| Vulkan-Headers 1.4.326 | `d1cd37e925510a167d4abef39340dbdea47d8989` | Apache-2.0/MIT headers; build dependency |
| SPIRV-Headers SDK 1.4.328.0 | `01e0577914a75a2569c846778c2f93aa8e6feddd` | Khronos MIT-style headers; build dependency |
| shaderc 2026.4, glslang 16.6.0, SPIRV-Tools 2026.3 | isolated conda-forge prefix; shaderc `hef10606_0` | Apache-2.0/BSD-family compiler dependencies; not extension runtime |

The GGUF bundle records Michelangelo encoder, Qwen3-0.6B and SkinVAE origins in its manifest. No unsafe Lightning/pickle checkpoint was loaded, no proprietary addon source used, and no model was retrained. Native source NOTICE records GGML, VAST-AI, NumPy sampler and neighboring ports' attribution. Build/runtime/model licenses remain in the separate provider cache; distribution of native binaries needs a complete transitive notice bundle. This extension package distributes only our Blender adapter, under GPL-3.0-or-later. Source publication labels are recorded here, not a guarantee about every training asset's rights.

F16 file SHA-256 identities are enforced by `skinning.py` before starting a worker:

```
mesh-encoder.gguf 532710809e3db6c54389dd6489c2aa3c768244868b9c197198d06fa664214527
skin-vae.gguf     dcd5859ac89bae62bcfd6b7823f9d0e2393b22364bcb19f84c1109af8e07455e
tokenrig.gguf     933529dc0e550fd499e2e1ae1c574c6d5852047c04832e7207304e184901ed82
```

## Reproducible Windows setup

User checkout `C:\Tools\AI\skin-tokens.cpp` remains clean and unchanged. Source, initialized GGML, model files, compiler helpers and built worker are isolated under:

`C:\Users\Elin\AppData\Local\LocalCharacter\providers\skin-tokens-46dbfec`

Build directory: `C:\LCBuild\st46vk`. Requirements: installed CMake/Git/Conda, VS 2022 Build Tools with ClangCL and a working system Vulkan loader. MSVC's compiler lacks the sampler's `uint128` support; ClangCL avoids changing the PCG64 algorithm. `/EHsc` and `_CRT_SECURE_NO_WARNINGS` resolve Windows compiler settings. The short build directory avoids nested Visual Studio MAX_PATH failures. Shader tools use a separate Conda prefix; the base Conda installation was not updated. The existing system Vulkan DLL supplies exports for a locally generated import library. No Vulkan SDK/system installer was run.

From the extension directory:

```
python tools/build_skin_tokens_windows.py --prepare
```

The helper clones/downloads missing pinned dependencies, checks clean revisions/model hashes, builds the worker and Vulkan backend, stages its DLLs, runs four upstream native tests and inspects the selected device. Its existing-cache prepare/build paths passed here. A completely empty-cache replay has not been separately tested. Omit `--prepare` to rebuild already-prepared dependencies. It writes `build-manifest.json` with build configuration and runtime binary hashes; detailed compilation goes to the provider cache. Do not rebuild/stage DLLs while a skinning job is running. Check the inspect output actually names the intended GPU.

## Job and correspondence contract

`prepare` snapshots world-meter base vertices and triangles, accepted deform joint heads/parents/names, original object pointers, bind matrices, shape coordinates, weight rows and relevant modifier state. GLB Y-up is only a transport coordinate convention. One primitive preserves original vertex IDs; no UV-based reindexing occurs. Placeholder root weights are supplied and ignored by neural binding. The original weights are withheld.

Deform joints are traversed depth-first with sibling order retained. An early breadth-first adapter fragmented limbs into many branch tokens and produced severe artifacts. On the identical 52-joint case, correcting only transport joint order reduced mean forearm-pose difference from 42.16 mm to 0.096 mm. Keep this regression diagnosis: arbitrary parent-first order is insufficient for reliable neural conditioning, even though GLTF accepts it. The accepted Blender skeleton and its bone order are not changed.

The process command uses `skin`, the pinned F16 bundle, explicit `--device vulkan`, `--fit none` and ten search beams. Native default seed is 0. Postprocess and geometric baseline are disabled. Inherited `SKINTOKENS_*` diagnostics are removed before launch to avoid forced-code bypasses; profiling is then enabled. Arguments are a list with no shell. Runtime hashes, request, input/output, status and log remain in a unique job directory. Escape/unregister terminate only this owned process. The long job has no undo boundary; the short copy-application operator owns undo so intervening user edits are not grouped into it.

Validation requires a learned binding, exact base vertex/triangle correspondence, unchanged accepted names/parents/joint heads, finite nonnegative normalized influences and valid IDs. Changed geometry, joints, painted weights or scene scale reject application before allocation. New copies retain full source rest matrices/rolls, hierarchy, UVs, materials, morphs and nonbone groups. The worker's simplified output geometry/materials never replaces the Blender asset. Failed copy creation removes only its owned partial objects/data/collection. Duplicate application fails. Export records provider/model revisions and normalizes four influences on another export copy.

## Actual evidence and limits

Blender 5.2.0 LTS, NVIDIA RTX 4090 24,564 MiB, driver 610.88; F16/Vulkan, ten beams, one private Shane avatar (7,234 vertices, 11,594 triangles). Original source GLB hash stayed unchanged. Source rig/vertices/weights/UVs/materials and three morphs passed preservation checks.

| Conditioning | Worker wall time | Forearm reference difference mean / max | Index mean / max | Knee mean / max |
| --- | --- | --- | --- | --- |
| 52 deform core, original joints retained | 65.09 s | 0.096 / 14.14 mm | 0.481 / 49.74 mm | 0.087 / 27.13 mm |
| 67 imported deform joints | 83.62 s | 0.208 / 25.78 mm | 0.172 / 22.84 mm | 0.243 / 40.21 mm |

Reference differences use the imported rig/weights in the same posed scene, not infallible ground truth. Poses: 60-degree forearm, 55-degree proximal index, 70-degree knee; no rigid accessory/collision/contact quality claim follows. Body and close-up hand renders were inspected privately. Depth-first ordering fixed severe distortions; small finger artifacts remain. The 52 case keeps imported nondeform extra bones in the scene but withholds them from neural conditioning; it does not test automatic placement of our parametric template.

Four upstream native tests passed: C++, C API, binding integration and tokenizer. Blender tests passed stale geometry/accepted joints/painted weights, NaN/invalid bone IDs, duplicate application and immediate owned-worker cancellation. The public apply operator is exercised. Callback-driven modal completion/interactive undo history still require broader manual UX testing. Pure transport/parser checks do not establish official model parity.

Observed whole-device memory was 11,207 MiB during an earlier ten-beam run; the same desktop without its worker was about 6,845 MiB. These are spot samples including other applications, not measured per-process peak VRAM or a 16-GB guarantee. Complete cold/warm RAM/VRAM measurements and broader consumer cards remain outstanding. CPU performance and official Python vs native tensor/code/weight parity have not been tested locally. The native F32 reference fixture path is documented upstream and remains a release gate for a production provider choice.

Private results and review `.blend`/PNG/FBX files live under `%LOCALAPPDATA%/Temp/local-character-ai-skin-*`, outside version control and packages. Compact numeric evidence is saved alongside this document. Next work: digit-region masking and seam-aware refinement, exact rigid attachment handling, clean mesh-only placement cases and official/native parity; then MIA placement and the wider motion pipeline.

## Unity weight policy verification

Fresh Unity 6000.3.21f1 and live 6000.4.3f1 pass actual AI-weighted FBX import, valid Humanoid Avatar, two skinned meshes, three morphs and unchanged vertices/bind matrices after calibration. Generic forearm deformation agrees with an independently evaluated Blender export copy within 1.96 micrometers. Open live scenes and their unsaved states remain unchanged; original monitored project file hashes match their baseline.

An initial 0.164-mm mismatch traced to trimming: the FBX contained 9,451 influences below .001, while Unity's complete weight API contained none. Requested importer minima 0 and 1e-8 reloaded as .001, including after forced synchronous reimport. Export now applies an explicit .001 floor on its temporary copy after selecting/normalizing four influences, always retains the strongest bone and renormalizes. Preflight warns, the character manifest records the minimum and the companion uses the matching value. The raw neural/artist weights in Blender are preserved. This avoids describing different engine and editor deformations as equivalent. Broader pose/deformation impact of that export policy still needs corpus checks. [Unity's documented trimming behavior](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/ModelImporter-minBoneWeight.html).
