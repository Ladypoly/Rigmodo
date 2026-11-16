# SPDX-License-Identifier: GPL-3.0-or-later
"""Data-only checks; run with Python, no GPU or shared server required."""
import sys,tempfile,json,math
from pathlib import Path
import numpy as np
repo=Path(sys.argv[1]);sys.path.insert(0,str(repo))
from comfy_video import Client,bind,h3_graph,h3_frames
from video_cycles import find_cycle
from video_setup import ready
assert h3_frames(3)==124 and h3_frames(10)==243 and h3_frames(15)==362
assert all((h3_frames(s)-5)%17==0 for s in (1,3,5,8,10,15,30))
request=dict(id='test',duration=3,prompt='Walk.',seed=1,loop=True,model='model',clip='clip',vae='vae',audio_vae='audio')
graph=h3_graph(request,'first.png');assert graph['condition']['inputs']['first_frame']==graph['condition']['inputs']['last_frame']
bridge=h3_graph(dict(request,loop=False),'last.png','first.png');assert bridge['condition']['inputs']['last_frame']==['last_image',0]
assert bind(graph,dict(prompt='condition.prompt'),dict(prompt='Dance'))['condition']['inputs']['prompt']=='Dance'
try:bind(graph,dict(prompt='missing.input'),dict(prompt='Dance'));raise AssertionError('Invalid binding accepted')
except ValueError:pass
try:Client('http://name:secret@localhost:8288');raise AssertionError('Credentials accepted in URL')
except ValueError:pass
class QueueClient(Client):
    def __init__(self):super().__init__('http://localhost:8288');self.calls=[]
    def request(self,path,data=None,timeout=15):
        self.calls.append((path,data))
        if path=='/queue' and data is None:return dict(queue_pending=[[0,'owned',{},{}],[1,'someone-else',{},{}]],queue_running=[[2,'running',{},{}]])
        return {}
client=QueueClient();assert client.cancel('owned')=='Removed queued Rigmodo job';assert client.calls[-1]==('/queue',{'delete':['owned']})
client.cancel('running');assert all(path!='/interrupt' for path,data in client.calls)
assert not ready('missing.exe','missing-models')
# A synthetic repeating motion should select a true repeated period.
times=np.arange(91,dtype=np.float32)/30;names=np.asarray(['Hips','Head','LeftFoot','RightFoot']);rest=np.repeat(np.eye(4,dtype=np.float32)[None],4,axis=0);rest[1,2,3]=1;rest[2,0,3]=.2;rest[3,0,3]=-.2
poses=np.repeat(rest[None],len(times),axis=0)
poses[:,2,1,3]=np.sin(times*2*np.pi)*.3;poses[:,3,1,3]=-np.sin(times*2*np.pi)*.3
data=dict(names=names,rest=rest,poses=poses,times=times,contact_probabilities=np.ones((len(times),2),dtype=np.float32),source_times=times+10)
cycle,metrics=find_cycle(data);assert abs((metrics['end_seconds']-metrics['start_seconds'])-round(metrics['end_seconds']-metrics['start_seconds']))<.04 and metrics['pose_error_fraction']<.001
assert cycle['times'][0]==0 and len(cycle['contact_probabilities'])==len(cycle['times']) and cycle['source_times'][0]>=10
report=dict(passed=True,h3_constraints=True,loop_and_bridge_references=True,workflow_bindings_validated=True,owned_queue_cancel_only=True,no_global_interrupt=True,credential_url_rejected=True,pose_aware_cycle_selection=True)
Path(sys.argv[2]).write_text(json.dumps(report,indent=2));print('COMFY_CYCLE_UNIT_PASS',report)
