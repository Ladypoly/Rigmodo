"""Diagnostic original-vertex neural weights vs imported Unity weights."""
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np
from scipy.spatial import cKDTree

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('skin_glb',root/'skin_glb.py')
transport=importlib.util.module_from_spec(spec); spec.loader.exec_module(transport)
binding=transport.read_binding(Path(sys.argv[1])/'output.glb')
fixture=Path(sys.argv[2])
unity=json.loads((fixture/'unity-weight-diagnostic.json').read_text())['vertices']
joints={j['name']:np.array(j['position']) for j in binding['joints']}
hips=joints['Hips'];up=joints['Head']-hips;up/=np.linalg.norm(up)
left=joints['LeftArm']-joints['RightArm'];left/=np.linalg.norm(left)
forward=np.cross(left,up);forward/=np.linalg.norm(forward)
points=(np.array(binding['positions'])-hips)@np.stack([left,forward,up],axis=1)
actual=np.array([[v['point'][k] for k in ('x','y','z')] for v in unity])
distance,index=cKDTree(points).query(actual)
names=[j['name'] for j in binding['joints']]
errors=[]
for u,source,dist in zip(unity,index,distance):
    expected={names[i]:w for i,w in zip(binding['ids'][source],binding['weights'][source]) if w>0}
    imported={name:w for name,w in zip(u['names'],u['weights']) if w>0}
    error=max(abs(expected.get(name,0)-imported.get(name,0)) for name in expected.keys()|imported.keys())
    errors.append((error,float(dist),int(source),expected,imported))
print(json.dumps({'base_vertex_error_max_m':float(distance.max()),'weight_error_max':max(v[0] for v in errors),
                  'largest_rows':sorted(errors,reverse=True,key=lambda p:p[0])[:8]},indent=2))
