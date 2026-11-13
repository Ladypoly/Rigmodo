"""Collect private inference/UI receipts without bundling meshes or checkpoints."""
import json,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1];base=Path(sys.argv[1])
paths={'giraffe':'acceptance-final/results.json','humanoid_regression':'humanoid-ui-final/results.json',
       'gui':'gui-results.json','fbx_roundtrip':'fbx-roundtrip-results.json','scorpion_live':'scorpion-live-results.json'}
evidence={name:json.loads((base/path).read_text()) for name,path in paths.items()}
assert all(check['passed'] for check in evidence.values())
outputs=list((base/'acceptance-final').glob('joints-*/output.json'));assert len(outputs)==1
model=json.loads(outputs[0].read_text())
assert model['model_coordinate_space']=='blender_z_up' and model['samples']==65536 and model['beams']==15
assert evidence['giraffe']['actual_unirig_inference'] and evidence['giraffe']['actual_skin_inference']
assert evidence['scorpion_live']['original_preserved'] and evidence['scorpion_live']['tail_requires_manual_review']
assert evidence['gui']['real_worker_cancelled'] and evidence['humanoid_regression']['fresh_actual_mia_fixture']
evidence.update(passed=True,version='0.14.0',model_input_space='blender_z_up',samples=65536,beams=15,
    fixture=dict(url='https://github.com/VAST-AI-Research/UniRig/blob/6793c6640ff01c8fb389f3993434124bb43d2933/examples/giraffe.glb',sha256='9a947cae00b169345802c08885c1e54313c6ce93c885bacf8e37e8a1f18f9e3b'),
    baseline_version='0.13.0',unity_editor_import_tested=False,creature_animation_implemented=False)
(root/'docs/creature-acceptance-2026-11-13.json').write_text(json.dumps(evidence,indent=2)+'\n')
print('CREATURE_EVIDENCE_COLLECTED',evidence['version'])
