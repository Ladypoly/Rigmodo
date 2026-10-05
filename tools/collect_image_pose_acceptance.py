# SPDX-License-Identifier: GPL-3.0-or-later
"""Record integration validation without treating MHR fixtures as neural inference."""
import json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];temporary=Path(os.environ['LOCALAPPDATA'])/'Temp'
def read(path):return json.loads(path.read_text())
source=read(temporary/'rigmodo-image-pose-acceptance/results.json')
extracted=read(temporary/'rigmodo-image-pose-extracted-results/results.json')
gui=read(temporary/'rigmodo-image-pose-interaction/results.json')
ui=read(temporary/'rigmodo-image-pose-ui-regression/results.json')
live=read(root/'docs/image-pose-live-2026-10-05.json')
regression=read(temporary/'rigmodo-image-pose-regression/solver-results.json')
assert all(r['passed'] for r in (source,extracted,gui,ui,live,regression))
assert not (temporary/'rigmodo-image-pose-interaction/error.txt').exists()
assert extracted['extracted_extension'] and source['avatar']['vertices']==6598
log=(temporary/'rigmodo-sam-research/runtime-check.log').read_text()
assert 'SAM imports passed 2.7.1+cu128 NVIDIA GeForce RTX 4090' in log
assert 'Pinned DINO backbone instantiated 840633600' in log
record=dict(passed=True,version='0.11.0',sam_neural_inference_tested=False,
    limitation='Approved gated SAM checkpoints unavailable; image prediction, accuracy and VRAM/time not yet measured',
    source=source,extracted=extracted,gui=gui,ui=ui,live=live,
    auto_pose_regression=dict(passed=regression['passed'],cases=len(regression['cases'])),
    runtime=dict(passed=True,isolated_python='3.11',torch='2.7.1+cu128',cuda_gpu='RTX 4090',
                 upstream_sam_imports=True,pinned_local_dino_constructed=True,dino_parameters=840633600),
    native_handler_adapter='Only stock reference-image handler yields in selected Rigmodo Motion sidebar; original restored on unregister',
    fixture='Public Apache-2.0 MHR v1.0.1, authored pose parameters; no image estimation',
    checkpoints='Not bundled; Meta SAM license and approved Hugging Face access required')
(root/'docs/image-pose-acceptance-2026-10-05.json').write_text(json.dumps(record,indent=2)+'\n')
print('IMAGE_POSE_EVIDENCE_COLLECTED',record['version'])
