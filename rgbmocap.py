# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned RGB MoCap worker adapter; no neural imports in Blender's UI."""
import json,os,subprocess,time
from pathlib import Path

REVISION='42844135d0612c7e574fd43f6c42414f5fce1219'
DEFAULT='R:/AI/Rigmodo/Providers/RGBMocap'
PREFIX='@@MOCAP@@'


def status(provider):
    root=Path(provider)
    for name in ('worker_boot.py','runtime/python.exe','runtime_exmr/python.exe'):
        if not (root/name).is_file():return 'Run RGB MoCap Setup first: missing '+name
    lock=json.loads(Path(__file__).with_name('rgbmocap_lock.json').read_text(encoding='utf-8'))
    for model in lock['models']:
        path=root/'models'/model['relative']
        if not path.is_file() or path.stat().st_size<model['minimum_bytes']:return 'Import or download '+model['name']+' in RGB MoCap'
        if model['sha256']:
            try:
                receipt=path.with_suffix(path.suffix+'.receipt.json')
                if receipt.stat().st_size>16384:raise ValueError('Oversized model receipt')
                value=json.loads(receipt.read_text(encoding='utf-8'));actual=path.stat()
                if not isinstance(value,dict) or value.get('sha256')!=model['sha256'] or value.get('stat')!=[actual.st_size,actual.st_mtime_ns]:raise ValueError('Model changed')
            except (OSError,ValueError):return 'Verify or import '+model['name']+' in RGB MoCap'
    return ''


def event(line):
    offset=line.find(PREFIX)
    if offset<0:return None
    if len(line)>1024*1024:raise ValueError('RGB MoCap returned an oversized progress event')
    try:value=json.JSONDecoder().raw_decode(line[offset+len(PREFIX):].lstrip())[0]
    except ValueError:
        if offset:return None
        raise
    if not isinstance(value,dict):raise ValueError('Invalid RGB MoCap progress event')
    return value


