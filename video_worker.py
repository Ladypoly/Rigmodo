# SPDX-License-Identifier: GPL-3.0-or-later
"""External capture runtime; never imports Blender or writes the user's scene."""
import sys,os,json,math,time,hashlib,subprocess,shutil,traceback
from pathlib import Path
import numpy as np


def atomic(path,data):
    tmp=path.with_suffix('.pending');tmp.write_text(json.dumps(data,indent=2),encoding='utf-8');os.replace(tmp,path)


def probe(path,ffprobe='ffprobe'):
    result=subprocess.run([ffprobe,'-v','error','-select_streams','v:0','-show_entries','stream=width,height,avg_frame_rate,nb_frames,duration:format=duration','-of','json',str(path)],capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    info=json.loads(result.stdout)
    if not info.get('streams'):raise ValueError('The file contains no video stream')
    stream=info['streams'][0];duration=float(stream.get('duration',info.get('format',{}).get('duration',0)))
    numerator,denominator=stream.get('avg_frame_rate','0/1').split('/');fps=float(numerator)/max(1,float(denominator))
    if not duration>0 or not fps>0:raise ValueError('The video has no usable duration or frame rate')
    return dict(duration=duration,fps=fps,width=stream['width'],height=stream['height'])


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def preflight(video,request):
    import re
    info=probe(video,request['ffprobe'])
    if not 0<=request.get('start',0)<info['duration']:raise ValueError('Video start is outside the clip')
    duration=min(request['duration'],info['duration']-request.get('start',0))
    if not .1<=duration<=60:raise ValueError('Capture a video interval between 0.1 and 60 seconds')
    command=[request['ffmpeg'],'-v','info','-ss',str(request.get('start',0)),'-i',str(video),'-t',str(duration),'-an','-vf',"scale=160:-2,select=gt(scene\,.4),showinfo",'-f','null','-']
    checked=subprocess.run(command,capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if checked.returncode:raise ValueError('Video decoding failed; transcode the source before capture')
    cuts=[float(v) for v in re.findall(r'pts_time:([0-9.]+)',checked.stderr)]
    if cuts:raise ValueError('Video contains a likely cut near '+str(round(cuts[0]+request.get('start',0),2))+'s; trim to one continuous shot')
    info['capture_start']=request.get('start',0);info['capture_duration']=duration;info['cut_check']='passed'
    return info


def tracking_report(result):
    tracking=result.get('tracking',{});observed=np.asarray(tracking.get('observed_primary',[]),dtype=bool)
    missing=np.flatnonzero(~observed).tolist();others=tracking.get('other_person_boxes',[])
    ambiguous=[i for i,boxes in enumerate(others) if len(boxes)]
    keypoints=result.get('conditions',{}).get('kp2d_native77')
    report=dict(missing_track_frames=missing,other_person_frames=ambiguous)
    if keypoints is not None:
        confidence=keypoints[0,:,:,2].detach().cpu().numpy();report['mean_joint_confidence']=float(confidence.mean())
        report['low_confidence_frames']=np.flatnonzero((confidence<.25).mean(1)>.3).tolist()
    if observed.size and observed.mean()<.5:raise ValueError('The subject is missing in most frames; crop a full-body subject and retry')
    if len(ambiguous)>max(3,len(observed)*.1):raise ValueError('Several people are visible; crop the intended subject before capture. Raw diagnostics are retained in this job')
    return report


def export_gem(result,assets,device,progress):
    import torch
    from gem.common.soma import SomaFixedGs1BodyAdapter,SomaRuntimeConfig
    progress('Reconstructing the captured skeleton')
    body=SomaFixedGs1BodyAdapter(SomaRuntimeConfig(data_root=str(assets),device=device,lod='xlo',apply_correctives=False,enable_procedural_transforms=True,procedural_reference='runtime'))
    params={k:v.to(device=device,dtype=torch.float32) for k,v in result['pred_soma_params_global'].items()}
    with torch.inference_mode(),torch.autocast(device_type=device.split(':')[0],enabled=False):
        evaluated=body(**params,return_joints_only=True)
        poses=evaluated['transforms'][0].detach().cpu().numpy()
        neutral={}
        for key,value in params.items():
            if key in {'body_pose','global_orient','transl'}:neutral[key]=torch.zeros_like(value[:,:1])
            else:neutral[key]=value.mean(1,keepdim=True) if value.ndim>=3 else value
        rest=body(**neutral,return_joints_only=True)['transforms'][0,0].detach().cpu().numpy()
    names=list(map(str,body.runtime.public_joint_names))
    parent_ids=body.runtime.output_joint_parent_ids.detach().cpu().numpy().astype(np.int32)
    if len(names)!=poses.shape[1] or len(parent_ids)!=len(names):raise ValueError('Unexpected SOMA transform layout')
    # SOMA uses Leg/Shin and Spine1/Spine2/Chest; normalize only this provider's names.
    aliases={'Spine1':'Spine','Spine2':'Spine1','Chest':'Spine2','Neck1':'Neck','Neck2':'SomaNeck2'}
    for side in ('Left','Right'):aliases[side+'Leg']=side+'UpLeg';aliases[side+'Shin']=side+'Leg'
    names=[aliases.get(n,n) for n in names]
    parents=parent_ids.copy()
    if parents[0] not in {-1,0}:raise ValueError('Unexpected SOMA virtual root parent')
    parents[0]=-1
    conversion=np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]],dtype=np.float32)
    poses=conversion@poses;rest=conversion@rest
    # Export rigid rotations while retaining the shape-aware FK joint locations.
    for values in (poses,rest):
        u,_,v=np.linalg.svd(values[...,:3,:3]);rotation=u@v
        negative=np.linalg.det(rotation)<0
        if negative.any():u[..., :, -1]*=np.where(negative,-1,1)[...,None];rotation=u@v
        values[...,:3,:3]=rotation
    hip=names.index('Hips');foot_indices=[i for i,n in enumerate(names) if n in {'LeftFoot','RightFoot','LeftToeBase','RightToeBase','LeftToeEnd','RightToeEnd'}]
    rest_floor=float(rest[foot_indices,2,3].min());source_floor=float(np.quantile(poses[:,foot_indices,2,3].min(1),.08))
    rest[1:,2,3]-=rest_floor
    origin=poses[0,hip,:2,3].copy();poses[:,:,:2,3]-=origin;poses[:,:,2,3]-=source_floor
    rest[0,:3,3]=0
    # A game Root carries ground travel; body height and flight remain in Hips.
    poses[:,0,:3,3]=poses[:,hip,:3,3];poses[:,0,2,3]=0
    # SOMA's joint axes are not Blender bone axes. A fixed right-side basis
    # change makes +Y follow each neutral bone without altering its motion delta.
    for i in range(len(names)):
        children=np.flatnonzero(parents==i);children=children[children!=i]
        if not len(children):continue
        child=int(children[0]);direction=rest[child,:3,3]-rest[i,:3,3]
        if np.linalg.norm(direction)<1e-6:continue
        y=direction/np.linalg.norm(direction);x=rest[i,:3,0]-y*np.dot(rest[i,:3,0],y)
        if np.linalg.norm(x)<1e-5:x=np.cross(y,np.array([0,0,1]) if abs(y[2])<.9 else np.array([1,0,0]))
        x/=np.linalg.norm(x);basis=np.column_stack((x,y,np.cross(x,y)));change=rest[i,:3,:3].T@basis
        rest[i,:3,:3]=basis;poses[:,i,:3,:3]=poses[:,i,:3,:3]@change
    times=np.arange(len(poses),dtype=np.float32)/30
    data=dict(names=np.asarray(names),parents=parents,rest=rest.astype(np.float32),poses=poses.astype(np.float32),times=times,labels=np.asarray(['']*len(names)))
    logits=result.get('static_conf_logits')
    if logits is not None:
        probs=torch.sigmoid(logits[0]).detach().cpu().numpy()
        data['contact_probabilities']=np.column_stack((probs[:,:2].max(1),probs[:,2:4].max(1))).astype(np.float32)
    return data


