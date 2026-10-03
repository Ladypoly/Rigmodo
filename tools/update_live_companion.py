"""Update only the previously owned validation companion; keep original project files."""
import hashlib,json,shutil,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
baseline=json.loads((root/'docs/live-project-baseline.json').read_text());project=Path(baseline['project']).resolve()
target=project/'Assets/LocalCharacterValidation';editor=target/'Editor'
assembly=editor/'LocalCharacter.Validation.Editor.asmdef'
assert assembly.is_file() and json.loads(assembly.read_text())['name']=='LocalCharacter.Validation.Editor'
def originals_unchanged():
    return all(hashlib.sha256((project/name).read_bytes()).hexdigest()==value for name,value in baseline['hashes'].items())
assert originals_unchanged()
backup=Path(tempfile.mkdtemp(prefix='local-character-live-companion-backup-'))
shutil.copytree(editor,backup/'Editor')
if (target/'Runtime').exists():shutil.copytree(target/'Runtime',backup/'Runtime')
for path in (root/'unity/Editor').glob('*.cs'):shutil.copy2(path,editor/path.name)
runtime=target/'Runtime';runtime.mkdir(exist_ok=True)
for path in (root/'unity/Runtime').glob('*'):
    if path.suffix in {'.cs','.asmdef'}:shutil.copy2(path,runtime/path.name)
data=json.loads(assembly.read_text());data['references']=sorted(set(data['references'])|{'LocalCharacter.Runtime'})
assembly.write_text(json.dumps(data,indent=2)+'\n')
for name in ('LICENSE','README.md'):shutil.copy2(root/'unity'/name,target/name)
assert originals_unchanged()
result=dict(version='0.5.0',project=str(project),owned_companion=str(target),backup=str(backup),original_monitored_files_preserved=True)
(root/'docs/live-companion-2026-10-03.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
