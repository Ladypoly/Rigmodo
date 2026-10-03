"""Reuse an owned private project for real external-avatar crossfade/prefab checks."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
root=Path(__file__).resolve().parents[1];project=Path(sys.argv[1]);turn=Path(sys.argv[2])
assert project.name.startswith('local-character-motion-unity-') and project.parent.name=='Temp'
editor=project/'Assets/LocalCharacter/Editor'
for source in (root/'unity/Editor').glob('*'):
    if source.suffix in {'.cs','.asmdef'}:shutil.copyfile(source,editor/source.name)
for source in (root/'unity/Runtime').glob('*'):
    if source.suffix in {'.cs','.asmdef'}:shutil.copyfile(source,editor.parent/'Runtime'/source.name)
shutil.copyfile(root/'tests/TransitionAcceptance.cs',editor/'TransitionAcceptance.cs')
shutil.copytree(turn,project/'Assets/Fixtures/TurnHUMANOIDTrue',dirs_exist_ok=True)
process=subprocess.run([r'C:\Program Files\Unity\Hub\Editor\6000.3.21f1\Editor\Unity.exe','-batchmode','-nographics','-projectPath',str(project),
    '-executeMethod','LocalCharacter.Tests.TransitionAcceptance.Run','-logFile',str(project/'transition.log')])
print((project/'transition-results.json').read_text(),flush=True);assert process.returncode==0
