"""Closed/open sections, independent digits, guides and exact joint locks."""
import importlib.util,json,sys
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hand_geometry',root/'hand_geometry.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
vertices=[];triangles=[];names=[];heads=[];tails=[]
for s,side in enumerate(('Left','Right')):
    names.append(side+'Hand');heads.append([s*.4,0,0]);tails.append([s*.4,0,.01])
    for i,finger in enumerate(g.FINGERS):
        x=s*.4+i*.03;start=len(vertices)
        for z in (0,.03,.06,.09,.12):
            vertices.extend([[x+.008*np.cos(a),.008*np.sin(a),z] for a in np.arange(32)*np.pi/16])
        for j in range(4):
            for k in range(32):
                a=start+j*32+k;b=start+j*32+(k+1)%32;c=a+32;d=b+32
                triangles.extend(((a,b,c),(b,d,c)))
        for j,z in ((0,0),(4,.12)):
            centre=len(vertices);vertices.append([x,0,z])
            triangles.extend((centre,start+j*32+k,start+j*32+(k+1)%32) for k in range(32))
        points=np.asarray([[x+.004,.003,z] for z in (.021,.051,.081,.105)])
        for j in range(3):names.append(side+'Hand'+finger+str(j+1));heads.append(points[j]);tails.append(points[j+1])
vertices=np.asarray(vertices);triangles=np.asarray(triangles);heads=np.asarray(heads);tails=np.asarray(tails)
h,t,report=g.refine(vertices,triangles,names,heads,tails)
assert all(r['accepted'] for r in report),report
for i,name in enumerate(names):
    if not g.digit(name):assert np.array_equal(h[i],heads[i]) and np.array_equal(t[i],tails[i]);continue
    expected_x=(0 if name.startswith('Left') else .4)+g.FINGERS.index(next(f for f in g.FINGERS if f in name))*.03
    assert abs(h[i,0]-expected_x)<1e-6 and abs(h[i,1])<1e-6,(name,h[i])
    if name[-1]!='3':assert np.array_equal(t[i],h[names.index(name[:-1]+str(int(name[-1])+1))])
locked='LeftHandIndex2';index=names.index(locked)
locked_h,locked_t,_=g.refine(vertices,triangles,names,heads,tails,locked=[locked])
assert np.array_equal(locked_h[index],heads[index]) and np.array_equal(locked_t[index],tails[index])
guides={'RightHandMiddleTip':[.46,0,.119],'RightHandMiddle2':[.46,0,.05]}
guide_h,guide_t,_=g.refine(vertices,triangles,names,heads,tails,guides=guides)
assert np.array_equal(guide_h[names.index('RightHandMiddle2')],guides['RightHandMiddle2'])
assert np.array_equal(guide_t[names.index('RightHandMiddle3')],guides['RightHandMiddleTip'])
folded={'RightHandMiddle'+key:[.46,0,z] for key,z in zip(('1','2','3','Tip'),(.04,.065,.08,.055))}
fold_h,fold_t,_=g.refine(vertices,triangles,names,heads,tails,guides=folded)
assert np.array_equal(fold_t[names.index('RightHandMiddle3')],folded['RightHandMiddleTip'])
# Removing longitudinal faces opens every contour. No automatic centroid is trusted.
open_faces=triangles[(vertices[triangles].mean(axis=1)[:,1]>0)]
open_h,open_t,open_report=g.refine(vertices,open_faces,names,heads,tails)
assert not any(r['accepted'] for r in open_report)
assert np.array_equal(open_h,heads) and np.array_equal(open_t,tails)
# A concentric accessory shell gives competing sections. Do not infer which
# material is a deforming finger merely from its proximity.
shell=vertices[0:162].copy();shell[:,:2]*=1.5
shell_faces=triangles[:320]
_,_,shell_report=g.refine(np.vstack((vertices,shell)),np.vstack((triangles,shell_faces+len(vertices))),names,heads,tails)
assert not shell_report[0]['accepted'] and shell_report[0]['requires_review'],shell_report[0]
result=dict(passed=True,closed_centres_fitted=True,open_sections_rejected=True,competing_shells_rejected=True,body_unchanged=True,chains_connected=True,locks_exact=True,guides_exact=True)
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(result,indent=2))
print('HAND_GEOMETRY_ACCEPTANCE',json.dumps(result))
