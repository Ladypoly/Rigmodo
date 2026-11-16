# SPDX-License-Identifier: GPL-3.0-or-later
"""Conservative cycle selection and optional fixed-camera video closing bridge."""
import json,math,os,subprocess
from pathlib import Path
import numpy as np


def find_cycle(data):
    times=data['times'];poses=data['poses'];names=list(map(str,data['names']));hips=names.index('Hips');head=names.index('Head')
    scale=max(np.linalg.norm(data['rest'][head,:3,3]-data['rest'][hips,:3,3])*2,.01)
    roles=['Hips','Head',*[s+p for s in ('Left','Right') for p in ('Arm','ForeArm','Hand','UpLeg','Leg','Foot')]]
    indices=[names.index(r) for r in roles if r in names]
    positions=poses[:,:,:3,3][:,indices]-poses[:,hips,None,:3,3];velocity=np.gradient(positions,times,axis=0);best=None
    for lo in range(0,max(1,len(times)//4),2):
        for hi in range(lo+1,len(times)):
            duration=float(times[hi]-times[lo])
            if duration<max(.45,float(times[-1])*.35):continue
            position=float(np.linalg.norm(positions[hi]-positions[lo],axis=-1).mean()/scale)
            speed=float(np.linalg.norm(velocity[hi]-velocity[lo],axis=-1).mean()/scale)
            a,b=poses[lo,indices,:3,:3],poses[hi,indices,:3,:3]
            angle=float(np.arccos(np.clip((np.trace(a@np.swapaxes(b,-1,-2),axis1=-2,axis2=-1)-1)/2,-1,1)).mean())
            if position>.075 or angle>.4 or speed>1.5:continue
            score=position+angle*.12+speed*.025-duration/float(times[-1])*.01
            if best is None or score<best[0]:best=(score,lo,hi,position,angle,speed)
    if best is None:raise ValueError('No convincing repeated cycle found. Trim a repeat manually, use the whole clip, or generate a closing bridge')
    _,lo,hi,position,angle,speed=best;output=dict(data)
    for key in ('poses','times','contact_probabilities','source_times'):
        if key in data:output[key]=data[key][lo:hi+1].copy()
    output['times']-=output['times'][0]
    return output,dict(start_seconds=float(times[lo]),end_seconds=float(times[hi]),pose_error_fraction=position,mean_rotation_error_rad=angle,velocity_error_per_second=speed)


def bridge(video,request,folder,progress):
    from comfy_video import Client,h3_graph
    from video_worker import probe,atomic
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True);saved=folder/'bridge-result.json'
    if saved.exists() and Path(json.loads(saved.read_text())['video']).is_file():return Path(json.loads(saved.read_text())['video'])
    def run(args):
        result=subprocess.run([request['ffmpeg'],'-y','-v','error',*map(str,args)],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if result.returncode:raise ValueError('Video bridge preparation failed: '+result.stderr[-700:])
    progress('Preparing the closing bridge');segment=folder/'segment.mp4';width,height=416,736
    run(['-ss',request.get('start',0),'-i',video,'-t',request['duration'],'-an','-vf',f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,fps=24','-c:v','libx264','-crf',18,segment])
    source=probe(segment,request['ffprobe']);last=max(0,round(source['duration']*24)-1);first=folder/'first.png';end=folder/'last.png'
    run(['-i',segment,'-frames:v',1,first]);run(['-i',segment,'-vf',f'select=eq(n\\,{last})','-frames:v',1,end])
    client=Client(request['comfy_url']);a=client.upload(end);b=client.upload(first)
    options=dict(request,id=request['id']+'-bridge',loop=False,duration=5.17,prompt=request['prompt']+' Continue the same action from the first image to the final image, preserving the character, lighting, floor and camera. One continuous shot. No audio.')
    graph=h3_graph(options,a,b);generated=client.run(graph,folder,progress,options['id'],'save')
    output=folder/'closed-cycle.mp4'
    run(['-i',segment,'-i',generated,'-filter_complex','[1:v]fps=24,trim=start_frame=1,setpts=PTS-STARTPTS[b];[0:v][b]concat=n=2:v=1:a=0[v]','-map','[v]','-an','-c:v','libx264','-crf',18,output])
    atomic(saved,dict(video=str(output),source=str(video),bridge=str(generated),profile='h3-capture-v1',interpolation=False));return output
