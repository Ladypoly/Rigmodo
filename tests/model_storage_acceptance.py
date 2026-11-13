"""Small on-disk migration checks; no installed models or user configuration touched."""
import importlib.util,json,sys,tempfile
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'model_storage.py';spec=importlib.util.spec_from_file_location('storage_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
base=Path(tempfile.mkdtemp(prefix='model-storage-test-',dir=out));providers=base/'providers';source=providers/'mia-original/models/joints.pth';source.parent.mkdir(parents=True);source.write_bytes(b'known-model-data')
shared=base/'models';config=base/'config.json';report=m.migrate(shared,providers,config)
target=shared/'mia/joints.pth';assert target.read_bytes()==b'known-model-data' and not source.exists()
assert m.resolve(source,providers,shared)==target and json.loads(config.read_text())['root']==str(shared)
again=m.migrate(shared,providers,config);assert len(again['models'])==1 and target.exists()
other=base/'other-models';m.migrate(other,providers,config);assert (other/'mia/joints.pth').is_file() and not target.exists()
conflict=base/'conflict';conflict.mkdir();source.write_bytes(b'original');(conflict/'mia').mkdir();(conflict/'mia/joints.pth').write_bytes(b'different')
try:m.migrate(conflict,providers,base/'conflict.json');raise AssertionError('Conflicting target accepted')
except ValueError:pass
assert source.read_bytes()==b'original' and not (base/'conflict.json').exists()
try:m.migrate(providers/'models',providers,base/'bad.json');raise AssertionError('Nested model cache accepted')
except ValueError:pass
result=dict(passed=True,verified_content=True,managed_original_removed_only_after_switch=True,idempotent=True,subsequent_root_move=True,conflicts_preserve_source=True,nested_provider_target_rejected=True)
(out/'results.json').write_text(json.dumps(result,indent=2));print('MODEL_STORAGE_ACCEPTANCE',json.dumps(result))
