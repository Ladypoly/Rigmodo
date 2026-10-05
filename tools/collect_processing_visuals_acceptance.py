"""Combine private receipts; keep actual model runs separate from UI fixtures."""
import json,os
from pathlib import Path
root=Path(__file__).resolve().parents[1];temp=Path(os.environ['LOCALAPPDATA'])/'Temp'
paths={'geometry':'rigmodo-processing-acceptance-final/results.json',
       'ui':'rigmodo-processing-ui-final/results.json',
       'viewport':'rigmodo-processing-preview-final/results.json',
       'actual_skin':'rigmodo-processing-interaction-final/results.json',
       'image_interaction':'rigmodo-processing-image-interaction-final/results.json'}
record={key:json.loads((temp/path).read_text()) for key,path in paths.items()}
record['live']=json.loads((root/'docs/processing-visuals-live-2026-10-05.json').read_text())
assert all(check['passed'] for check in record.values())
assert record['actual_skin']['actual_skin_inference'] and 'actual_workflow_cancel_button_preserves_character' in record['actual_skin']['cases']
assert record['viewport']['real_viewport_gpu_draws']>0 and not record['viewport']['actual_skin_inference']
assert record['image_interaction']['simulated_worker'] and 'shared_cancel_preserves_pose' in record['image_interaction']['cases']
assert record['ui']['shared_progress_has_one_cancel'] and record['ui']['effects_settings_only_in_preferences']
record.update(passed=True,version=record['live']['version'],actual_skin_inference_tested=True,
    final_viewport_preview_simulated=True,image_worker_simulated=True,
    unchanged_model_and_unity_baseline_version='0.12.1',real_skin_before_final_visual_polish=True)
(root/'docs/processing-visuals-acceptance-2026-10-05.json').write_text(json.dumps(record,indent=2)+'\n')
print('PROCESSING_EVIDENCE_COLLECTED',record['version'])
