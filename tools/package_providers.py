"""Package verified native binaries, inference source and notices; no AI checkpoints."""
import hashlib
import json
import os
from pathlib import Path
import urllib.request
import zipfile

root=Path(__file__).resolve().parents[1];cache=Path(os.environ['LOCALAPPDATA'])/'LocalCharacter/providers'
artifact=root/'artifacts/local_character-windows-providers.zip';artifact.parent.mkdir(exist_ok=True)
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
mia=cache/'mia-original';licenses=mia/'licenses';licenses.mkdir(exist_ok=True)
previous_lock=json.loads((root/'provider-release-lock.json').read_text())
shape_pin=previous_lock['shape2vec_source_revision']
with urllib.request.urlopen(f'https://raw.githubusercontent.com/1zb/3DShape2VecSet/{shape_pin}/LICENSE',timeout=30) as response:
    (licenses/'3DShape2VecSet.MIT.txt').write_bytes(response.read())
with urllib.request.urlopen('https://huggingface.co/jasongzy/Make-It-Animatable/resolve/ca0daf6cb164f939e77bf32667513fc7558d5f98/README.md',timeout=30) as response:
    (licenses/'MIA-model-card.md').write_bytes(response.read())
providers=['skin-tokens-46dbfec','kimodo-5679ff1','mia-original'];files={}
for name in providers:
    directory=cache/name
    if name!='mia-original':
        manifest=json.loads((directory/'build-manifest.json').read_text())
        for relative,expected in manifest['binaries'].items():assert sha(directory/'bin'/relative)==expected
        for path in (directory/'bin').iterdir():
            if path.is_file():files[f'{name}/bin/{path.name}']=path
        files[f'{name}/build-manifest.json']=directory/'build-manifest.json'
        # Corresponding source is retained with native licenses; no compiler or
        # shader SDK installation is required by the prebuilt runtime.
        for path in (directory/'source').rglob('*'):
            relative=path.relative_to(directory)
            if path.is_file() and '.git' not in relative.parts and (path.suffix.lower() in {'.c','.cc','.cpp','.h','.hpp','.in','.cmake','.txt','.md','.py','.json','.glsl','.comp','.vert','.frag'} or path.name.startswith(('LICENSE','NOTICE','COPYING'))):
                if path.stat().st_size<=10*1024**2:files[f'{name}/{relative.as_posix()}']=path
        files[f'{name}/source/LICENSE']=directory/'source/LICENSE'
        files[f'{name}/source/ggml/LICENSE']=directory/'source/ggml/LICENSE'
    else:
        for relative in ('model.py','models_ae.py','util/dataset_mixamo.py','LICENSE'):
            files[f'{name}/source/{relative}']=directory/'source'/relative
    if (directory/'licenses').exists():
        for path in (directory/'licenses').rglob('*'):
            if path.is_file():files[f'{name}/{path.relative_to(directory).as_posix()}']=path
skin=cache/'skin-tokens-46dbfec'
for name in ('LICENSE','README.md','MANIFEST.json','SHA256SUMS'):
    if (skin/'models'/name).exists():files[f'skin-tokens-46dbfec/models/{name}']=skin/'models'/name
for key,path in [('json.MIT.txt',skin/'json/LICENSE.MIT')]:
    if path.is_file():files['skin-tokens-46dbfec/licenses/'+key]=path
files['mia-original/licenses/Apache-2.0.txt']=root/'licenses/Apache-2.0.txt'
with zipfile.ZipFile(artifact,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for relative,path in sorted(files.items()):archive.write(path,relative)
models=[]
model_specs=[('mia-original','jasongzy/Make-It-Animatable','ca0daf6cb164f939e77bf32667513fc7558d5f98','',[(f'models/{name}',f'output/best/new/{name}') for name in ('joints.pth','joints_coarse.pth')]),
 ('skin-tokens-46dbfec','LocalAI-io/SkinTokens-GGUF','2c55d38ffe01871c6956103926cc4a40bd7acc8a','models',[(f'F16/{name}',f'F16/{name}') for name in ('mesh-encoder.gguf','skin-vae.gguf','tokenrig.gguf')]),
 ('kimodo-5679ff1','LocalAI-io/Kimodo-SOMA-RP-v1.1-GGML','65f8b8ab34ee7524161cc87b20ae4cb4f5d3a12d','weights',[('models/kimodo-soma-rp-v1.1-f32.gguf','models/kimodo-soma-rp-v1.1-f32.gguf')]),
 ('kimodo-5679ff1','LocalAI-io/Llama-3-Kimodo-GGML','3e8d958803beaddb6011ac534f2be972e2710c7d','weights',[(name,name) for name in ('Llama-3-Kimodo-Q8_0.gguf','tokenizer.gguf')])]
for provider,repo,revision,prefix,entries in model_specs:
    available={f['rfilename'] for f in json.load(urllib.request.urlopen(f'https://huggingface.co/api/models/{repo}/revision/{revision}',timeout=30))['siblings']}
    for local,remote in entries:
        path=cache/provider/prefix/local
        # MIA stores checkpoints under models locally; resolve its pinned HF path.
        if remote not in available and 'models/'+remote in available:remote='models/'+remote
        if remote not in available:raise ValueError('Missing pinned model path: '+repo+'/'+remote)
        models.append(dict(path=f'{provider}/{prefix+"/" if prefix else ""}{local}',url=f'https://huggingface.co/{repo}/resolve/{revision}/{remote}',
                           sha256=sha(path),bytes=path.stat().st_size))
lock=dict(schema_version=1,platform='windows_x64',native_archive_sha256=sha(artifact),native_archive_bytes=artifact.stat().st_size,
          files={name:sha(path) for name,path in files.items()},models=models,shape2vec_source_revision=shape_pin)
(root/'provider-release-lock.json').write_text(json.dumps(lock,indent=2))
(root/'mia-runtime-lock.json').write_bytes((root/'tools/mia-runtime-lock.json').read_bytes())
print('PROVIDER_ARCHIVE',artifact,artifact.stat().st_size,'files',len(files),'checkpoint bytes',sum(m['bytes'] for m in models))
