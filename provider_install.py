# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned Windows provider installation; standalone Python 3.11 worker."""
import argparse
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import subprocess
import sys
import urllib.request
import venv
import zipfile
HIDDEN=getattr(subprocess,'CREATE_NO_WINDOW',0)

class SilentVenv(venv.EnvBuilder):
    def _call_new_python(self,context,*args,**kwargs):
        kwargs.setdefault('creationflags',HIDDEN)
        return super()._call_new_python(context,*args,**kwargs)

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def download(entry,path,seed=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file() and sha(path)==entry['sha256']:return
    temporary=path.with_suffix(path.suffix+'.download')
    if temporary.is_file() and 'bytes' in entry and temporary.stat().st_size>=entry['bytes']:
        if temporary.stat().st_size==entry['bytes'] and sha(temporary)==entry['sha256']:
            os.replace(temporary,path);return
        temporary.unlink()
    if seed and seed.is_file() and sha(seed)==entry['sha256']:
        if temporary.exists():temporary.unlink()
        try:os.link(seed,temporary)
        except OSError:shutil.copyfile(seed,temporary)
    else:
        offset=temporary.stat().st_size if temporary.exists() else 0
        request=urllib.request.Request(entry['url'],headers={'User-Agent':'LocalCharacter-local-provider-setup',**({'Range':f'bytes={offset}-'} if offset else {})})
        with urllib.request.urlopen(request,timeout=60) as response:
            if response.status==206:
                if not response.headers.get('Content-Range','').startswith(f'bytes {offset}-'):raise ValueError('Unexpected download range')
                mode='ab'
            else:mode='wb';offset=0
            maximum=entry.get('bytes',4*1024**3)
            if offset>maximum:raise ValueError('Partial download exceeds its pinned size')
            print('Downloading',path.name,'from byte',offset,flush=True)
            next_report=offset+64*1024**2
            with temporary.open(mode) as stream:
                while chunk:=response.read(1024**2):
                    offset+=len(chunk)
                    if offset>maximum:raise ValueError('Download exceeds its size budget')
                    stream.write(chunk)
                    if offset>=next_report:print(path.name,offset,'bytes',flush=True);next_report=offset+64*1024**2
    if ('bytes' in entry and temporary.stat().st_size!=entry['bytes']) or sha(temporary)!=entry['sha256']:
        raise ValueError('Downloaded file differs from its pinned size/hash: '+path.name)
    os.replace(temporary,path)


def extract(archive,cache,lock):
    if sha(archive)!=lock['native_archive_sha256']:raise ValueError('Native provider archive differs from this extension release')
    with zipfile.ZipFile(archive) as package:
        entries=package.infolist()
        if len(entries)>10000 or sum(e.file_size for e in entries)>1024**3:raise ValueError('Provider archive exceeds its budget')
        if {e.filename for e in entries}!=set(lock['files']):raise ValueError('Provider archive inventory changed')
        for entry in entries:
            relative=PurePosixPath(entry.filename)
            if relative.is_absolute() or '..' in relative.parts or '\\' in entry.filename or ':' in entry.filename:raise ValueError('Unsafe provider archive path')
            destination=cache/relative
            if not destination.resolve().is_relative_to(cache.resolve()):raise ValueError('Provider path escapes its cache')
            wanted=lock['files'][entry.filename]
            if destination.is_file():
                if sha(destination)==wanted:continue
                # Local developer build manifests retain compiler/source paths.
                # Keep their extra fields when the pinned binary inventory agrees.
                if destination.name=='build-manifest.json':
                    existing=json.loads(destination.read_text());incoming=json.loads(package.read(entry))
                    same_source=existing.get('source_revision',existing.get('provider_revision'))==incoming.get('source_revision',incoming.get('provider_revision'))
                    if same_source and existing.get('binaries')==incoming.get('binaries'):continue
                    # 0.8 only adds an independent entry point to the unchanged
                    # 0.7 Kimodo runtime. Verify every existing executable/DLL
                    # before updating its inventory; retain compiler metadata.
                    previous={k:v for k,v in incoming.get('binaries',{}).items() if k!='kmd-keyframes.exe'}
                    if same_source and relative.parts[0]=='kimodo-5679ff1' and not existing.get('keyframe_adapter') and existing.get('binaries')==previous and incoming.get('keyframe_adapter',{}).get('version')==1:
                        for name,digest in previous.items():
                            path=destination.parent/'bin'/name
                            if sha(path)!=digest:raise ValueError('Existing native runtime changed: '+name)
                        existing.update(binaries=incoming['binaries'],keyframe_adapter=incoming['keyframe_adapter'])
                        temporary=destination.with_suffix('.install');temporary.write_text(json.dumps(existing,indent=2));os.replace(temporary,destination)
                        continue
                raise ValueError('Existing provider file has edits; choose a clean cache: '+str(destination))
            destination.parent.mkdir(parents=True,exist_ok=True);temporary=destination.with_suffix(destination.suffix+'.install')
            with package.open(entry) as source,temporary.open('wb') as target:shutil.copyfileobj(source,target,1024**2)
            if sha(temporary)!=wanted:raise ValueError('Native provider entry failed verification')
            os.replace(temporary,destination)


def runtime(cache,lock,seed=None):
    if sys.version_info[:2]!=(3,11):raise ValueError('Choose an installed Python 3.11 executable for the isolated MIA runtime')
    directory=cache/'mia-original/runtime';python=directory/'Scripts/python.exe'
    if not python.is_file():SilentVenv(with_pip=True,system_site_packages=False).create(directory)
    inventory=json.loads(subprocess.check_output([str(python),'-m','pip','list','--format=json'],text=True,creationflags=HIDDEN))
    versions={e['name'].lower().replace('_','-'):e['version'] for e in inventory}
    wheels=cache/'mia-original/wheels'
    for entry in sorted(lock['packages'],key=lambda e:e['name']!='pip'):
        if versions.get(entry['name'].lower().replace('_','-'))==entry['version']:continue
        wheel=wheels/entry['filename'];source=seed/'mia-original/wheels'/entry['filename'] if seed else None
        download(entry,wheel,source)
        subprocess.run([str(python),'-m','pip','install','--no-index','--no-deps',str(wheel)],check=True,creationflags=HIDDEN,stdout=sys.stdout,stderr=subprocess.STDOUT)
    subprocess.run([str(python),'-m','pip','check'],check=True,creationflags=HIDDEN,stdout=sys.stdout,stderr=subprocess.STDOUT)
    subprocess.run([str(python),'-I','-c','import torch,numpy,einops; assert torch.cuda.is_available(); print(torch.__version__,torch.cuda.get_device_name())'],check=True,creationflags=HIDDEN,stdout=sys.stdout,stderr=subprocess.STDOUT)
    inventory=json.loads(subprocess.check_output([str(python),'-m','pip','list','--format=json'],text=True,creationflags=HIDDEN))
    (cache/'mia-original/runtime-manifest.json').write_text(json.dumps(dict(python=sys.version,python_executable=str(python),isolated=True,packages=inventory),indent=2))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--cache',type=Path,default=Path(os.environ['LOCALAPPDATA'])/'LocalCharacter/providers')
    parser.add_argument('--seed-cache',type=Path);parser.add_argument('--skip-runtime',action='store_true')
    args=parser.parse_args();root=Path(__file__).resolve().parent
    if os.name!='nt':raise ValueError('This provider archive targets Windows x64')
    args.cache.mkdir(parents=True,exist_ok=True);lock=json.loads((root/'provider-release-lock.json').read_text())
    extract(args.archive,args.cache,lock);print('Verified native providers and inference source',flush=True)
    for entry in lock['models']:
        destination=args.cache/entry['path'];seed=args.seed_cache/entry['path'] if args.seed_cache else None
        if not destination.is_file() and not seed and shutil.disk_usage(args.cache).free<entry['bytes']+5*1024**3:raise ValueError('Insufficient model cache disk space')
        download(entry,destination,seed);print('Verified model',entry['path'],flush=True)
    if not args.skip_runtime:runtime(args.cache,json.loads((root/'mia-runtime-lock.json').read_text()),args.seed_cache)
    (args.cache/'provider-installation.json').write_text(json.dumps(dict(schema_version=1,release_lock_sha256=sha(root/'provider-release-lock.json'),models=lock['models']),indent=2))
    print('LOCAL_CHARACTER_PROVIDERS_READY',args.cache,flush=True)

if __name__=='__main__':main()
