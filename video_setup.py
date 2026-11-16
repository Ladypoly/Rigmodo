# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned capture installation in a separate environment; also runs without Blender."""
import hashlib,json,os,shutil,subprocess,sys,urllib.request,venv,zipfile
from pathlib import Path

REVISION='4aef1452e5df171deff4f293c08e643eb450981e'
SCHEMA=1


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def ready(python,models):
    try:
        marker=Path(python).parent.parent/'capture-ready.json';data=json.loads(marker.read_text())
        if data.get('schema')!=SCHEMA or data.get('source_revision')!=REVISION or not Path(python).is_file() or Path(data['models']).resolve()!=Path(models).resolve():return False
        return all(Path(v['path']).is_file() and Path(v['path']).stat().st_size==v['bytes'] and Path(v['path']).stat().st_mtime_ns==v['mtime_ns'] for v in data['files'])
    except (OSError,ValueError,KeyError):return False


def install(folder):
    folder=Path(folder);request=json.loads((folder/'request.json').read_text());python=Path(request['python']);base=python.parent.parent;models=Path(request['models']);source=Path(request['source']);package=Path(__file__).parent
    cache=base.parent.parent/'Cache'/'capture-install';(cache/'temp').mkdir(parents=True,exist_ok=True)
    os.environ['TEMP']=os.environ['TMP']=str(cache/'temp');os.environ['PIP_CACHE_DIR']=str(cache/'pip')
    def progress(phase):
        (folder/'progress.json').write_text(json.dumps(dict(phase=phase)));print(phase,flush=True)
    def run(args):subprocess.run(list(map(str,args)),check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if not request.get('verify_only'):
        if not shutil.which('git'):raise ValueError('Install Git for Windows before setting up capture')
        source.parent.mkdir(parents=True,exist_ok=True)
        if not source.exists():
            progress('Downloading pinned GEM-X source');run(['git','clone','https://github.com/NVlabs/GEM-X.git',source]);run(['git','-C',source,'checkout','--detach',REVISION])
        actual=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
        if actual!=REVISION or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('The capture source differs from the pinned version; choose a clean provider directory')
        if not python.exists():
            progress('Creating isolated capture environment');venv.EnvBuilder(with_pip=True).create(base)
        progress('Installing capture dependencies')
        run([python,'-m','pip','install','--upgrade','pip==26.3','setuptools==84.2.1','wheel==0.48.0'])
        run([python,'-m','pip','install','-r',package/'requirements-video-capture.txt','--extra-index-url','https://download.pytorch.org/whl/cu128'])
        run([python,'-m','pip','install','--no-deps',source])
    if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=REVISION:raise ValueError('Capture source revision differs from the pinned provider')
    lock=json.loads((package/'video_capture_lock.json').read_text());verified=[]
    for item in lock:
        path=models/item['path'];path.parent.mkdir(parents=True,exist_ok=True)
        progress('Verifying '+item['path'])
        if not path.exists() or sha(path)!=item['sha256']:
            if request.get('verify_only'):raise ValueError('Capture checkpoint is missing or changed: '+item['path'])
            progress('Downloading '+item['path']);pending=path.with_suffix(path.suffix+'.download')
            url=item.get('url') or f"https://huggingface.co/{item['repo']}/resolve/{item['revision']}/{item['file']}"
            with urllib.request.urlopen(url,timeout=90) as response,pending.open('wb') as stream:shutil.copyfileobj(response,stream)
            if item.get('zip_member'):
                with zipfile.ZipFile(pending) as archive,archive.open(item['zip_member']) as src,path.with_suffix('.extract').open('wb') as dst:shutil.copyfileobj(src,dst)
                extracted=path.with_suffix('.extract')
                if sha(extracted)!=item['sha256']:raise ValueError('Downloaded detector failed verification')
                os.replace(extracted,path);pending.unlink()
            else:
                if sha(pending)!=item['sha256']:raise ValueError('Downloaded checkpoint failed verification: '+item['path'])
                os.replace(pending,path)
        stat=path.stat();verified.append(dict(path=str(path.resolve()),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=item['sha256']))
    progress('Checking CUDA and capture imports')
    probe=subprocess.check_output([str(python),'-c',"import torch,gem,soma; print(torch.__version__); assert torch.cuda.is_available(), 'NVIDIA CUDA is required for this capture profile'"],text=True)
    marker=dict(schema=SCHEMA,source_revision=REVISION,models=str(models.resolve()),files=verified,probe=probe.strip())
    temporary=base/'capture-ready.pending';temporary.write_text(json.dumps(marker,indent=2));os.replace(temporary,base/'capture-ready.json')
    (folder/'status.json').write_text(json.dumps(dict(schema_version=1,status='complete')));progress('Video capture ready')


if __name__=='__main__':
    folder=Path(sys.argv[sys.argv.index('--')+1])
    try:install(folder)
    except Exception as exc:
        import traceback
        traceback.print_exc();(folder/'status.json').write_text(json.dumps(dict(schema_version=1,status='failed',error=str(exc))));sys.exit(1)
