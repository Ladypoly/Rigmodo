"""Validate a private AI bundle in a fresh Unity 6.3 project."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
bundle=Path(sys.argv[1]).resolve()
project=Path(tempfile.mkdtemp(prefix='local-character-ai-unity-')).resolve()
editor=project/'Assets/LocalCharacter/Editor';editor.mkdir(parents=True)
for file in (root/'unity/Editor').glob('*.cs'): shutil.copy2(file,editor/file.name)
for name in ('UnityAcceptance.cs','AnimationAcceptance.cs','SkinningAcceptance.cs'):
    shutil.copy2(root/'tests'/name,editor/name)
shutil.copytree(bundle,project/'Assets/Fixtures/ShaneAISkin')
(project/'Packages').mkdir();(project/'Packages/manifest.json').write_text('{"dependencies":{}}')
(project/'ProjectSettings').mkdir();(project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.21f1\n')
print('Private AI Unity workspace:',project,flush=True)
subprocess.run([r'C:\Program Files\Unity\Hub\Editor\6000.3.21f1\Editor\Unity.exe','-batchmode','-nographics',
                '-projectPath',str(project),'-executeMethod','LocalCharacter.Tests.SkinningAcceptance.Run',
                '-logFile',str(project/'acceptance.log')],check=True)
result=json.loads((project/'ai-skin-validation.json').read_text())
assert result['passed'] and result['avatar']['blendshapes']==3
result['avatar'].pop('calibration',None)
(project/'summary.json').write_text(json.dumps(result,indent=2))
print('LOCAL_CHARACTER_AI_UNITY_PASSED',project/'summary.json',flush=True)
