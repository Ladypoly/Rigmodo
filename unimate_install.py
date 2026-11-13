# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned inference-only UniMate installation; reuse the existing CUDA Torch."""
import argparse,hashlib,json,subprocess,sys,urllib.request,venv,zipfile
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
        print('Downloading '+path.name,flush=True)
        with urllib.request.urlopen(url,timeout=120) as response,part.open('wb') as stream:
            while chunk:=response.read(4*1024*1024):stream.write(chunk)
        if sha(part)!=expected:raise ValueError('Download checksum mismatch: '+path.name)
        part.replace(path)
    finally:part.unlink(missing_ok=True)

def install(provider):
    import sysconfig
    lock=json.loads(Path(__file__).with_name('unimate-lock.json').read_text())
    provider=provider.resolve();provider.mkdir(parents=True,exist_ok=True)
    (provider/'installation.json').unlink(missing_ok=True)
    archive=provider/'source.zip';download(lock['source_url'],archive,lock['source_sha256'])
    hashes={}
    with zipfile.ZipFile(archive) as bundle:
        prefix=bundle.namelist()[0]
        for entry in bundle.infolist():
            name=entry.filename.removeprefix(prefix)
            if not ((name.startswith('unimate/') and name.endswith('.py')) or name=='LICENSE'):continue
            relative=Path(name)
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid source archive path')
            target=provider/'source'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(bundle.read(entry));hashes[target.relative_to(provider).as_posix()]=sha(target)
    runtime=provider/'runtime';python=runtime/'Scripts/python.exe' if sys.platform=='win32' else runtime/'bin/python'
    if not python.is_file():venv.EnvBuilder(with_pip=True).create(runtime)
    purelib=subprocess.check_output([str(python),'-I','-c','import sysconfig;print(sysconfig.get_path("purelib"))'],text=True).strip()
    # A separate venv supplies small dependencies; the .pth reuses MIA's 3 GB CUDA runtime.
    Path(purelib,'rigmodo_shared_torch.pth').write_text(sysconfig.get_path('purelib')+'\n')
    subprocess.run([str(python),'-I','-m','pip','install','--disable-pip-version-check',*lock['dependencies']],check=True)
    for entry in lock['files']:download(entry['url'],provider/entry['path'],entry['sha256'])
    code='import torch,torch_geometric,torchdiffeq,sentencepiece,transformers;assert torch.cuda.is_available();from transformers import T5EncoderModel,T5Tokenizer;print(torch.cuda.get_device_name(),torch.__version__)'
    subprocess.run([str(python),'-I','-c',code],check=True)
    record=dict(schema_version=1,source_revision=lock['source_revision'],source_hashes=hashes,
        python=str(python),shared_python=sys.executable,lock_sha256=sha(Path(__file__).with_name('unimate-lock.json')))
    (provider/'installation.json').write_text(json.dumps(record,indent=2))
    print('UNIMATE_PROVIDER_READY',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--provider',type=Path,required=True)
    install(ap.parse_args().provider)
