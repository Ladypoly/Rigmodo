"""Create a private temporary test project, export fixtures and run real Unity acceptance."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--blender',default=r'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe')
parser.add_argument('--unity',default=r'C:\Program Files\Unity\Hub\Editor\6000.3.21f1\Editor\Unity.exe')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
workspace=Path(tempfile.mkdtemp(prefix='local-character-acceptance-')).resolve()
fixtures=workspace/'fixtures';project=workspace/'unity'
print('Private acceptance workspace:',workspace,flush=True)
subprocess.run([args.blender,'--background','--factory-startup','--disable-autoexec','--python-exit-code','1',
                '--python',str(root/'tests/blender_acceptance.py'),'--',str(fixtures)],check=True)
blender_results=json.loads((fixtures/'blender-results.json').read_text())
assert all(c['status']=='pass' for c in blender_results)
editor=project/'Assets/LocalCharacter/Editor';editor.mkdir(parents=True)
for file in (root/'unity/Editor').glob('*.cs'):
    shutil.copyfile(file,editor/file.name)
shutil.copyfile(root/'tests/UnityAcceptance.cs',editor/'UnityAcceptance.cs')
shutil.copyfile(root/'tests/AnimationAcceptance.cs',editor/'AnimationAcceptance.cs')
for name in ('SyntheticT','SyntheticA','ShanePreserved','SyntheticMotionGeneric','SyntheticMotionHumanoid'):
    shutil.copytree(fixtures/name,project/'Assets/Fixtures'/name)
(project/'Packages').mkdir();(project/'Packages/manifest.json').write_text('{"dependencies":{}}')
(project/'ProjectSettings').mkdir();(project/'ProjectSettings/ProjectVersion.txt').write_text('m_EditorVersion: 6000.3.21f1\n')
subprocess.run([args.unity,'-batchmode','-nographics','-projectPath',str(project),'-executeMethod',
                'LocalCharacter.Tests.UnityAcceptance.Run','-logFile',str(project/'acceptance.log')],check=True)
unity_results=json.loads((project/'unity-results.json').read_text())
assert all(c['passed'] and c['humanoid_pose_applied'] for c in unity_results['cases'])
assert all(c['passed'] for c in unity_results['animations'])
compact={'blender':blender_results,'unity_version':unity_results['unity_version'],
         'unity':[{k:v for k,v in c.items() if k!='validation'} | {'validation':{k:v for k,v in c['validation'].items() if k!='calibration'}} for c in unity_results['cases']],
         'animations':unity_results['animations']}
(workspace/'summary.json').write_text(json.dumps(compact,indent=2))
print('LOCAL_CHARACTER_ALL_CHECKS_PASSED',workspace/'summary.json',flush=True)
