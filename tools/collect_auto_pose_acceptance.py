# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect compact, checked receipts; exclude private avatar paths and geometry."""
import json
import os
from pathlib import Path

root=Path(__file__).resolve().parents[1]
temporary=Path(os.environ['LOCALAPPDATA'])/'Temp'
def read(path):return json.loads(path.read_text())
def unity_report(log_name):
    lines=(temporary/'rigmodo-auto-pose-development'/log_name).read_text().splitlines()
    line=next(line for line in lines if line.startswith('Private motion Unity workspace: '))
    return read(Path(line.partition(': ')[2])/'motion-results.json')

source=read(temporary/'rigmodo-auto-pose-development/solver-results.json')
extracted=read(temporary/'rigmodo-auto-pose-extracted-results/solver-results.json')
interaction=read(temporary/'rigmodo-auto-pose-interaction/interaction-results.json')
avatar=read(temporary/'rigmodo-auto-pose-avatar/avatar-results.json');avatar.pop('private_exports',None)
live=read(root/'docs/auto-pose-live-2026-10-05.json')
unity=unity_report('unity-corrected.log')
failed=unity_report('unity-final.log')
for case in failed['cases']:
    if case['error']:case['error']=case['error'].split('\r')[0]
regressions={name:read(temporary/path/'results.json') for name,path in (
    ('ui_and_landmarks','rigmodo-auto-pose-ui-regression'),('kimodo_controls','rigmodo-auto-pose-keyframe-regression'))}
for receipt in (source,extracted,interaction,avatar,live,*regressions.values()):assert receipt['passed']
assert source['version']==extracted['version']==live['version']=='0.10.0'
assert extracted['extracted_extension']
assert len(source['cases'])==36 and len(interaction['cases'])==9
assert all(case['passed'] for case in unity['cases'])
report=dict(passed=True,version='0.10.0',source=source,extracted=extracted,interaction=interaction,avatar=avatar,
    unity=unity,failed_unity_before_explicit_root_marker=failed,regressions=regressions,live=live,
    solver='hierarchical pin-first DLS on exact rest-offset FK; CPU, no AI weights',
    limits=['Standard Rigmodo humanoid only','Conservative swing/twist bounds, not full anatomical hinge limits',
            'No Auto Keying, NLA/control-rig editing, native gizmos, collision or balance',
            'Timings exclude viewport drawing; no 30/60 Hz guarantee'],
    private_geometry_and_paths_excluded=True)
(root/'docs/auto-pose-acceptance-2026-10-05.json').write_text(json.dumps(report,indent=2)+'\n')
print('AUTO_POSE_RECEIPTS_CHECKED',len(source['cases']),'solver cases;',len(interaction['cases']),'interaction cases; Unity both profiles passed')
