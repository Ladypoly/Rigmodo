import os
import json,time,urllib.request,sys,hashlib
from pathlib import Path
import cv2,numpy as np,mediapipe as mp
models=Path('R:/AI/Models/Rigmodo/mediapipe');models.mkdir(parents=True,exist_ok=True);model=models/'pose_landmarker_lite.task'
if not model.exists():urllib.request.urlretrieve('https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task',model)
options=mp.tasks.vision.PoseLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),running_mode=mp.tasks.vision.RunningMode.VIDEO,num_poses=1)
source=os.environ.get('RIGMODO_TEST_VIDEO','R:/AI/Rigmodo/Jobs/Acceptance/full-avatar-walk/avatar-walk.mp4');cap=cv2.VideoCapture(source);fps=cap.get(cv2.CAP_PROP_FPS);samples=[];visibility=[];began=time.monotonic();count=0
with mp.tasks.vision.PoseLandmarker.create_from_options(options) as detector:
    while True:
        ok,frame=cap.read()
        if not ok:break
        image=mp.Image(image_format=mp.ImageFormat.SRGB,data=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB));result=detector.detect_for_video(image,round(count/fps*1000));count+=1
        if result.pose_world_landmarks:
            row=result.pose_world_landmarks[0];samples.append([[p.x,p.y,p.z] for p in row]);visibility.append([p.visibility for p in result.pose_landmarks[0]])
cap.release();elapsed=time.monotonic()-began
report=dict(passed=bool(samples),provider='MediaPipe Pose Landmarker Lite',device='CPU',elapsed_seconds=elapsed,decoded_frames=count,detected_frames=len(samples),mean_visibility=float(np.mean(visibility)),fps=fps,world_joints=33,model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),comparison_limit='Detection baseline only; not a temporal world-motion or contact model. No retargeted quality equivalence claimed.')
Path(sys.argv[1]).write_text(json.dumps(report,indent=2));print('MEDIAPIPE_BASELINE',json.dumps(report))
