"""Package companion, check distributable contents and retain compact evidence."""
import hashlib
import json
import os
from pathlib import Path
import tomllib
import zipfile
root=Path(__file__).resolve().parents[1];version=tomllib.loads((root/'blender_manifest.toml').read_text())['version']
artifacts=root/'artifacts';companion=artifacts/f'local_character-unity-companion-{version}.zip'
with zipfile.ZipFile(companion,'w',compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root/'unity').rglob('*')):
        if path.is_file() and path.suffix!='.meta':archive.write(path,path.relative_to(root/'unity').as_posix())
extension=artifacts/f'local_character-{version}.zip'
with zipfile.ZipFile(extension) as archive:
    names=set(archive.namelist())
    assert {'__init__.py','workflow.py','deformation_qa.py','provider_install.py','provider-release-lock.json','mia-runtime-lock.json','NOTICE','LICENSE','soma30.json'}<=names
    assert not any(n.startswith(('tests/','tools/','docs/','artifacts/','unity/','.git/')) for n in names)
    assert not any(Path(n).suffix.lower() in {'.blend','.fbx','.glb','.png','.pth','.gguf','.exe','.dll','.whl'} for n in names)
    for name in names:
        if name.endswith('.py'):compile(archive.read(name),name,'exec')
with zipfile.ZipFile(companion) as archive:
    assert {'LICENSE','README.md','Editor/LocalCharacter.Editor.asmdef','Runtime/LocalCharacter.Runtime.asmdef','Runtime/LocalCharacterTwists.cs'}<=set(archive.namelist())
temporary=Path(os.environ['LOCALAPPDATA'])/'Temp'
evidence={}
sources={'fresh_install':'local-character-install-veal6fz8/results.json','fresh_inference':'local-character-fresh-inference/results.json',
    'corpus':'local-character-corpus-final/results.json','controls':'local-character-controls-final/results.json',
    'rigid':'local-character-rigid-release/results.json','geometry':'local-character-geometry-release/results.json',
    'contacts':'local-character-contact-release/results.json','unity_motion':'local-character-motion-unity-jxyi7p_v/motion-results.json',
    'unity_jump':'local-character-motion-unity-f0xtiqv0/motion-results.json','unity_transition':'local-character-motion-unity-jxyi7p_v/transition-results.json',
    'baseline':'local-character-acceptance-ll8iyr05/summary.json','rpm_visual_failure':'local-character-rpm-release/results.json',
    'unity_failed_rpm_structural_parity':'local-character-motion-unity-mr_jbcl_/motion-results.json',
    'deformation_gate':'local-character-deformation-release/results.json','hazmat_release':'local-character-hazmat-release/results.json',
    'extracted_release':'local-character-archive-release/results.json',
    'unity_hazmat':'local-character-motion-unity-vdo054if/motion-results.json',
    'imported_camera_recovery':'local-character-camera-recovery/results.json','unity_camera_recovery':'local-character-motion-unity-vzas0bzq/motion-results.json'}
for name,path in sources.items():
    file=temporary/path
    if file.is_file():evidence[name]=json.loads(file.read_text())
for key in ('deformation_gate','hazmat_release','imported_camera_recovery','extracted_release'):assert evidence[key]['passed']
assert evidence['hazmat_release']['visual_review_passed']
assert not evidence['rpm_visual_failure']['passed'] and evidence['rpm_visual_failure']['structural_checks_passed']
profile=json.loads((temporary/'local-character-one-click/resource-profile.json').read_text());profile.pop('samples',None);evidence['resource_profile']=profile
evidence['live_reload']=json.loads((root/'docs/live-reload-2026-10-03.json').read_text())
evidence['live_companion']=json.loads((root/'docs/live-companion-2026-10-03.json').read_text())
assert evidence['live_companion']['compilation_passed'] and evidence['live_companion']['open_scene_state_preserved']
baseline=json.loads((root/'docs/live-project-baseline.json').read_text())
evidence['live_unity_original_files_preserved']=all(hashlib.sha256((Path(baseline['project'])/name).read_bytes()).hexdigest()==value for name,value in baseline['hashes'].items())
assert evidence['live_unity_original_files_preserved']
checksums={}
for file in (extension,companion,artifacts/'local_character-windows-providers.zip'):
    with file.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    checksums[file.name]=dict(bytes=file.stat().st_size,sha256=digest)
record=dict(version=version,extension_zip_validated=True,source_modules_compile=True,private_assets_excluded=True,
    artifacts=checksums,evidence=evidence,hardware_limit='RTX 4090 24 GB tested; sampled global device usage is not a physical 16 GB proof')
(root/'docs/release-verification-2026-10-03.json').write_text(json.dumps(record,indent=2)+'\n')
(artifacts/f'local_character-{version}-checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
print('RELEASE_PACKAGED',json.dumps(checksums),flush=True)
