# SPDX-License-Identifier: GPL-3.0-or-later
"""Install a separately licensed SAM provider into its own Python 3.11 environment."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile
sys.path.insert(0,str(Path(__file__).parent))
from sam_pose_protocol import SAM_REV,DINO_REV,HF_REV,MODEL_REPO,MODELS,ARCHIVES,sha,source_files

def run(command):
    subprocess.run(command,check=True,stdout=sys.stdout,stderr=subprocess.STDOUT,
                   creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)

class HiddenVenv(venv.EnvBuilder):
    def _call_new_python(self,context,*args,**kwargs):
        # venv's ensurepip child must also stay hidden in a Blender-launched setup.
        if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
        return super()._call_new_python(context,*args,**kwargs)

def sources(provider):
    for folder,(repo,revision,expected) in ARCHIVES.items():
        destination=provider/folder
        marker=destination/'.rigmodo-source-pin'
        if marker.is_file() and marker.read_text()==revision:continue
        print('Downloading pinned '+repo+' source',flush=True)
        with tempfile.TemporaryDirectory(dir=provider) as tmp:
            archive=Path(tmp)/'source.zip'
            urllib.request.urlretrieve('https://codeload.github.com/facebookresearch/'+repo+'/zip/'+revision,archive)
            if sha(archive)!=expected:raise ValueError(repo+' source checksum failed')
            with zipfile.ZipFile(archive) as z:
                for entry in z.infolist():
                    parts=Path(entry.filename).parts
                    if len(parts)<2:continue
                    path=(destination/Path(*parts[1:])).resolve()
                    if not path.is_relative_to(destination.resolve()):raise ValueError('Unsafe source archive')
                    if entry.is_dir():path.mkdir(parents=True,exist_ok=True)
                    else:
                        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(z.read(entry))
        marker.write_text(revision)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--provider',type=Path,required=True);ap.add_argument('--models',type=Path,required=True)
    ap.add_argument('--runtime-only',action='store_true');args=ap.parse_args()
    if sys.version_info[:2]!=(3,11):raise ValueError('Use Python 3.11 for SAM provider installation')
    provider=args.provider.resolve();provider.mkdir(parents=True,exist_ok=True)
    sources(provider)
    runtime=provider/'runtime';python=runtime/'Scripts/python.exe'
    if not python.is_file():HiddenVenv(with_pip=True).create(runtime)
    run([str(python),'-m','pip','install','--disable-pip-version-check','pip==25.2'])
    run([str(python),'-m','pip','install','--disable-pip-version-check','torch==2.7.1','torchvision==0.22.1',
         '--index-url','https://download.pytorch.org/whl/cu128'])
    run([str(python),'-m','pip','install','--disable-pip-version-check','numpy==1.26.4','pillow==11.3.0',
         'opencv-python==4.11.0.86','pytorch-lightning==2.5.5','yacs==0.1.8','einops==0.8.1',
         'timm==1.0.20','roma==1.5.4','omegaconf==2.3.0','braceexpand==0.1.7','huggingface-hub==0.35.3','termcolor==3.1.0'])
    if args.runtime_only:
        print('RIGMODO_SAM_RUNTIME_READY; approved checkpoints still required',flush=True);return
    models=args.models.resolve();models.mkdir(parents=True,exist_ok=True)
    if not all((models/n).is_file() for n in (*MODELS,'model_config.yaml')):
        # Uses the user's existing HF authentication. Never requests/accepts gated access for them.
        code='from huggingface_hub import snapshot_download; snapshot_download(repo_id='+repr(MODEL_REPO)+', revision='+repr(HF_REV)+', local_dir='+repr(str(models))+', allow_patterns='+repr([*MODELS,'model_config.yaml','LICENSE'])+')'
        run([str(python),'-c',code])
    for name,expected in MODELS.items():
        if sha(models/name)!=expected:raise ValueError('Wrong or incomplete SAM checkpoint: '+name)
    (provider/'installation.json').write_text(json.dumps(dict(schema_version=1,sam_revision=SAM_REV,dino_revision=DINO_REV,hf_revision=HF_REV,
         models=str(models),config_sha256=sha(models/'model_config.yaml'),sources=source_files(provider)),indent=2))
    print('RIGMODO_SAM_PROVIDER_READY',flush=True)

if __name__=='__main__':main()
