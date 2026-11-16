import importlib.util,sys,tempfile,json
from pathlib import Path
from types import SimpleNamespace,ModuleType
p=Path(__file__).resolve().parents[1]/'capture_progress.py';spec=importlib.util.spec_from_file_location('capture_progress_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
folder=Path(tempfile.mkdtemp(prefix='rigmodo-progress-test-'));progress=m.Progress(folder);progress('Loading model');assert 'total' not in m.read(folder)
progress('Tracking person',0,600);progress('Tracking person',600,600);assert m.read(folder)['completed']==600 and m.read(folder)['total']==600
(folder/'progress.json').write_text('{incomplete');assert m.read(folder)=={}
(folder/'progress.json').write_text(json.dumps(dict(phase='Invalid',completed=10,total=2)));assert 'completed' not in m.read(folder)
events=[]
def notify(phase,done=None,total=None,**kw):events.append((phase,done,total))
native=ModuleType('gem.common.pose2d.native77');native.decode_native77_heatmaps=lambda n:[0]*n
for name in ('gem','gem.common','gem.common.pose2d'):sys.modules[name]=ModuleType(name)
sys.modules['gem.common.pose2d'].native77=native;sys.modules['gem.common.pose2d.native77']=native
class Detector:
 def detect(self,frame):return frame
class Observations:
 release_id='fixture'
 def predict(self,frames,boxes):return native.decode_native77_heatmaps(len(frames))
class Encoder:
 def encode(self,batch):return SimpleNamespace(pose_tokens=list(batch))
def track(frames,detector,**kw):return [detector.detect(f) for f in frames]
def features(frames,boxes,intrinsics,model,**kw):return model.encode(frames).pose_tokens
module=SimpleNamespace(detect_track=track,load_native77_detector=lambda *a,**kw:Observations(),extract_body_features=features,run_motion=lambda *a,**kw:'motion')
original=dict(vars(module))
with m.instrument_gem(module,notify):
 assert module.detect_track([1,2,3],Detector())==[1,2,3]
 assert len(module.load_native77_detector().predict([1,2,3],None))==3
 assert module.extract_body_features([1,2,3],None,None,Encoder())==[1,2,3]
 assert module.run_motion(None,None)=='motion'
assert vars(module)==original
for phase in ('Tracking person','Estimating 2D joints','Extracting body features'):assert (phase,3,3) in events
assert ('Solving temporal motion',1,1) in events
report=dict(passed=True,real_counter_boundaries=True,no_estimate_during_loading=True,malformed_progress_safe=True,instrumentation_restores_provider=True)
Path(sys.argv[1]).write_text(json.dumps(report,indent=2),encoding='utf-8');print('PROGRESS_TEST_PASS',report)
