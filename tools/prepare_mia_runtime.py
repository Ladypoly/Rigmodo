"""Reproducible isolated Python 3.11 CUDA inference runtime, never install into Blender.

Invoke with an existing Python 3.11 interpreter. Downloads only hash-pinned wheels;
all packages and their notices stay in the per-user provider cache.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request
import venv

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    if sys.version_info[:2]!=(3,11) or os.name!='nt':raise SystemExit('This Windows runtime lock requires Python 3.11')
    lock=json.loads(Path(__file__).with_name('mia-runtime-lock.json').read_text())
    cache=Path(os.environ['LOCALAPPDATA'])/'LocalCharacter/providers/mia-original'
    runtime=cache/'runtime';python=runtime/'Scripts/python.exe'
    if not python.exists():venv.EnvBuilder(with_pip=True,system_site_packages=False).create(runtime)
    # Record actual versions through this environment, never the caller's packages.
    installed=json.loads(subprocess.check_output([str(python),'-m','pip','list','--format=json'],text=True))
    installed={entry['name'].lower().replace('_','-'):entry['version'] for entry in installed}
    wheels=cache/'wheels';wheels.mkdir(parents=True,exist_ok=True)
    for entry in lock['packages']:
        if installed.get(entry['name'].lower().replace('_','-'))==entry['version']:continue
        path=wheels/entry['filename']
        if not path.exists() or sha(path)!=entry['sha256']:
            temporary=path.with_suffix('.download')
            print('Downloading pinned',entry['name'],entry['version'],flush=True)
            with urllib.request.urlopen(entry['url'],timeout=60) as response,temporary.open('wb') as stream:
                while chunk:=response.read(1024**2):stream.write(chunk)
            if sha(temporary)!=entry['sha256']:raise SystemExit('Wheel hash mismatch: '+entry['filename'])
            os.replace(temporary,path)
        subprocess.run([str(python),'-m','pip','install','--no-index','--no-deps',str(path)],check=True)
    subprocess.run([str(python),'-m','pip','check'],check=True)
    inventory=json.loads(subprocess.check_output([str(python),'-m','pip','list','--format=json'],text=True))
    (cache/'runtime-manifest.json').write_text(json.dumps(dict(python=sys.version,python_executable=str(python),
        isolated=True,wheel_lock_sha256=sha(Path(__file__).with_name('mia-runtime-lock.json')),packages=inventory),indent=2))
    subprocess.run([str(python),'-I','-c','import torch,numpy,einops; assert torch.cuda.is_available(); print(torch.__version__,torch.cuda.get_device_name())'],check=True)
    print('MIA_ISOLATED_RUNTIME_READY',python,flush=True)

if __name__=='__main__':main()
