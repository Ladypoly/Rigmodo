"""Ownership-aware idle cleanup and failed-submission recovery, no GPU required."""
import importlib.util,json,tempfile,sys,urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('comfy_memory_test',root/'comfy_video.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Fake(m.Client):
 def __init__(self,mode='own'):super().__init__('http://127.0.0.1:8288');self.mode=mode;self.calls=[];self.queue_count=0
 def request(self,path,data=None,timeout=15):
  self.calls.append((path,data))
  if path=='/queue':
   self.queue_count+=1;busy=self.mode=='busy' or self.mode=='race' and self.queue_count>1
   return dict(queue_running=[[1,'own',{},dict(client_id='rigmodo')]] if busy else [],queue_pending=[])
  if path.startswith('/history'):
   key='other' if self.mode=='other' else 'own';return {key:dict(prompt=[1,key,{},dict(client_id='someone' if self.mode=='wrong_client' else 'rigmodo')],status=dict(completed=True),outputs={})}
  return {}
for mode,expected in [('own',True),('busy',False),('race',False),('other',False),('wrong_client',False)]:
 c=Fake(mode);assert c.release_models('own','rigmodo')['released']==expected;assert any(p=='/free' for p,d in c.calls)==expected
c=Fake();assert c.find_prompt(dict(client_id='rigmodo'))=='own';assert c.find_prompt(dict(client_id='unrelated')) is None
real=m.Client;c=Fake();m.Client=lambda url:c
folder=Path(tempfile.mkdtemp(prefix='rigmodo-memory-test-'));(folder/'bridge').mkdir();(folder/'bridge'/'comfy.json').write_text(json.dumps(dict(url=c.url,client_id='rigmodo')))
assert m.release_job(folder)[0]['released'];count=len(c.calls);assert m.release_job(folder)[0]['released'];assert not any(p=='/free' for p,d in c.calls[count:])
m.Client=real
class Failed(m.Client):
 def validate(self,graph):pass
 def request(self,path,data=None,timeout=15):
  if path=='/queue':return dict(queue_running=[],queue_pending=[])
  if path=='/prompt':raise ValueError('Transport failed after accepting prompt')
  return {}
called=[];old=m.release_job;m.release_job=lambda p:called.append(p)
try:Failed('http://127.0.0.1:8288').run({},folder,lambda p:None,'unique-client')
except ValueError:pass
assert called==[folder] and json.loads((folder/'comfy.json').read_text())['client_id']=='unique-client'
m.release_job=old
report=dict(passed=True,idle_owned_release=True,busy_queue_preserved=True,submission_race_rechecked=True,other_client_cache_preserved=True,bridge_cleanup_idempotent=True,pending_submission_identifiable=True,cleanup_on_exception=True)
Path(sys.argv[1]).write_text(json.dumps(report,indent=2),encoding='utf-8');print('COMFY_MEMORY_PASS',report)
