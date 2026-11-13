"""Conservative automatic heading and labels, including ambiguous and rotated rigs."""
import bpy,importlib.util,json,sys
from pathlib import Path
import numpy as np
r=Path(__file__).resolve().parents[1];args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('rigmodo_annotation_test',r/'__init__.py',submodule_search_locations=[str(r)])
a=importlib.util.module_from_spec(spec);sys.modules[spec.name]=a;spec.loader.exec_module(a);a.register();bpy.context.preferences.addons.new().module=spec.name
g=a.creature_annotation
assert g.clean('DEF-tail01')=='tail 01' and g.clean('l_forearm2')=='Left forearm 2'
names=['Pelvis','Head','Left Hip','Left Knee','Left Foot','Right Hip','Right Knee','Right Foot']
parents=[-1,0,0,2,3,0,5,6];heads=np.array([[0,0,.5],[.5,0,.7],[0,.2,.4],[0,.3,.2],[.1,.35,0],[0,-.2,.4],[0,-.3,.2],[.1,-.35,0]])
tails=heads+[.1,0,0];angle=.63;c=np.cos(angle);s=np.sin(angle);rot=np.array([[c,-s,0],[s,c,0],[0,0,1]])
report=g.analyze(names,parents,heads@rot.T,tails@rot.T)
assert np.dot(report['forward'],rot[:,0])>.999999 and report['confidence']=='named'
names=['Joint'+str(i) for i in range(7)];angles=np.linspace(0,2*np.pi,6,endpoint=False)
heads=np.vstack([[0,0,.3],np.column_stack([np.cos(angles),np.sin(angles),np.full(6,.2)])]);tails=heads.copy();tails[1:,:2]*=1.5
radial=g.analyze(names,[-1]+[0]*6,heads,tails);assert radial['confidence']=='review'
rig=a.skeleton.create_armature(bpy.context);before=a.skinning._digest(rig,[]);rig.data.bones['Head'].lc_unimate_label='Custom Head'
first=g.annotate(rig);second=g.annotate(rig)
assert before==a.skinning._digest(rig,[]) and rig.data.bones['Head'].lc_unimate_label=='Custom Head' and first['forward']==second['forward']
result=dict(passed=True,rotated_named_heading=True,ambiguous_radial_requires_review=True,manual_labels_preserved=True,source_rest_preserved=True)
if len(args)>1:
    fixture=json.loads(Path(args[1]).read_text());tripo=g.analyze(**fixture)
    assert tripo['confidence']=='geometry' and np.dot(tripo['forward'],[1,0,0])>.98,tripo
    mapping=dict(zip(fixture['names'],tripo['labels']))
    assert mapping['bone_3']=='Tail' and mapping['bone_24']=='Left Front Hip' and mapping['bone_19']=='Left Claw',mapping
    result['unnamed_tripo_scanned']=True;result['tripo_labels']=mapping;result['tripo_forward']=tripo['forward']
(out/'results.json').write_text(json.dumps(result,indent=2));print('CREATURE_ANNOTATION_ACCEPTANCE',json.dumps(result),flush=True)
