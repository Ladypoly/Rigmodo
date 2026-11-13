# SPDX-License-Identifier: GPL-3.0-or-later
"""Install the official SOMA ONNX model without the demo/TensorRT stack."""
import argparse,json,subprocess,sys,sysconfig,venv
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import model_storage
from unimate_install import download,sha

def install(provider):
    model_storage.ensure()
    provider=provider.resolve();provider.mkdir(parents=True,exist_ok=True)
    lock_path=Path(__file__).with_name('motionbricks-lock.json');lock=json.loads(lock_path.read_text())
    (provider/'installation.json').unlink(missing_ok=True)
    runtime=provider/'runtime';python=runtime/'Scripts/python.exe'
    venv.EnvBuilder(with_pip=True).create(runtime)
    purelib=subprocess.check_output([str(python),'-I','-c','import sysconfig;print(sysconfig.get_path("purelib"))'],text=True).strip()
    Path(purelib,'rigmodo_shared_torch.pth').write_text(sysconfig.get_path('purelib')+'\n')
    subprocess.run([str(python),'-I','-m','pip','install','--disable-pip-version-check',*lock['dependencies']],check=True)
    for entry in lock['files']:download(entry['url'],model_storage.resolve(provider/entry['path']),entry['sha256'])
    code='import torch;import onnxruntime as ort;ort.preload_dlls();assert "CUDAExecutionProvider" in ort.get_available_providers();print(torch.cuda.get_device_name(),ort.__version__)'
    subprocess.run([str(python),'-I','-c',code],check=True)
    (provider/'installation.json').write_text(json.dumps(dict(schema_version=1,lock_sha256=sha(lock_path),python=str(python),shared_python=sys.executable),indent=2))
    print('MOTIONBRICKS_PROVIDER_READY',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--provider',type=Path,required=True);install(ap.parse_args().provider)
