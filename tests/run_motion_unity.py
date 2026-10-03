"""Import actual generated clips into an isolated Unity 6.3 project."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1];fixtures=Path(sys.argv[1]).resolve()
project=Path(tempfile.mkdtemp(prefix='local-character-motion-unity-'))
editor=project/'Assets/LocalCharacter/Editor';editor.mkdir(parents=True)
for path in (root/'unity/Editor').glob('*'):
    if path.suffix in {'.cs','.asmdef'}:shutil.copy2(path,editor/path.name)
runtime=editor.parent/'Runtime';runtime.mkdir()
for path in (root/'unity/Runtime').glob('*'):
    if path.suffix in {'.cs','.asmdef'}:shutil.copy2(path,runtime/path.name)
shutil.copy2(root/'tests/GeneratedMotionAcceptance.cs',editor/'GeneratedMotionAcceptance.cs')
for directory in fixtures.iterdir():
    if directory.is_dir() and (directory/(directory.name+'.character.json')).exists():
        shutil.copytree(directory,project/'Assets/Fixtures'/directory.name)
(project/'Packages').mkdir();(project/'Packages/manifest.json').write_text('{"dependencies":{}}')
(project/'ProjectSettings').mkdir();(project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.21f1\n')
print('Private motion Unity workspace:',project,flush=True)
process=subprocess.run([r'C:\Program Files\Unity\Hub\Editor\6000.3.21f1\Editor\Unity.exe','-batchmode','-nographics',
    '-projectPath',str(project),'-executeMethod','LocalCharacter.Tests.GeneratedMotionAcceptance.Run','-logFile',str(project/'acceptance.log')])
result=json.loads((project/'motion-results.json').read_text());print(json.dumps(result),flush=True)
assert process.returncode==0 and result['cases'] and all(case['passed'] for case in result['cases'])
print('LOCAL_CHARACTER_MOTION_UNITY_PASSED',project/'motion-results.json')