def capture(video,request,folder,progress):
    import torch
    from omegaconf import OmegaConf
    from gem.inference.body_video import run_body_video
    models=Path(request['models']);config=OmegaConf.load(str(models/'body_video_native77.yaml'))
    for section,name in [('pose','body_s240000.ckpt'),('observations','vitpose.pth'),('motion','motion_native77_e774_s292175.ckpt'),('detector','yolox_humanart.onnx')]:config[section]['checkpoint']=str(models/name)
    config['motion']['stats']=str(models/'motion_stats_raw.npz');config['camera']['mode']=request.get('camera_mode','static')
    config['pose']['batch_size']=1;config['observations']['batch_size']=1
    device='cuda' if torch.cuda.is_available() else 'cpu'
    if device=='cuda':
        while torch.cuda.mem_get_info()[0]<5*1024**3:
            progress('Waiting for GPU memory; close or finish other GPU tasks');time.sleep(2)
        torch.cuda.reset_peak_memory_stats()
    began=time.monotonic();result=run_body_video(str(video),OmegaConf.to_container(config,resolve=True),device=device,start=request.get('start',0),duration=request['duration'],progress=progress)
    torch.save(result,folder/'raw-gem.pt')
    quality=tracking_report(result);data=export_gem(result,models/'soma',device,progress)
    data['source_times']=data['times']+float(request.get('start',0))
    metrics=dict(provider='GEM-X',quality=quality,source_revision='4aef1452e5df171deff4f293c08e643eb450981e',elapsed_seconds=time.monotonic()-began,device=device,peak_torch_bytes=torch.cuda.max_memory_allocated() if device=='cuda' else None,frames=len(data['times']),fps=30,source_video=str(video))
    return data,metrics


