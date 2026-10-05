# SPDX-License-Identifier: GPL-3.0-or-later
"""Collect native Action guidance checks separately from older snapshot evidence."""
import json, os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
temporary=Path(os.environ['LOCALAPPDATA'])/'Temp'
def read(path):return json.loads(path.read_text())
source=read(temporary/'rigmodo-timeline-keyposes-release/results.json')
extracted=read(temporary/'rigmodo-timeline-keyposes-extracted-results/results.json')
ui=read(temporary/'rigmodo-timeline-keyposes-ui-final/results.json')
image_gui=read(temporary/'rigmodo-timeline-image-key-interaction/results.json')
live=read(root/'docs/timeline-keyposes-live-2026-10-05.json')
assert all(r['passed'] for r in (source,extracted,ui,image_gui,live))
assert all(r['version']=='0.12.0' for r in (source,extracted,image_gui,live))
assert extracted['extracted_extension'] and not source['extracted_extension']
assert source['cases'][0]['actual_kimodo_inference']
assert source['cases'][2]['avatar_vertices']==6598
assert max(r['max_anchor_matrix_error'] for r in source['cases']+extracted['cases'])<1e-5
assert ui['keyposes_use_one_toggle'] and ui['no_capture_recall_clear_buttons']
assert 'kimodo_timeline_keyframes' in image_gui['cases'] and image_gui['sam_neural_inference_tested']
assert live['scene_preserved']
record=dict(passed=True,version='0.12.0',source=source,extracted=extracted,ui=ui,image_gui=image_gui,live=live,
            workflow='Ordinary active-Action pose keys, one Use Key Poses toggle; clip starts at Timeline Start',
            inference='One real conditioned Kimodo run; retarget-only cases use cached motion. Real SAM image-drop/keyframe GUI also passes',
            unity='Exporter and generated-Action representation unchanged; prior Unity checks retained as a historical baseline')
(root/'docs/timeline-keyposes-acceptance-2026-10-05.json').write_text(json.dumps(record,indent=2)+'\n')
print('TIMELINE_KEYPOSES_EVIDENCE_COLLECTED')
