# SPDX-License-Identifier: GPL-3.0-or-later
"""Measured provider progress without modifying the pinned capture checkout."""
import json,math,os,time
from pathlib import Path
from contextlib import contextmanager,ExitStack
from unittest.mock import patch

LABELS={'Normalizing the input clip to 30fps':'Reading video at 30 fps','Detecting and tracking the primary person':'Loading person detector','Extracting native77 2D observations':'Loading 2D joint model','Extracting frozen body Pose features':'Loading body model','Predicting native temporal Motion':'Loading temporal motion model','Reconstructing the captured skeleton':'Building 3D motion'}

def read(folder):
    path=Path(folder)/'progress.json'
    try:
        if path.stat().st_size>16384:return {}
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('phase'),str):return {}
        result={'phase':data['phase'][:240]}
        for key in ('completed','total','eta_seconds','stage_elapsed','updated_at'):
            value=data.get(key)
            if isinstance(value,(int,float)) and math.isfinite(value) and value>=0:result[key]=value
        result['unit']=str(data.get('unit','frames'))[:24]
        if not result.get('total') or result.get('completed',0)>result['total']:
            for key in ('completed','total','eta_seconds'):result.pop(key,None)
        return result
    except (OSError,ValueError,TypeError):return {}


def write(folder,data):
    # Windows readers can briefly deny replacement; progress must never abort inference.
    temporary=Path(folder)/('progress.'+str(os.getpid())+'.pending')
    try:
        temporary.write_text(json.dumps(data),encoding='utf-8')
        for attempt in range(5):
            try:os.replace(temporary,Path(folder)/'progress.json');return True
            except PermissionError:time.sleep(.01*(attempt+1))
        return False
    except OSError:return False
    finally:
        try:temporary.unlink(missing_ok=True)
        except OSError:pass


class Progress:
    def __init__(self,folder):
        self.folder=Path(folder);self.phase='';self.started=time.monotonic();self.written=0.;self.timings={}
    def __call__(self,phase,completed=None,total=None,unit='frames'):
        phase=LABELS.get(phase,phase);now=time.monotonic();changed=phase!=self.phase
        if changed:
            if self.phase:self.timings[self.phase]=self.timings.get(self.phase,0)+now-self.started
            self.phase=phase;self.started=now;print('CAPTURE_STAGE',phase,flush=True)
        if not changed and now-self.written<.4 and completed!=total:return
        self.written=now;elapsed=now-self.started
        data=dict(phase=phase,updated_at=time.time(),stage_elapsed=elapsed)
        if total is not None and total>0 and completed is not None:
            if not 0<=completed<=total:raise ValueError('Capture progress exceeds its stage total')
            data.update(completed=int(completed),total=int(total),unit=unit)
            if completed>=3 and elapsed>=1:data['eta_seconds']=elapsed/completed*(total-completed)
        write(self.folder,data)
    def finish(self):
        if self.phase:self.timings[self.phase]=self.timings.get(self.phase,0)+time.monotonic()-self.started
        return {name:round(seconds,3) for name,seconds in self.timings.items()}


@contextmanager
def instrument_gem(module,progress):
    """Count completed frames/batches at the existing public inference boundaries."""
    track=module.detect_track;load=module.load_native77_detector;features=module.extract_body_features;motion=module.run_motion
    def tracked(frames,detector,**kwargs):
        total=len(frames);done=0;progress('Tracking person',0,total)
        class Detector:
            def detect(self,*args,**kw):
                nonlocal done
                result=detector.detect(*args,**kw);done+=1;progress('Tracking person',done,total);return result
        return track(frames,Detector(),**kwargs)
    def observed(*args,**kwargs):
        detector=load(*args,**kwargs)
        class Observations:
            release_id=detector.release_id
            def predict(self,frames,boxes):
                from gem.common.pose2d import native77
                decode=native77.decode_native77_heatmaps;total=len(frames);done=0;progress('Estimating 2D joints',0,total)
                def decoded(*args,**kw):
                    nonlocal done
                    result=decode(*args,**kw);done+=len(result);progress('Estimating 2D joints',done,total);return result
                with patch.object(native77,'decode_native77_heatmaps',decoded):return detector.predict(frames,boxes)
        return Observations()
    def encoded(frames,boxes,intrinsics,model,**kwargs):
        total=len(frames);done=0;progress('Extracting body features',0,total)
        class Encoder:
            def encode(self,*args,**kw):
                nonlocal done
                result=model.encode(*args,**kw);done+=len(result.pose_tokens);progress('Extracting body features',done,total);return result
        return features(frames,boxes,intrinsics,Encoder(),**kwargs)
    def predicted(*args,**kwargs):
        progress('Solving temporal motion',0,1,unit='pass');result=motion(*args,**kwargs);progress('Solving temporal motion',1,1,unit='pass');return result
    with ExitStack() as stack:
        for name,value in [('detect_track',tracked),('load_native77_detector',observed),('extract_body_features',encoded),('run_motion',predicted)]:stack.enter_context(patch.object(module,name,value))
        yield
