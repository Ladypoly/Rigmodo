import bpy,addon_utils,importlib,json,sys,tempfile,subprocess
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
fixture=Path(sys.argv[sys.argv.index('--')+2]);out=Path(tempfile.mkdtemp(prefix='rigmodo-library-lock-'));library=out/'Library';workers=[];logs=[]
for i in range(2):
    job=out/str(i);job.mkdir();(job/'request.json').write_text(json.dumps(dict(kind='import',root=str(library),files=[str(fixture)])))
    log=(job/'worker.log').open('w');logs.append(log)
    command=[bpy.app.binary_path,'--factory-startup','--background','--disable-autoexec','--python',str(Path(a.__file__).with_name('motion_library_worker.py')),'--',str(job)]
    workers.append((subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW),job))
for process,job in workers:
    assert process.wait(timeout=40)==0
    assert json.loads((job/'status.json').read_text())['status']=='complete',(job/'worker.log').read_text()
for log in logs:log.close()
entries=a.motion_store.catalog(library)['clips'];assert len(entries)==1
entry=entries[0];assert (library/'Assets'/(entry['id']+'.blend')).is_file()
assert not list((library/'Assets').glob('*.pending'))
with bpy.data.libraries.load(str(library/'Assets'/(entry['id']+'.blend')),link=False) as (available,loaded):assert len(available.actions)==1
report=dict(passed=True,concurrent_process_import=True,no_lost_or_duplicate_catalog_entries=True,atomic_asset_publishing=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('CONCURRENT_LIBRARY_PASS',json.dumps(report))