def main(folder):
    request=json.loads((folder/'request.json').read_text(encoding='utf-8'))
    def progress(phase):atomic(folder/'progress.json',dict(phase=phase));print('CAPTURE_STAGE',phase,flush=True)
    video=Path(request.get('video',''))
    if request['kind']=='comfy':
        from comfy_video import Client,bind,h3_graph
        client=Client(request['comfy_url']);progress('Checking ComfyUI')
        image=client.upload(request['reference']) if request.get('reference') else None
        if request.get('workflow'):
            workflow=Path(request['workflow'])
            if workflow.stat().st_size>5*1024*1024:raise ValueError('Use an API workflow smaller than 5 MB')
            graph=json.loads(workflow.read_text(encoding='utf-8'))
            if 'nodes' in graph:raise ValueError('Export the custom workflow in API format before using it in Rigmodo')
            values=dict(prompt=request['prompt'],seed=request['seed'],frames=round(request['duration']*24),fps=24,image=image,first_image=image,last_image=image,width=request.get('width',416),height=request.get('height',736),output_prefix='video/rigmodo_'+request['id'])
            graph=bind(graph,request.get('bindings',{}),values)
        else:graph=h3_graph(request,image)
        saved=folder/'generated-video.json'
        if saved.exists() and Path(json.loads(saved.read_text())['video']).is_file():
            video=Path(json.loads(saved.read_text())['video']);progress('Reusing generated video')
        else:
            video=client.run(graph,folder,progress,request['id'],request.get('output_node',''));atomic(saved,dict(video=str(video)))
        request['start']=0
        request['duration']=min(60,probe(video,request['ffprobe'])['duration'])
    if not video.is_file():raise ValueError('Choose an existing video file')
    if request.get('loop') and request.get('cycle_method')=='BRIDGE':
        from video_cycles import bridge
        video=bridge(video,request,folder/'bridge',progress);request['start']=0;request['duration']=min(60,probe(video,request['ffprobe'])['duration'])
    progress('Checking the video');source=preflight(video,request)
    request['duration']=min(request['duration'],source['duration']-request.get('start',0))
    if request['duration']<.1:raise ValueError('Choose a video interval spanning at least two frames')
    os.environ['PATH']=str(Path(request['ffmpeg']).parent)+os.pathsep+os.environ.get('PATH','')
    from comfy_video import release_job
    release_job(folder)
    identity=dict(video_sha256=file_hash(video),start=request.get('start',0),duration=request['duration'],camera=request.get('camera_mode','static'),adapter=3,models=file_hash(Path(request['models'])/'rigmodo-checkpoints.json') if (Path(request['models'])/'rigmodo-checkpoints.json').exists() else file_hash(Path(__file__).with_name('video_capture_lock.json')))
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest();cache=folder.parent/'CaptureCache'/key;cache.mkdir(parents=True,exist_ok=True)
    if (cache/'output.npz').exists() and (cache/'metrics.json').exists():
        progress('Reusing cached motion capture');shutil.copyfile(cache/'output.npz',folder/'output.npz');metrics=json.loads((cache/'metrics.json').read_text());metrics['cache_hit']=True
    else:
        data,metrics=capture(video,request,folder,progress)
        temporary=folder/'output.pending.npz';np.savez_compressed(temporary,**data);os.replace(temporary,folder/'output.npz')
        staging=cache/'output.pending.npz';shutil.copyfile(folder/'output.npz',staging);os.replace(staging,cache/'output.npz');atomic(cache/'metrics.json',metrics)
    if request.get('loop') and request.get('cycle_method')=='TRIM':
        from video_cycles import find_cycle
        with np.load(folder/'output.npz',allow_pickle=False) as archive:data={k:archive[k] for k in archive.files}
        shutil.copyfile(folder/'output.npz',folder/'raw-motion.npz');data,cycle=find_cycle(data)
        np.savez_compressed(folder/'output.npz',**data);metrics['selected_cycle']=cycle
    metrics['checkpoint_manifest_sha256']=identity['models'];metrics['source_video_sha256']=identity['video_sha256']
    if request['kind']=='comfy':metrics['workflow_sha256']=file_hash(request['workflow']) if request.get('workflow') else file_hash(Path(__file__).with_name('comfy_video.py'))
    atomic(folder/'capture-source.json',dict(identity=identity,source=source,metrics=metrics))
    atomic(folder/'results.json',dict(video=str(video),source=source,metrics=metrics))
    atomic(folder/'status.json',dict(schema_version=1,status='complete'))
    print('VIDEO_CAPTURE_COMPLETE',json.dumps(metrics),flush=True)


if __name__=='__main__':
    folder=Path(sys.argv[sys.argv.index('--')+1])
    try:main(folder)
    except Exception as exc:
        traceback.print_exc();atomic(folder/'status.json',dict(schema_version=1,status='failed',error=str(exc)));raise

    finally:
        from comfy_video import release_job
        release_job(folder)
