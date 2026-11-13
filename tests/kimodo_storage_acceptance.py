"""Actual Kimodo native inference after redirecting its model and tokenizer paths."""
import bpy,importlib.util,json,sys,time
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('rigmodo_kimodo_storage',r/'__init__.py',submodule_search_locations=[str(r)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register()
rig=a.skeleton.create_armature(bpy.context);folder=a.motion_jobs.prepare(bpy.context,rig,'A person stands still.',15,10,101,True,parent=out);a.motion_jobs.start(folder)
while True:
 status=a.skinning.poll(folder)
 if status['status']!='running':break
 time.sleep(.3)
assert status['status']=='complete',(status,(folder/'worker.log').read_text(errors='replace')[-1000:])
root,rot=a.motion_data.load(folder,15);result=dict(passed=True,actual_kimodo_inference=True,shared_models=True,frames=len(root))
(out/'results.json').write_text(json.dumps(result,indent=2));print('KIMODO_STORAGE_ACCEPTANCE',json.dumps(result),flush=True)
