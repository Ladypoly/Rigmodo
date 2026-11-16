"""Progress/error protocol and transformed refinement snapshot regression."""
import bpy,addon_utils,importlib,json,sys,tempfile,time
from pathlib import Path
from mathutils import Matrix
addon_utils.enable('bl_ext.user_default.local_character')
a=importlib.import_module('bl_ext.user_default.local_character');rgb=importlib.import_module(a.__name__+'.rgbmocap')
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
python=a.regional_jobs.python_executable();seen=[]
rgb.run([str(python),'-c',"print('@@MOCAP@@{\"type\":\"progress\",\"current\":4,\"total\":9,\"message\":\"Body features\"}');print('@@MOCAP@@{\"type\":\"complete\"}')"],out,None,lambda phase,**kw:seen.append((phase,kw)),'Starting')
assert seen[-1][1]==dict(completed=4,total=9,unit='frames'),seen
try:rgb.run([str(python),'-c',"print('@@MOCAP@@{\"type\":\"failed\",\"message\":\"Model missing\"}');exit(7)"],out,None,lambda *a,**k:None,'Starting');raise AssertionError('Failure swallowed')
except RuntimeError as e:assert str(e)=='Model missing'
assert rgb.event('ordinary model log') is None
assert rgb.event('progress bar '+rgb.PREFIX+'{"type":"progress","current":2,"total":3}')['current']==2
import subprocess
script="import sys,io;sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='cp1252');sys.path.insert(0,"+repr(str(Path(a.__file__).parent))+");import video_worker;print(chr(0x258f))"
encoded=subprocess.run([str(python),'-c',script],capture_output=True,text=True,encoding='utf-8')
assert encoded.returncode==0 and chr(0x258f) in encoded.stdout,(encoded.returncode,encoded.stderr)
for bad in ('@@MOCAP@@[]','@@MOCAP@@'+('x'*1048577)):
 try:rgb.event(bad);raise AssertionError('Invalid event accepted')
 except ValueError:pass
assert 'missing' in rgb.status(out)
bpy.ops.wm.read_factory_settings(use_empty=True)
rig=a.skeleton.create_armature(bpy.context);bpy.ops.mesh.primitive_cube_add(size=.1,location=(0,0,1));body=bpy.context.object
body.parent=rig;body.matrix_world=Matrix.Rotation(.73,4,'Z')@Matrix.Scale(2.114974,4);body.vertex_groups.new(name='Hips').add(list(range(8)),1.,'REPLACE');body.modifiers.new('Skin','ARMATURE').object=rig
from types import SimpleNamespace
assert a.character_context.bound_meshes(SimpleNamespace(view_layer=SimpleNamespace(objects=[None,body])),rig)==[body]
collection,copy_rig,meshes=a.weight_copy.clone(bpy.context,rig,[body],label='Snapshot')
job=a.regional_jobs.prepare(bpy.context,copy_rig,meshes,out/'jobs',iterations=2)
request=json.loads((job/'request.json').read_text());bpy.context.view_layer.update()
assert request['source_digest']==a.skinning._digest(copy_rig,meshes),'Freshly parented mesh invalidates itself'
a.regional_jobs.start(job)
while a.skinning.poll(job)['status']=='running':time.sleep(.05)
assert a.skinning.poll(job)['status']=='complete',(job/'worker.log').read_text()
a.regional_jobs.apply(bpy.context,job)
body.data.vertices[0].co.x+=.01
result=dict(passed=True,progress_counters=True,utf8_worker_logs=True,embedded_progress_events=True,worker_error_preserved=True,invalid_events_rejected=True,transformed_refinement_applied=True)
(out/'results.json').write_text(json.dumps(result,indent=2));print('RGBMOCAP_ACCEPTANCE_PASS',result)
