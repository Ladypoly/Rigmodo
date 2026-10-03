"""Fresh native cache, checkpoint integrity, isolated runtime and descendant cancellation."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import psutil

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lc_process_tree',root/'process_tree.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
output=Path(tempfile.mkdtemp(prefix='local-character-install-')).resolve();print('Private installation workspace:',output,flush=True)
cache=output/'providers';seed=output/'verified-seed';lock=json.loads((root/'provider-release-lock.json').read_text())
original=Path(os.environ['LOCALAPPDATA'])/'LocalCharacter/providers'
# Network transport is exercised on the tokenizer; larger already-verified
# checkpoints are seeded without duplicating eleven gigabytes on disk.
for entry in lock['models']:
    if entry['path'].endswith('/tokenizer.gguf'):continue
    target=seed/entry['path'];target.parent.mkdir(parents=True,exist_ok=True);os.link(original/entry['path'],target)
log=(output/'installer.log').open('wb')
process=subprocess.Popen([sys.executable,'-I',str(root/'provider_install.py'),'--archive',str(root/'artifacts/local_character-windows-providers.zip'),
    '--cache',str(cache),'--seed-cache',str(seed)],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
job=module.WindowsJob(process)
try:code=process.wait()
finally:job.close();log.close()
if code:print((output/'installer.log').read_text(),flush=True)
assert code==0,'Fresh installer failed'
assert all((cache/name).is_file() for name in lock['files'])
runtime=json.loads((cache/'mia-original/runtime-manifest.json').read_text());assert runtime['isolated']
assert {p['name'].lower():p['version'] for p in runtime['packages']}['torch']=='2.7.1+cu128'
# An owned parent and its child must both die when the UI cancels the job.
marker=output/'children.json';worker=output/'owned_children.py'
worker.write_text('import subprocess,sys,time,json\nfrom pathlib import Path\np=subprocess.Popen([sys.executable,"-I","-c","import time; time.sleep(90)"],creationflags=subprocess.CREATE_NO_WINDOW)\nPath(sys.argv[1]).write_text(json.dumps({"child":p.pid}))\ntime.sleep(90)\n')
process=subprocess.Popen([sys.executable,'-I',str(worker),str(marker)],creationflags=subprocess.CREATE_NO_WINDOW)
job=module.WindowsJob(process)
try:
    deadline=time.monotonic()+10
    while not marker.exists() and time.monotonic()<deadline:time.sleep(.05)
    assert marker.exists();child=json.loads(marker.read_text())['child'];assert psutil.pid_exists(child)
finally:job.close()
process.wait(timeout=3)
deadline=time.monotonic()+3
while psutil.pid_exists(child) and time.monotonic()<deadline:time.sleep(.05)
assert not psutil.pid_exists(child),'Cancelled installer left a child process'
result=dict(passed=True,cache=str(cache),native_files=len(lock['files']),models=len(lock['models']),
            tokenizer_downloaded=True,larger_checkpoints_seeded=True,fresh_isolated_runtime=True,owned_descendants_cancelled=True)
(output/'results.json').write_text(json.dumps(result,indent=2));print('INSTALL_ACCEPTANCE',json.dumps(result),flush=True)
