# SPDX-License-Identifier: GPL-3.0-or-later
"""One persistent model root; runtimes/source stay in the provider cache."""
import argparse,hashlib,json,os,shutil,sys
from pathlib import Path

BASE=Path(os.environ.get('LOCALAPPDATA',Path.home()/'AppData/Local'))/'LocalCharacter'
CONFIG=BASE/'model-storage.json'
LAYOUT=(('mia-original','models','mia'),('skin-tokens-46dbfec','models','skintokens'),
    ('kimodo-5679ff1','weights','kimodo'),('sam-3d-body-b5c765a','models','sam-3d-body'),
    ('unimate-b78c780','weights','unimate/weights'),('unimate-b78c780','text_encoder','unimate/text_encoder'),
    ('unirig-69ee59d','models','unirig'))
MB_FILES=('mmm_v6_soma_fp32.onnx','soma_n1.json','LICENSE.md','LICENSE')

def current():
    try:return Path(json.loads(CONFIG.read_text())['root'])
    except FileNotFoundError:return None

def preferred():return current() or (Path(os.environ['RIGMODO_MODEL_DIRECTORY']) if os.environ.get('RIGMODO_MODEL_DIRECTORY') else Path('R:/AI/Models/Rigmodo') if Path('R:/').is_dir() else BASE/'models')

def ensure():
    if current() is None:migrate(preferred())

def resolve(path,providers=None,models_root=None):
    path=Path(path);root=Path(models_root) if models_root is not None else current()
    if root is None:return path
    providers=Path(providers or BASE/'providers')
    for provider,old,new in LAYOUT:
        try:return root/new/path.absolute().relative_to((providers/provider/old).absolute())
        except ValueError:pass
    for name in MB_FILES:
        if path.absolute()==(providers/'motionbricks-54fc563'/name).absolute():return root/'motionbricks'/name
    return path

def component(name,fallback):
    root=current();return root/name if root else Path(fallback)

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def lock_matches(record,path):
    raw=Path(path).read_bytes().replace(b'\r\n',b'\n')
    return record['lock_sha256'] in {hashlib.sha256(raw).hexdigest(),hashlib.sha256(raw.replace(b'\n',b'\r\n')).hexdigest()}

def migrate(root,providers=None,config=None,cleanup=True):
    root=Path(root).absolute();providers=Path(providers or BASE/'providers').absolute();config=Path(config or CONFIG)
    if not root.is_absolute() or root==Path(root.anchor) or root.is_relative_to(providers) or providers.is_relative_to(root):raise ValueError('Choose a separate model folder outside the provider/runtime cache')
    previous=Path(json.loads(config.read_text())['root']).absolute() if config.exists() else None
    if previous and previous!=root and (root.is_relative_to(previous) or previous.is_relative_to(root)):raise ValueError('Choose a model folder outside the existing model tree')
    root.mkdir(parents=True,exist_ok=True);entries=[]
    for provider,old,new in LAYOUT:
        source=previous/new if previous else providers/provider/old
        if source.is_dir():entries.extend((p,root/new/p.relative_to(source),p.resolve().is_relative_to((previous or providers).resolve())) for p in source.rglob('*') if p.is_file())
        legacy=providers/provider/old
        if previous and legacy.is_dir():entries.extend((p,root/new/p.relative_to(legacy),p.resolve().is_relative_to(providers.resolve())) for p in legacy.rglob('*') if p.is_file())
    mb=providers/'motionbricks-54fc563'
    mb=previous/'motionbricks' if previous else mb
    entries.extend((mb/name,root/'motionbricks'/name,(mb/name).resolve().is_relative_to((previous or providers).resolve())) for name in MB_FILES if (mb/name).is_file())
    if previous:entries.extend((providers/'motionbricks-54fc563'/name,root/'motionbricks'/name,(providers/'motionbricks-54fc563'/name).resolve().is_relative_to(providers.resolve())) for name in MB_FILES if (providers/'motionbricks-54fc563'/name).is_file())
    record=providers/'unirig-69ee59d/installation.json'
    if record.is_file() and not previous:
        source=Path(json.loads(record.read_text())['checkpoint'])
        if source.is_file() and not source.absolute().is_relative_to(providers):entries.append((source,root/'unirig/skeleton.safetensors',False))
    entries=list({str(target):(source,target,owned) for source,target,owned in entries}.values());verified=[];copied=0;linked=0
    for source,target,owned in entries:
        if not target.resolve().is_relative_to(root.resolve()):raise ValueError('Model target resolves outside the shared folder')
        if source.resolve()==target.resolve():
            verified.append(dict(source=str(source),target=str(target),sha256=sha(source),bytes=source.stat().st_size,owned=False));continue
        target.parent.mkdir(parents=True,exist_ok=True);expected=sha(source)
        if target.exists():
            if sha(target)!=expected:raise ValueError('Different model already exists at '+str(target))
        else:
            print('Storing '+str(target.relative_to(root)),flush=True)
            part=target.with_name(target.name+'.rigmodo-part')
            try:
                part.unlink(missing_ok=True)
                try:os.link(source,part);linked+=1
                except OSError:shutil.copyfile(source,part);copied+=source.stat().st_size
                if sha(part)!=expected:raise ValueError('Model copy verification failed: '+str(target))
                part.replace(target)
            finally:part.unlink(missing_ok=True)
        verified.append(dict(source=str(source),target=str(target),sha256=expected,bytes=source.stat().st_size,owned=owned))
    # Copies are complete before changing any active paths or removing any cache files.
    report=dict(schema_version=1,root=str(root),models=verified,copied_bytes=copied,hardlinked_files=linked)
    config.parent.mkdir(parents=True,exist_ok=True);part=config.with_suffix('.tmp');part.write_text(json.dumps(report,indent=2),encoding='utf-8');part.replace(config)
    for entry in verified:
        source=Path(entry['source']);target=Path(entry['target'])
        if entry['owned'] and cleanup:
            if not (source.resolve().is_relative_to(providers.resolve()) or previous and source.resolve().is_relative_to(previous.resolve())) or not target.resolve().is_relative_to(root.resolve()):raise ValueError('Model cleanup escaped its managed directories')
            if sha(source)!=entry['sha256'] or sha(target)!=entry['sha256']:raise ValueError('Model changed during migration; original retained')
            source.unlink()
    print('SHARED_MODELS_READY',json.dumps(dict(root=str(root),files=len(verified),copied_bytes=copied,hardlinked_files=linked)),flush=True)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--providers',type=Path);p.add_argument('--config',type=Path);p.add_argument('--keep-cache-copies',action='store_true')
    args=p.parse_args();migrate(args.root,args.providers,args.config,not args.keep_cache_copies)
