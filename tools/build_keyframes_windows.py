"""Build the independent keyframe entry point against pinned native sources."""
import hashlib,json,os,shutil,subprocess
from pathlib import Path
root=Path(__file__).resolve().parents[1]
provider=Path(os.environ['LOCALAPPDATA'])/'LocalCharacter/providers/kimodo-5679ff1'
build=Path(r'C:\LCBuild\kmd-keyframes');source=root/'native/kimodo-keyframes'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((provider/'build-manifest.json').read_text())
if manifest['source_revision']!='5679ff19ba0a522c0b0516e9a9d402fe1af2c027' or manifest['ggml_revision']!='8c63e70982c95ceb862e3a1073a2c1beef75d60a':
    raise SystemExit('The keyframe adapter requires the pinned Kimodo/GGML provider')
release=json.loads((root/'provider-release-lock.json').read_text())
for name,digest in release['files'].items():
    if name.startswith('kimodo-5679ff1/source/') and '/local-character-keyframes/' not in name:
        if sha(provider.parent/name)!=digest:raise SystemExit('Pinned native source changed: '+name)
for name,digest in manifest['binaries'].items():
    if name.startswith('ggml') and sha(provider/'bin'/name)!=digest:raise SystemExit('Pinned GGML runtime changed')
subprocess.run(['cmake','-S',str(source),'-B',str(build),'-G','Visual Studio 17 2022','-A','x64','-T','ClangCL',
    '-DKIMODO_SOURCE_DIR='+str(provider/'source'),'-DGGML_BUILD_DIR=C:/LCBuild/kmd567vk/ggml'],check=True)
subprocess.run(['cmake','--build',str(build),'--config','Release','--parallel','8'],check=True)
destination=provider/'bin/kmd-keyframes.exe';shutil.copy2(build/'Release/kmd-keyframes.exe',destination)
owned=provider/'source/local-character-keyframes';owned.mkdir(exist_ok=True)
shutil.copy2(root/'licenses/Apache-2.0.txt',owned/'LICENSE')
for file in source.iterdir():
    if file.is_file():shutil.copy2(file,owned/file.name)
manifest=json.loads((provider/'build-manifest.json').read_text())
manifest['binaries'][destination.name]=sha(destination)
manifest['keyframe_adapter']=dict(version=1,source={p.name:sha(p) for p in source.iterdir() if p.is_file()},sampler='pinned_conditioned_DDIM',build=str(build))
(provider/'build-manifest.json').write_text(json.dumps(manifest,indent=2))
print('KEYFRAME_ADAPTER_BUILT',destination,sha(destination),flush=True)
