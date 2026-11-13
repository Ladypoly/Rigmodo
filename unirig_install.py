# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the pinned inference-only UniRig provider beside existing providers."""
import argparse,hashlib,json,os,subprocess,sys,urllib.request
from pathlib import Path

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def download(url,path,expected):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.is_file():
        if sha(path)==expected:return
        raise ValueError('Existing file has a different checksum: '+str(path))
    part=path.with_name(path.name+'.rigmodo-part')
    try:
        with urllib.request.urlopen(url,timeout=120) as response,part.open('wb') as stream:
            while chunk:=response.read(4*1024*1024):stream.write(chunk)
        if sha(part)!=expected:raise ValueError('Download checksum mismatch: '+path.name)
        part.replace(path)
    finally:part.unlink(missing_ok=True)

def install(provider,checkpoint=None):
    lock=json.loads(Path(__file__).with_name('unirig-lock.json').read_text())
    provider=provider.resolve();source=provider/'unirig_model';source.mkdir(parents=True,exist_ok=True)
    download(f"https://raw.githubusercontent.com/VAST-AI-Research/UniRig/{lock['upstream_revision']}/LICENSE",provider/'UNIRIG-LICENSE',lock['upstream_license_sha256'])
    originals=provider/'upstream';originals.mkdir(exist_ok=True)
    for name,expected in lock['source_files'].items():
        path=originals/name
        download(f"https://raw.githubusercontent.com/{lock['source_repo']}/{lock['source_revision']}/{name}",path,expected)
        target=source/Path(name).name if name!='LICENSE' else provider/'LICENSE'
        text=path.read_text()
        if name.endswith('unirig_ar.py'):
            text=text.replace('import comfy.ops','').replace('comfy.ops.disable_weight_init','nn')
        if name.endswith('michelangelo_encoder.py'):
            text=text.replace('import comfy.ops','').replace('import comfy.utils','from safetensors.torch import load_file')
            text=text.replace('comfy.ops.disable_weight_init','nn').replace('comfy.utils.load_torch_file','load_file')
        if name.endswith('parse_encoder.py'):
            text='\n'.join(line for line in text.splitlines() if 'ptv3obj' not in line and 'PointTransformerV3Object' not in line)
        target.write_text(text,encoding='utf-8')
    (source/'attention.py').write_text('''# SPDX-License-Identifier: GPL-3.0-or-later
# Standalone SDPA dispatch for the pinned UniRig Michelangelo implementation.
from torch.nn.functional import scaled_dot_product_attention
def comfy_attention(q,k,v,heads):
    return scaled_dot_product_attention(q.transpose(1,2),k.transpose(1,2),v.transpose(1,2)).transpose(1,2)
''')
    deps=provider/'python'
    if not (deps/'transformers').is_dir() or not (deps/'torch_cluster').is_dir():
        wheel='https://data.pyg.org/whl/torch-2.7.0%2Bcu128/torch_cluster-1.6.3%2Bpt27cu128-cp311-cp311-win_amd64.whl'
        subprocess.run([sys.executable,'-m','pip','install','--disable-pip-version-check','--target',str(deps),
            'numpy==2.2.6','scipy==1.15.2','transformers==4.51.3','safetensors==0.5.3','huggingface-hub==0.30.2',wheel],check=True)
    if checkpoint is None:
        candidates=[Path('C:/Tools/AI/ComfyUI_windows_portable/ComfyUI/models/unirig/skeleton.safetensors'),
            Path.home()/'ComfyUI/models/unirig/skeleton.safetensors']
        checkpoint=next((p for p in candidates if p.is_file() and sha(p)==lock['model_sha256']),provider/'models'/lock['model_file'])
    checkpoint=checkpoint.resolve()
    download(f"https://huggingface.co/{lock['model_repo']}/resolve/{lock['model_revision']}/{lock['model_file']}",checkpoint,lock['model_sha256'])
    hashes={p.relative_to(provider).as_posix():sha(p) for p in source.iterdir() if p.is_file()}
    record=dict(schema_version=1,source_revision=lock['source_revision'],checkpoint=str(checkpoint),
        checkpoint_sha256=lock['model_sha256'],source_hashes=hashes,base_python=sys.executable,
        dependencies='transformers 4.51.3; torch-cluster 1.6.3 pt27cu128; existing Torch 2.7.1 cu128',
        model_reused=not checkpoint.is_relative_to(provider))
    (provider/'installation.json').write_text(json.dumps(record,indent=2))
    # Validate actual imports in the same isolated interpreter used for inference.
    code="import sys;sys.path.insert(0,sys.argv[1]);import torch,torch_cluster,safetensors;from transformers import OPTForCausalLM;assert torch.cuda.is_available();assert torch.__version__.startswith('2.7.');assert len(torch_cluster.fps(torch.rand(8,3,device='cuda'),ratio=.25))==2;print(torch.cuda.get_device_name())"
    try:subprocess.run([sys.executable,'-I','-c',code,str(deps)],check=True)
    except Exception:(provider/'installation.json').unlink(missing_ok=True);raise
    print('UNIRIG_PROVIDER_READY',json.dumps(record),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--provider',type=Path,required=True);ap.add_argument('--checkpoint',type=Path)
    args=ap.parse_args();install(args.provider,args.checkpoint)
