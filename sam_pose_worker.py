# SPDX-License-Identifier: GPL-3.0-or-later
"""Single image, one person, external pinned SAM 3D Body CUDA inference. No Blender imports."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).parent))
from sam_pose_protocol import SAM_REV, DINO_REV, HF_REV, MODELS, MAPPING, DIRECTIONS, sha, source_files

def verify(provider):
    manifest = json.loads((provider/'installation.json').read_text())
    if (manifest['sam_revision'],manifest['dino_revision'],manifest['hf_revision']) != (SAM_REV,DINO_REV,HF_REV):
        raise ValueError('Install the pinned SAM 3D Body image-pose provider')
    if source_files(provider) != manifest['sources']:
        raise ValueError('Image-pose provider sources changed; reinstall the runtime')
    models = Path(manifest['models'])
    for name, expected in MODELS.items():
        if sha(models/name) != expected: raise ValueError('SAM checkpoint verification failed: '+name)
    if sha(models/'model_config.yaml') != manifest['config_sha256']:
        raise ValueError('SAM model configuration changed; reinstall the runtime')
    return models

def pack(mhr, prediction):
    """Read named MHR global rotations and evaluate its own neutral calibration.

    SAM flips Y/Z of emitted coordinates, but pred_global_rots retain the MHR
    frame. Both the rotations and this calibration use unflipped MHR Y-up.
    """
    import numpy as np
    import torch
    import roma
    names = list(mhr.get_joint_names())
    if len(names)!=127 or len(set(names))!=127: raise ValueError('Unsupported MHR joint layout')
    lookup = {name:i for i,name in enumerate(names)}
    device = next(mhr.buffers()).device
    shape = torch.as_tensor(prediction['shape_params'],device=device).float().reshape(1,45)
    params = torch.as_tensor(prediction['mhr_model_params'],device=device).float().reshape(1,204).clone()
    params[:,:136] = 0  # Keep inferred scale parameters, clear all articulated pose parameters.
    _, state = mhr(shape,params,torch.zeros(1,72,device=device),False)
    neutral = state[0].detach().cpu().numpy()
    rest_rot = roma.unitquat_to_rotmat(state[0,:,3:7]).detach().cpu().numpy()
    posed = np.asarray(prediction['pred_global_rots'],dtype=np.float64)
    if posed.shape != (127,3,3): raise ValueError('SAM returned an unexpected joint rotation shape')
    rows = {}
    for target,source in MAPPING.items():
        index = lookup[source]
        direction = None
        if target in DIRECTIONS:
            start,end = (lookup[n] for n in DIRECTIONS[target])
            direction = (neutral[end,:3]-neutral[start,:3]).tolist()
        rows[target] = dict(rotation=posed[index].tolist(),neutral_rotation=rest_rot[index].tolist(),neutral_direction=direction)
    return dict(schema_version=1,provider='sam-3d-body',source_revision=SAM_REV,
                coordinates='MHR_Y_UP',joints=rows,
                diagnostics=dict(subject='One person / full image crop',hand_refinement=bool(prediction.get('_hands',True)),
                                 limitations='Single-image depth and occluded joints are inferred; inspect the pose'))

def infer(folder):
    import torch
    request = json.loads((folder/'request.json').read_text())
    if sha(folder/'request.json') != (folder/'request.sha256').read_text():raise ValueError('Image-pose request changed')
    if sha(folder/request['input_file']) != request['input_sha256']:raise ValueError('Image input changed')
    provider = Path(request['provider'])
    models = verify(provider)
    if not torch.cuda.is_available():raise ValueError('SAM 3D Body requires a working NVIDIA CUDA runtime')
    os.environ['MOMENTUM_ENABLED']='0'  # Use the official portable TorchScript MHR asset.
    os.environ['HF_HUB_OFFLINE']='1'
    sys.path.insert(0,str(provider/'source'))
    # The upstream DINO loader otherwise downloads mutable torch.hub source on first inference.
    original = torch.hub.load
    def local_hub(repo,name,*args,**kwargs):
        if repo!='facebookresearch/dinov3':raise ValueError('Unexpected remote torch.hub dependency')
        kwargs['source']='local';kwargs['pretrained']=False
        return original(str(provider/'dinov3'),name,*args,**kwargs)
    torch.hub.load = local_hub
    from sam_3d_body import load_sam_3d_body, SAM3DBodyEstimator
    from PIL import Image, ImageOps
    import numpy as np
    with Image.open(folder/request['input_file']) as image:
        if image.width*image.height>40_000_000:raise ValueError('Use an image smaller than 40 megapixels')
        image=ImageOps.exif_transpose(image).convert('RGB')
        image.thumbnail((2048,2048))
        rgb=np.asarray(image)
    began=time.monotonic()
    model,cfg=load_sam_3d_body(str(models/'model.ckpt'),device='cuda',mhr_path=str(models/'assets/mhr_model.pt'))
    estimator=SAM3DBodyEstimator(model,cfg)  # No detector, segmentor or FOV downloads.
    with torch.inference_mode():
        outputs=estimator.process_one_image(rgb,inference_type='full' if request['hands'] else 'body')
        if len(outputs)!=1:raise ValueError('No single-person pose was produced')
        outputs[0]['_hands']=request['hands']
        result=pack(model.head_pose.mhr,outputs[0])
    result.update(request_sha256=sha(folder/'request.json'),input_sha256=request['input_sha256'])
    result['diagnostics'].update(elapsed_seconds=time.monotonic()-began,
                                 gpu=torch.cuda.get_device_name(),peak_vram_bytes=torch.cuda.max_memory_allocated())
    temporary=folder/'pose.tmp';temporary.write_text(json.dumps(result,allow_nan=False));temporary.replace(folder/'pose.json')
    (folder/'pose.sha256').write_text(sha(folder/'pose.json'))
    print('RIGMODO_IMAGE_POSE_COMPLETE',flush=True)

if __name__=='__main__':
    try:infer(Path(sys.argv[1]).resolve())
    except Exception as error:
        print(type(error).__name__+': '+str(error),flush=True)
        raise
