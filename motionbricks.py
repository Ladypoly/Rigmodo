# SPDX-License-Identifier: GPL-3.0-or-later
"""Pose-conditioned MotionBricks jobs using Rigmodo's human motion transport."""
import json,math
from pathlib import Path
from . import skinning,motion_jobs,motion_keyframes,model_storage

PIN='54fc563aeaaf819a753d72cc9fdc6713989cdd43'
def cache():return skinning.provider_cache().parent/'motionbricks-54fc563'
def ready(provider):
    try:
        root=Path(provider);record=json.loads((root/'installation.json').read_text());lock=Path(__file__).with_name('motionbricks-lock.json')
        return model_storage.lock_matches(record,lock) and Path(record['python']).is_file() and model_storage.resolve(root/'mmm_v6_soma_fp32.onnx').is_file()
    except (OSError,ValueError,KeyError,TypeError):return False

def prepare(context,rig,seed,in_place,provider,parent=None):
    motion_jobs.validate_rig(context,rig)
    times=sorted({float(k.co.x) for c in motion_keyframes.pose_curves(rig) for k in c.keyframe_points})
    if len(times)<2:raise ValueError('Insert at least two ordinary bone pose keyframes in the active Action')
    fps=context.scene.render.fps/context.scene.render.fps_base
    frames=math.ceil((times[-1]-times[0])*30/fps-1e-6)+1
    if not 15<=frames<=900:raise ValueError('Use a pose sequence between 0.5 and 30 seconds')
    if any(not .5-1e-5<=(b-a)/fps<=2+1e-5 for a,b in zip(times,times[1:])):raise ValueError('Space adjacent pose keys 0.5–2 seconds apart; add intermediate poses for longer moves')
    folder=motion_jobs.prepare(context,rig,'MotionBricks pose transitions',frames,100,seed,in_place,parent=parent,keyframes=True,start_frame=times[0])
    request=json.loads((folder/'request.json').read_text());lock=json.loads(Path(__file__).with_name('motionbricks-lock.json').read_text())
    request.update(provider='motionbricks',provider_revision=PIN,provider_cache=str(Path(provider).resolve()),models={f['path']:f['sha256'] for f in lock['files']})
    (folder/'request.json').write_text(json.dumps(request,indent=2,allow_nan=False));(folder/'request.sha256').write_text(motion_jobs.sha(folder/'request.json'))
    return folder

def start(folder):
    from . import image_pose
    folder=Path(folder).resolve();request=json.loads((folder/'request.json').read_text());provider=Path(request['provider_cache'])
    if skinning._jobs:raise ValueError('Wait for the current local job or cancel it')
    if skinning.poll(folder)['status']!='prepared' or not ready(provider):raise ValueError('Install MotionBricks in Extension Settings → Setup')
    motion_jobs.check_inputs(folder,request)
    python=json.loads((provider/'installation.json').read_text())['python']
    image_pose.launch(folder,[python,'-I',str(Path(__file__).with_name('motionbricks_worker.py')),str(folder)],'Generating key-pose transitions · MotionBricks')
    skinning._jobs[str(folder)]['finish']=motion_jobs.finish