def run(command,root,env,progress,label):
    progress(label);events=[];tail=[]
    child=subprocess.Popen(command,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
        text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    try:
        for line in child.stdout:
            print(line.rstrip(),flush=True);tail=(tail+[line.rstrip()])[-16:]
            value=event(line)
            if value is None:continue
            kind=value.get('type')
            if kind in {'prepared','complete','failed','batch_item_done'}:events.append(value)
            if kind=='failed':continue
            if kind in {'progress','batch_item_start','compute_plan','memory_mode'}:
                message=value.get('message') or value.get('stage') or label
                total=value.get('total');current=value.get('current')
                if isinstance(total,(int,float)) and isinstance(current,(int,float)) and total>0:
                    progress('ExMR · '+str(message),completed=current,total=total,unit=value.get('unit','frames'))
                else:progress('ExMR · '+str(message))
        code=child.wait()
        failures=[v.get('message','ExMR stage failed') for v in events if v.get('type')=='failed']
        if code or failures:raise RuntimeError(failures[-1] if failures else label+' failed: '+'\n'.join(tail)[-2000:])
        return events
    finally:
        child.stdout.close()
        if child.poll() is None:child.terminate();child.wait(timeout=5)


def capture(video,request,folder,progress):
    import numpy as np
    root=Path(request['rgbmocap_provider']).resolve();problem=status(root)
    if problem:raise ValueError(problem)
    checked=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if checked.returncode or checked.stdout.strip()!=REVISION:raise ValueError('This RGB MoCap adapter requires revision '+REVISION+'; use its pinned setup')
    env=dict(os.environ,RGB_MOCAP_MANAGED='1',RGB_MOCAP_DATA=str(root),RGB_MOCAP_EXMR_OPTIONS=json.dumps(dict(static_camera=request.get('camera_mode','static')=='static',smoothing='global')))
    env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
    started=time.monotonic();workspace=(folder/'RGBMocap').resolve();workspace.mkdir(parents=True,exist_ok=True)
    def command(stage,*args):
        profile='runtime_exmr' if stage.startswith('exmr') else 'runtime'
        return [str(root/profile/'python.exe'),'-I','-X','utf8',str(root/'worker_boot.py'),stage,*map(str,args)]
    prepared=run(command('prepare','--video',video,'--project',workspace,'--start',request.get('start',0),'--end',request.get('start',0)+request['duration'],'--motion-tool','exmr','--result','initial'),root,env,progress,'ExMR · Preparing video')
    rows=[v for v in prepared if v.get('type')=='prepared']
    if len(rows)!=1:raise ValueError('RGB MoCap did not return its prepared project')
    project=Path(rows[0]['project']).resolve()
    if not project.is_relative_to(workspace):raise ValueError('RGB MoCap project escaped the capture job')
    run(command('track','--project',project,'--result','initial'),root,env,progress,'ExMR · Tracking subject')
    with np.load(project/'tracking.npz',allow_pickle=False) as tracking:
        observed=np.asarray(tracking['observed'],dtype=bool)
    if observed.ndim!=1 or not observed.size or observed.mean()<.5:raise ValueError('The subject is missing in most frames; crop a full-body subject and retry')
    # shortcut: upstream tracking exposes one primary track; add actor selection for multi-person capture.
    quality=dict(missing_track_frames=np.flatnonzero(~observed).tolist(),person_selection='Primary track; crop videos to one person')
    batch=workspace/'batch.json';batch.write_text(json.dumps(dict(version=1,root=str(workspace),phase='all',jobs=[dict(project=str(project),result='initial',force=False)])),encoding='utf-8')
    inference=run(command('exmr_batch','--request',batch,'--project',project,'--result','initial'),root,env,progress,'ExMR · Reconstructing body and hands')
    # Source foot correction precedes target fitting; target correction adapts different proportions.
    run(command('correct','--project',project,'--result','corrected_initial','--foot-lock','1','--hand-lock','0','--correction-preset','normal','--correction-mode','flat'),root,env,progress,'ExMR · Correcting source foot contacts')
    run(command('rig','--project',project,'--result','corrected_initial'),root,env,progress,'ExMR · Preparing game skeleton')
    info=json.loads((project/'corrected_initial_mixamo.json').read_text(encoding='utf-8'));filename=info['bvh_file']
    if Path(filename).name!=filename:raise ValueError('Invalid RGB MoCap animation path')
    imported=folder/'Import';imported.mkdir(exist_ok=True)
    (imported/'request.json').write_text(json.dumps(dict(file=str(project/filename))),encoding='utf-8')
    run([request['blender'],'--factory-startup','--background','--disable-autoexec','--python',str(Path(__file__).with_name('animation_import_worker.py')),'--',str(imported)],root,env,progress,'ExMR · Importing captured motion')
    state=json.loads((imported/'status.json').read_text(encoding='utf-8'))
    if state.get('status')!='complete':raise ValueError(state.get('error','Captured skeleton import failed'))
    with np.load(imported/'output.npz',allow_pickle=False) as archive:data={k:archive[k] for k in archive.files}
    if len(data['times'])!=int(info['frames']):raise ValueError('Captured animation frame count changed during import')
    frame_file=info['frames_file']
    if Path(frame_file).name!=frame_file:raise ValueError('Invalid RGB MoCap frame path')
    native=np.load(project/frame_file,mmap_mode='r',allow_pickle=False)
    expected=native[:,:,:3,3][:,:,[0,2,1]]*np.asarray([1,-1,1])
    imported_names=list(map(str,data['names']));indices=[imported_names.index(n) for n in info['names']]
    error=float(np.abs(np.take(data['poses'][...,:3,3],indices,axis=1)-expected).max());del native
    if error>.0005:raise ValueError('Captured BVH changed source joint positions or units; maximum error '+str(error)+' m')
    data['source_times']=data['times']+float(request.get('start',0))
    with np.load(project/'corrected_initial_contacts.npz',allow_pickle=False) as contacts:
        probability=np.zeros((len(data['times']),2),np.float32)
        for foot,start,end,*_ in contacts['segments']:
            foot,start,end=int(foot),int(start),int(end)
            if foot not in (0,1) or not 0<=start<end<=len(probability):raise ValueError('Invalid source foot contact interval')
            probability[start:end,foot]=1
        data['contact_probabilities']=probability
    correction=json.loads((project/'corrected_initial_correction.json').read_text(encoding='utf-8'))
    metrics=dict(provider='ExMR via RGB MoCap',source_revision=REVISION,elapsed_seconds=time.monotonic()-started,frames=len(data['times']),fps=info['fps'],source_video=str(video),project=str(project),smoothing='global',bvh_joint_position_max_error_m=error,source_correction=correction,quality=quality,peak_torch_bytes=max((v['peak_cuda_allocated_bytes'] for v in inference if v.get('peak_cuda_allocated_bytes') is not None),default=None))
    return data,metrics
