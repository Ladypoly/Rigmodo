"""Real native skin prediction from shared weights, without changing source paint."""
import bpy,importlib.util,json,sys,time
from pathlib import Path
r=Path(__file__).resolve().parents[1];args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('rigmodo_skin_storage',r/'__init__.py',submodule_search_locations=[str(r)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register()
bpy.ops.wm.open_mainfile(filepath=args[1]);rig=bpy.context.active_object
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.parent==rig]
before=a.skinning._digest(rig,meshes);folder=a.skinning.prepare(bpy.context,rig,meshes,parent=out,beams=1)
# Intentionally pass the legacy location to test the common native entry point.
a.skinning.start(folder,a.skinning.provider_cache()/'bin/skintokens-cli.exe',a.skinning.provider_cache()/'models/F16')
while True:
 status=a.skinning.poll(folder)
 if status['status']!='running':break
 time.sleep(.3)
assert status['status']=='complete',(status,(folder/'worker.log').read_text(errors='replace')[-1500:])
assert a.skinning._digest(rig,meshes)==before
report=dict(passed=True,actual_native_skinning=True,shared_models=True,source_paint_preserved=True)
(out/'results.json').write_text(json.dumps(report,indent=2));print('SKINNING_STORAGE_ACCEPTANCE',json.dumps(report),flush=True)
