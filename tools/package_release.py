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
    if version in {'0.6.0','0.7.0','0.8.0','0.9.0'}:assert {'configuration.py','landmarks.py','ui.py'}<=names
    if version in {'0.7.0','0.8.0','0.9.0'}:assert {'hands.py','hand_geometry.py'}<=names
    if version in {'0.8.0','0.9.0'}:assert 'motion_keyframes.py' in names
    if version=='0.9.0':assert 'character_result.py' in names
    assert not any(n.startswith(('tests/','tools/','native/','docs/','artifacts/','unity/','.git/')) for n in names)
    assert not any(Path(n).suffix.lower() in {'.blend','.fbx','.glb','.png','.pth','.gguf','.exe','.dll','.whl'} for n in names)
    for name in names:
        if name.endswith('.py'):compile(archive.read(name),name,'exec')
        if name.endswith('.py') or name=='blender_manifest.toml':assert archive.read(name)==(root/name).read_bytes(),name
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
if version=='0.6.0':
    sources.update(baseline='local-character-acceptance-3bp3b080/summary.json',
        ui_and_landmarks='local-character-ui-release/results.json',automatic_skinning='local-character-auto-skin-ui/results.json',
        extracted_release='local-character-archive-ui-release/results.json')
if version=='0.7.0':
    sources.update(baseline='local-character-acceptance-3bp3b080/summary.json',
        ui_and_landmarks='local-character-hand-ui/results.json',
        hand_geometry='local-character-hand-development/geometry-results.json',
        hand_placement='local-character-hand-acceptance/results.json',
        ordinary_placement='local-character-hand-shane/results.json',
        hand_skinning='local-character-hand-skin/results.json',
        extracted_release='local-character-hand-archive-final-release/results.json',
        hand_unity='local-character-ai-unity-c1iyvx3t/summary.json')
if version=='0.8.0':
    archive_paths=json.loads((artifacts/'keyframe-archive-test-paths.json').read_text())
    sources.update(keyframe_inference='local-character-keyframes-final/results.json',
        keyframe_avatar='local-character-keyframes-avatar/results.json',keyframe_controls='local-character-keyframes-controls-final/results.json',
        ui_and_landmarks='local-character-keyframes-ui/results.json',hand_geometry='local-character-keyframes-geometry-regression',
        keyframe_final_ui='local-character-keyframes-final-ui/results.json',
        keyframe_unity='local-character-motion-unity-3ts9jn9f/motion-results.json',
        motion_regression_unity='local-character-motion-unity-qfsjikp7/motion-results.json',
        avatar_keyframe_unity='local-character-motion-unity-lnhslna_/motion-results.json',
        extracted_keyframe_release=str(Path(archive_paths['output'])/'results.json'))
if version=='0.9.0':
    sources.update(rigmodo_results='rigmodo-results-acceptance/results.json',rigmodo_actual_skin='rigmodo-auto-skin-acceptance/results.json',
        ui_and_landmarks='rigmodo-ui-regression/results.json',keyframe_controls='rigmodo-keyframe-regression/results.json',
        rigmodo_export='rigmodo-export-acceptance/results.json',rigmodo_unity='local-character-motion-unity-ifbo4iqj/motion-results.json',
        rigmodo_extracted='rigmodo-extracted-acceptance/results.json')
for name,path in sources.items():
    file=temporary/path
    if file.is_file():evidence[name]=json.loads(file.read_text())
for key in ('deformation_gate','hazmat_release','imported_camera_recovery','extracted_release'):assert evidence[key]['passed']
assert evidence['hazmat_release']['visual_review_passed']
assert not evidence['rpm_visual_failure']['passed'] and evidence['rpm_visual_failure']['structural_checks_passed']
profile=json.loads((temporary/'local-character-one-click/resource-profile.json').read_text());profile.pop('samples',None);evidence['resource_profile']=profile
evidence['live_reload']=json.loads((root/'docs/live-reload-2026-10-03.json').read_text())
if version=='0.6.0':
    for key in ('ui_and_landmarks','automatic_skinning'):assert evidence[key]['passed']
    assert evidence['automatic_skinning']['version']==version
    evidence['live_reload']=json.loads((root/'docs/ui-live-reload-2026-10-04.json').read_text())
    evidence['landmark_editor']=json.loads((root/'docs/ui-editor-acceptance-2026-10-04.json').read_text())
    assert evidence['live_reload']['version']==version and evidence['landmark_editor']['passed']
if version=='0.7.0':
    for key in ('ui_and_landmarks','hand_geometry','hand_placement','ordinary_placement','hand_skinning','extracted_release','hand_unity'):assert evidence[key]['passed']
    assert evidence['extracted_release']['version']==version
    for key,file in (('live_reload','hand-live-reload'),('hand_editor','hand-editor-acceptance'),('live_hand_copy','hand-live-copy')):
        evidence[key]=json.loads((root/f'docs/{file}-2026-10-04.json').read_text())
        assert evidence[key]['passed'] and evidence[key]['version']==version
if version=='0.8.0':
    for key in ('keyframe_inference','keyframe_avatar','keyframe_controls','keyframe_final_ui','ui_and_landmarks','extracted_keyframe_release'):assert evidence[key]['passed']
    assert evidence['extracted_keyframe_release']['version']==version
    for key in ('keyframe_unity','avatar_keyframe_unity','motion_regression_unity'):
        assert all(case['passed'] for case in evidence[key]['cases'])
    evidence['provider_upgrade']=json.loads((artifacts/'keyframe-upgrade-results.json').read_text());assert evidence['provider_upgrade']['passed']
    evidence['live_reload']=json.loads((root/'docs/keyframes-live-reload-2026-10-04.json').read_text())
    assert evidence['live_reload']['passed'] and evidence['live_reload']['version']==version
if version=='0.9.0':
    for key in ('rigmodo_results','rigmodo_actual_skin','ui_and_landmarks','keyframe_controls','rigmodo_export','rigmodo_extracted'):assert evidence[key]['passed']
    assert evidence['rigmodo_actual_skin']['version']==version and evidence['rigmodo_actual_skin']['actual_skin_inference']
    assert evidence['rigmodo_extracted']['extracted_extension']
    assert all(case['passed'] for case in evidence['rigmodo_unity']['cases'])
    evidence['live_reload']=json.loads((root/'docs/rigmodo-live-2026-10-05.json').read_text())
    assert evidence['live_reload']['passed'] and evidence['live_reload']['version']==version
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
release_date='2026-10-05' if version=='0.9.0' else '2026-10-04' if version in {'0.6.0','0.7.0','0.8.0'} else '2026-10-03'
release_name=f'release-verification-{version}-{release_date}' if version in {'0.7.0','0.8.0','0.9.0'} else f'release-verification-{release_date}'
(root/f'docs/{release_name}.json').write_text(json.dumps(record,indent=2)+'\n')
(artifacts/f'local_character-{version}-checksums.json').write_text(json.dumps(checksums,indent=2)+'\n')
print('RELEASE_PACKAGED',json.dumps(checksums),flush=True)
