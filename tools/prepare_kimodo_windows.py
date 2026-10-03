"""Pinned native Kimodo build/download, isolated from the user's Kimodo checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

SOURCE_PIN='5679ff19ba0a522c0b0516e9a9d402fe1af2c027'
GGML_PIN='8c63e70982c95ceb862e3a1073a2c1beef75d60a'
REPOS={
 'LocalAI-io/Kimodo-SOMA-RP-v1.1-GGML':('65f8b8ab34ee7524161cc87b20ae4cb4f5d3a12d',['models/kimodo-soma-rp-v1.1-f32.gguf']),
 'LocalAI-io/Llama-3-Kimodo-GGML':('3e8d958803beaddb6011ac534f2be972e2710c7d',['Llama-3-Kimodo-Q8_0.gguf','tokenizer.gguf']),
}
parser=argparse.ArgumentParser();parser.add_argument('--download',action='store_true');parser.add_argument('--build',action='store_true')
args=parser.parse_args()
cache=Path(os.environ['LOCALAPPDATA'])/'LocalCharacter/providers/kimodo-5679ff1'
dependencies=cache.parent/'skin-tokens-46dbfec';build=Path(r'C:\LCBuild\kmd567vk')
cache.mkdir(parents=True,exist_ok=True)
def run(cmd,**kwargs):
 print('Running',*map(str,cmd[:2]),flush=True);return subprocess.run(list(map(str,cmd)),check=True,**kwargs)
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
if args.download:
 lock={}
 for repo,(revision,files) in REPOS.items():
  licenses=cache/'licenses'/repo.replace('/','__');licenses.mkdir(parents=True,exist_ok=True)
  api=json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{revision}'))
  available={f['rfilename'] for f in api['siblings']}
  for name in available:
   if '/' not in name and (name.startswith(('LICENSE','NOTICE','USE_POLICY')) or name in {'README.md','MANIFEST.json'}):
    urllib.request.urlretrieve(f'https://huggingface.co/{repo}/resolve/{revision}/{name}',licenses/name)
  manifest=json.loads((licenses/'MANIFEST.json').read_text())
  if manifest['format']!='kimodo-gguf-manifest-v1':raise SystemExit('Unknown manifest format')
  selected=[]
  for relative in files:
   entry=next(f for f in manifest['files'] if f['path']==relative)
   path=cache/'weights'/relative;path.parent.mkdir(parents=True,exist_ok=True)
   if not path.exists() or path.stat().st_size!=entry['bytes'] or sha(path)!=entry['sha256']:
    if shutil.disk_usage(cache).free<entry['bytes']+2*1024**3:raise SystemExit('Insufficient cache disk space')
    temporary=path.with_suffix('.download')
    print('Downloading',repo,relative,entry['bytes'],flush=True)
    urllib.request.urlretrieve(f'https://huggingface.co/{repo}/resolve/{revision}/{relative}',temporary)
    if temporary.stat().st_size!=entry['bytes'] or sha(temporary)!=entry['sha256']:raise SystemExit('Download failed size/hash validation')
    os.replace(temporary,path)
   print('Verified',relative,flush=True);selected.append(entry)
  lock[repo]=dict(revision=revision,files=selected,source_revisions=manifest['source_revisions'])
 (cache/'model-lock.json').write_text(json.dumps(lock,indent=2))
if args.build:
 source=cache/'source'
 if not source.exists():
  run(['git','clone','--no-checkout','https://github.com/localai-org/kimodo.cpp.git',source])
  run(['git','-C',source,'checkout','--detach',SOURCE_PIN])
  run(['git','-C',source,'submodule','update','--init'])
 for path,pin in [(source,SOURCE_PIN),(source/'ggml',GGML_PIN)]:
  if subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()!=pin:raise SystemExit('Pinned source mismatch')
  if subprocess.check_output(['git','-C',str(path),'status','--porcelain'],text=True).strip():raise SystemExit('Choose a clean isolated source cache')
 configuration=['cmake','-S',source,'-B',build,'-G','Visual Studio 17 2022','-A','x64','-T','ClangCL',
  '-DBUILD_SHARED_LIBS=ON','-DKIMODO_ENABLE_VULKAN=ON','-DKIMODO_BUILD_TESTS=ON',
  '-DCMAKE_C_FLAGS=-D_CRT_SECURE_NO_WARNINGS',
  '-DCMAKE_CXX_FLAGS_RELEASE=/O2 /UNDEBUG',
  '-DCMAKE_CXX_FLAGS=-D_CRT_SECURE_NO_WARNINGS /EHsc -I'+str(dependencies/'spirv-install/include'),
  '-DSPIRV-Headers_DIR='+str(dependencies/'spirv-install/share/cmake/SPIRV-Headers'),
  '-DVulkan_INCLUDE_DIR='+str(dependencies/'vulkan-headers/include'),
  '-DVulkan_LIBRARY='+str(dependencies/'vulkan-import/vulkan-1.lib'),
  '-DVulkan_GLSLC_EXECUTABLE='+str(dependencies/'shader-tools/Library/bin/glslc.exe')]
 with (cache/'build.log').open('w') as log:
  run(configuration,stdout=log,stderr=subprocess.STDOUT)
  run(['cmake','--build',build,'--config','Release','--target','kmd-generate','kmd-inspect','kimodo-diffusion-test','--parallel','8'],stdout=log,stderr=subprocess.STDOUT)
 binary=cache/'bin';binary.mkdir(exist_ok=True)
 for path in build.rglob('Release/*.dll'):shutil.copy2(path,binary/path.name)
 for name in ('kmd-generate.exe','kmd-inspect.exe','kimodo-diffusion-test.exe'):
  matches=list(build.rglob(name))
  if len(matches)!=1:raise SystemExit('Ambiguous native executable')
  shutil.copy2(matches[0],binary/name)
 for name in ('LICENSE','NOTICE'):shutil.copy2(source/name,binary/name)
 run([binary/'kimodo-diffusion-test.exe'])
 (cache/'build-manifest.json').write_text(json.dumps(dict(source_revision=SOURCE_PIN,ggml_revision=GGML_PIN,
  configuration=list(map(str,configuration)),binaries={p.name:sha(p) for p in binary.iterdir() if p.suffix in {'.exe','.dll'}}),indent=2))
