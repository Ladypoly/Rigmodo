"""Extract the exact releases into a short private path; reuse pinned local weights."""
import importlib.util,json,os,tempfile,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1];directory=Path(tempfile.mkdtemp(prefix='lckf-'))
extension=directory/'extension';extension.mkdir()
with zipfile.ZipFile(root/'artifacts/local_character-0.8.0.zip') as archive:archive.extractall(extension)
spec=importlib.util.spec_from_file_location('installer',extension/'provider_install.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
lock=json.loads((extension/'provider-release-lock.json').read_text());providers=directory/'providers'
module.extract(root/'artifacts/local_character-windows-providers.zip',providers,lock)
for name,sha in __import__('json').loads((extension/'provider-release-lock.json').read_text())['files'].items():
    assert module.sha(providers/name)==sha
source=Path(os.environ['LOCALAPPDATA'])/'LocalCharacter/providers/kimodo-5679ff1'
for path in (source/'weights').rglob('*'):
    if path.is_file() and path.suffix=='.gguf':
        target=providers/'kimodo-5679ff1'/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);os.link(path,target)
record=dict(extension=str(extension),provider=str(providers/'kimodo-5679ff1'),output=str(directory/'results'))
(root/'artifacts/keyframe-archive-test-paths.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
