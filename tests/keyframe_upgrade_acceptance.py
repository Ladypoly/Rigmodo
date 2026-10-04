"""Recognize a verified 0.7 runtime when installing the new independent CLI."""
import importlib.util,json,subprocess,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('installer',root/'provider_install.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
directory=Path(tempfile.mkdtemp(prefix='lckf-upgrade-'));old=json.loads(subprocess.check_output(['git','-C',str(root),'show','d5ddb2e:provider-release-lock.json'],text=True));new=json.loads((root/'provider-release-lock.json').read_text())
module.extract(root/'artifacts/local_character-windows-providers-0.7.0.zip',directory,old)
provider=directory/'kimodo-5679ff1';before={p.name:module.sha(p) for p in (provider/'bin').iterdir()};manifest=json.loads((provider/'build-manifest.json').read_text());assert 'keyframe_adapter' not in manifest
module.extract(root/'artifacts/local_character-windows-providers.zip',directory,new)
assert all(module.sha(provider/'bin'/name)==digest for name,digest in before.items())
assert module.sha(provider/'bin/kmd-keyframes.exe')==new['files']['kimodo-5679ff1/bin/kmd-keyframes.exe']
manifest=json.loads((provider/'build-manifest.json').read_text());assert manifest['keyframe_adapter']['version']==1
module.extract(root/'artifacts/local_character-windows-providers.zip',directory,new)
result=dict(passed=True,verified_0_7_upgrade=True,old_binaries_preserved=True,new_entrypoint_verified=True,idempotent=True)
(root/'artifacts/keyframe-upgrade-results.json').write_text(json.dumps(result,indent=2));print('KEYFRAME_PROVIDER_UPGRADE_PASSED',json.dumps(result),flush=True)
