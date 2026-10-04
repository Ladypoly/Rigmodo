"""Real MIA inference and copy application on a private captured character."""
import addon_utils,importlib,importlib.util,json,sys,time,zipfile
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix,Vector
args=sys.argv[sys.argv.index('--')+1:];job,reference,output=map(Path,args[:3]);output.mkdir(parents=True,exist_ok=True)
if len(args)>3:
    source=output/'extracted';source.mkdir(exist_ok=True)
    with zipfile.ZipFile(args[3]) as archive:archive.extractall(source)
    spec=importlib.util.spec_from_file_location('local_character',source/'__init__.py',submodule_search_locations=[str(source)])
    addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
else:
    addon_utils.enable('bl_ext.user_default.local_character',default_set=True)
    addon=importlib.import_module('bl_ext.user_default.local_character')
placement,hands,skinning,skeleton=(getattr(addon,n) for n in ('placement','hands','skinning','skeleton'))
ref=json.loads(reference.read_text());arrays=np.load(job/'input.npz');v=arrays['vertices'];tri=arrays['triangles']
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
data=bpy.data.meshes.new('Private fixture');data.from_pydata([(p[0],-p[2],p[1]) for p in v],[],tri.tolist());data.update()
mesh=bpy.data.objects.new('Private fixture',data);bpy.context.scene.collection.objects.link(mesh)
rig=skeleton.create_armature(bpy.context,1.8)
bpy.ops.object.mode_set(mode='EDIT')
for name,b in ref['bones'].items():
    bone=rig.data.edit_bones[name];bone.head=b['head'];bone.tail=b['tail'];bone.matrix=Matrix(b['matrix']);bone.length=(Vector(b['tail'])-Vector(b['head'])).length
bpy.ops.object.mode_set(mode='OBJECT');mesh.parent=rig;rig['lc_placement']='private_fixture'
for name,b in ref['bones'].items():
    if b['locked']:rig.data.bones[name]['lc_joint_locked']=True
# Give the source an exact paint value; refinement must copy it, not rebind.
group=mesh.vertex_groups.new(name='RightHandIndex2');group.add([0],.37,'REPLACE');modifier=mesh.modifiers.new('Fixture skin','ARMATURE');modifier.object=rig
locked='LeftHandIndex2';rig.data.bones[locked]['lc_joint_locked']=True
before=skinning._digest(rig,[mesh]);body={b.name:(b.head_local.copy(),b.tail_local.copy(),b.matrix_local.copy()) for b in rig.data.bones if not hands.hand_geometry.digit(b.name)}
folder=placement.prepare(bpy.context,[mesh],rig,parent=output,hands_only=True)
placement.start(folder)
while skinning.poll(folder)['status']=='running':time.sleep(.1)
assert skinning.poll(folder)['status']=='complete',(folder/'worker.log').read_text()
collection,target,copies,result=placement.apply(bpy.context,folder)
assert before==skinning._digest(rig,[mesh])
for name,(head,tail,matrix) in body.items():
    b=target.data.bones[name];assert (b.head_local-head).length<1e-7 and (b.tail_local-tail).length<1e-7,name
    assert max(abs(b.matrix_local[i][j]-matrix[i][j]) for i in range(4) for j in range(4))<1e-6,name
assert np.allclose(target.data.bones[locked].head_local,rig.data.bones[locked].head_local,atol=1e-7)
assert np.allclose(target.data.bones[locked].tail_local,rig.data.bones[locked].tail_local,atol=1e-7)
assert abs(copies[0].vertex_groups[group.name].weight(0)-.37)<1e-6
assert copies[0].modifiers[modifier.name].object==target
count=len(bpy.data.objects)
try:placement.apply(bpy.context,folder);raise AssertionError('Duplicate applied')
except ValueError as error:assert 'already applied' in str(error)
assert len(bpy.data.objects)==count
# A guide is exact in all three dimensions and influences descendants before fitting.
name='RightHandIndex2';i=result['names'].index(name);p=result['heads'][i];guide=[p[0],-p[2],p[1]]
guide[1]+=.001
data=dict(schema_version=1,source_digest=before,points={name:guide});bpy.context.scene.lc_settings.hand_guide_data=json.dumps(data)
second=placement.prepare(bpy.context,[mesh],rig,parent=output,hands_only=True,finger_guides=data)
placement.start(second)
while skinning.poll(second)['status']=='running':time.sleep(.1)
assert skinning.poll(second)['status']=='complete',(second/'worker.log').read_text()
_,guided,_,guided_result=placement.apply(bpy.context,second)
assert (guided.data.bones[name].head_local-Vector(guide)).length<1e-6
assert before==skinning._digest(rig,[mesh])
# Request edits and stale guides cannot bypass the public application gate.
third=placement.prepare(bpy.context,[mesh],rig,parent=output,hands_only=True,finger_guides=data)
import shutil
shutil.copy2(second/'output.json',third/'output.json');placement.finish(third);skinning._state(third,'complete')
changed=dict(data,points={name:[guide[0]+.01,*guide[1:]]});bpy.context.scene.lc_settings.hand_guide_data=json.dumps(changed)
count=len(bpy.data.objects)
try:placement.apply(bpy.context,third);raise AssertionError('Stale guides accepted')
except ValueError as error:assert 'Hand guides changed' in str(error)
assert len(bpy.data.objects)==count
bpy.context.scene.lc_settings.hand_guide_data=json.dumps(data)
request=json.loads((third/'request.json').read_text());request['seed']=123;(third/'request.json').write_text(json.dumps(request))
try:placement.apply(bpy.context,third);raise AssertionError('Changed request accepted')
except ValueError as error:assert 'constraints changed' in str(error)
assert len(bpy.data.objects)==count
summary=dict(passed=True,source_unchanged=True,body_matrices_preserved=True,locked_digit_exact=True,paint_preserved=True,
    guide_exact=True,duplicate_apply_rejected=True,stale_guides_rejected=True,changed_request_rejected=True,
    inference_seconds=result['elapsed_seconds'],device=result['device'],peak_reserved_vram_bytes=result['peak_reserved_vram_bytes'],
    hand_report=result['hand_report'],job=str(folder),version=addon.exporter.VERSION,extracted_archive=args[3] if len(args)>3 else None)
(output/'results.json').write_text(json.dumps(summary,indent=2));print('HAND_PLACEMENT_ACCEPTANCE',json.dumps(summary))
