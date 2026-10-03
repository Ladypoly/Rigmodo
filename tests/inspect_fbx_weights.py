import json
from pathlib import Path
import sys
from io_scene_fbx import parse_fbx
path=Path(sys.argv[sys.argv.index('--')+1])
root,_=parse_fbx.parse(str(path))
objects=next(e for e in root.elems if e.id==b'Objects')
weights=[]
for element in objects.elems:
    if element.id==b'Deformer':
        for child in element.elems:
            if child.id==b'Weights': weights.extend(child.props[0])
small=[w for w in weights if 0<w<.001]
print('FBX_WEIGHTS',json.dumps({'count':len(weights),'below_001':len(small),'min':min(weights)}))
