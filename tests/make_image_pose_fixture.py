# SPDX-License-Identifier: GPL-3.0-or-later
"""Run with an external torch/roma environment and the public MHR v1.0.1 asset.

python THIS --mhr path/to/mhr_model.pt --output path/to/pose-fixture.json
This authors model parameters; it does not run SAM neural image prediction.
"""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch,roma
from sam_pose_worker import pack
ap=argparse.ArgumentParser();ap.add_argument('--mhr',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args();m=torch.jit.load(str(args.mhr),map_location='cpu');names=m.get_parameter_names();params=torch.zeros(1,204)
for name,value in {'l_uparm_ry':.3,'l_uparm_rz':.8,'l_elbow_bend':-1.1,'r_uparm_rz':-.4,'r_elbow_bend':-.5,
                   'spine_bend0':.2,'l_knee_bend':.45,'l_index1_rz':.4,'l_index2_rz':.8,'r_thumb1_ry':.4}.items():params[0,names.index(name)]=value
with torch.inference_mode():
    _,state=m(torch.zeros(1,45),params,torch.zeros(1,72),False)
    result=pack(m,dict(shape_params=torch.zeros(45).numpy(),mhr_model_params=params[0].numpy(),
                       pred_global_rots=roma.unitquat_to_rotmat(state[0,:,3:7]).numpy()))
args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,allow_nan=False))
print('MHR_POSE_FIXTURE',len(result['joints']))
