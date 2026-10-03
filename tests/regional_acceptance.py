"""Controlled close-digit, seam, lock and rigid deformation acceptance."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import hashlib

import bpy
from mathutils import Quaternion, Vector
import numpy as np

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon)
bpy.ops.wm.read_factory_settings(use_empty=True);addon.register()
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
from local_character import skeleton,regions,skinning,regional_jobs
rig=skeleton.create_armature(bpy.context,1.75,0,False,(0,0,0))
names=[b.name for b in rig.data.bones if b.use_deform]
def make(name,positions,faces):
    data=bpy.data.meshes.new(name);data.from_pydata(positions,[],faces);data.update()
    mesh=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(mesh)
    mesh.parent=rig;mesh.modifiers.new('Armature','ARMATURE').object=rig
    for name in names:mesh.vertex_groups.new(name=name)
    return mesh
def put(mesh,vertex,row):
    for name,value in row.items():mesh.vertex_groups[name].add([vertex],value,'REPLACE')
# Two quads share a verified UV-style duplicate boundary; a very close third
# digit is a separate surface and must never receive spatial adjacency.
positions=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),(1,0,0),(2,0,0),(2,1,0),(1,1,0),
           (0,0,.000001),(1,0,.000001),(1,1,.000001),(0,1,.000001)]
mesh=make('SeamAndCloseDigits',positions,[(0,1,2,3),(4,5,6,7),(8,9,10,11)])
for i in range(4):put(mesh,i,{'LeftHandIndex1':.6,'LeftHandIndex2':.3,'LeftHandMiddle1':.1})
for i in range(4,8):put(mesh,i,{'LeftHandIndex2':.6,'LeftHandIndex3':.4})
for i in range(8,12):put(mesh,i,{'LeftHandMiddle1':.6,'LeftHandMiddle2':.4})
labels=regions.digit_labels(regions.dense_weights(mesh,names),names)
edges,conductance,seams,graph=regions.surface_graph(mesh,labels)
assert graph['verified_seam_edges']==1 and len(seams)==2,graph
assert not any((a<8)!=(b<8) for a,b in edges),'Close separate digits gained adjacency'
# Do not use a distance weld when opposing layers coincide exactly.
touching=make('OpposingContact',positions[:4]+positions[:4],[(0,1,2,3),(7,6,5,4)])
for i in range(8):put(touching,i,{'LeftHandIndex1':1})
contact_edges,_,_,contact=regions.surface_graph(touching,np.full(8,'LeftHandIndex'))
assert contact['verified_seam_edges']==0,contact
protected=make('ProtectedAndLocked',[(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[(0,1,2,3)])
for i in range(4):put(protected,i,{'LeftHandIndex1':.25,'LeftHandIndex2':.75 if i<2 else .25,**({} if i<2 else {'LeftHandIndex3':.5})})
regions.protect(protected,[0]);protected.vertex_groups['LeftHandIndex1'].lock_weight=True
# A ring and a mechanical plate use explicit rigid constraints, even with bad
# initial multi-bone weights; surface diffusion must not change their assignment.
ring=make('RigidRing',[(math.cos(a),math.sin(a),z) for z in (0,.1) for a in [i*math.tau/8 for i in range(8)]],
          [(i,(i+1)%8,(i+1)%8+8,i+8) for i in range(8)])
for i in range(16):put(ring,i,{'LeftHand':.6,'LeftHandIndex2':.4})
regions.mark(ring,list(range(16)),'RIGID','LeftHandIndex2')
robot=make('RobotPlate',[(-.1,-.1,0),(.1,-.1,0),(.1,.1,0),(-.1,.1,0)],[(0,1,2,3)])
for i in range(4):put(robot,i,{'LeftArm':.5,'LeftForeArm':.5})
regions.mark(robot,list(range(4)),'RIGID','LeftForeArm')
meshes=[mesh,protected,ring,robot]
before=skinning._digest(rig,meshes)
(collection,copied_rig,copies),reports=regions.refine(bpy.context,rig,meshes,'AUTO',16,.35)
assert before==skinning._digest(rig,meshes),'Refinement changed source geometry or weights'
field=regions.dense_weights(copies[0],names)
assert np.array_equal(field[1],field[4]) and np.array_equal(field[2],field[7]),'Verified seam weights disagree'
assert np.all(field[:8,names.index('LeftHandMiddle1')]==0),'Digit exclusion failed'
assert np.all(field[8:,:][:,[names.index('LeftHandIndex1'),names.index('LeftHandIndex2'),names.index('LeftHandIndex3')]]==0),'Cross-digit leakage'
locked=regions.dense_weights(copies[1],names);original=regions.dense_weights(protected,names)
assert np.array_equal(locked[0],original[0]),'Protected row changed'
assert np.array_equal(locked[:,names.index('LeftHandIndex1')],original[:,names.index('LeftHandIndex1')]),'Locked influence changed'
assert copies[1].vertex_groups['LeftHandIndex1'].lock_weight,'Lock flag lost on copy'
for copied,bone in [(copies[2],'LeftHandIndex2'),(copies[3],'LeftForeArm')]:
    weights=regions.dense_weights(copied,names)
    assert np.all(weights[:,names.index(bone)]==1) and np.all(weights.sum(axis=1)==1)
    p=copied_rig.pose.bones[bone];p.rotation_mode='QUATERNION';p.rotation_quaternion=Quaternion(Vector((1,0,0)),.7)
    bpy.context.view_layer.update();evaluated=copied.evaluated_get(bpy.context.evaluated_depsgraph_get())
    before_points=np.array([v.co[:] for v in copied.data.vertices]);after_points=np.array([v.co[:] for v in evaluated.data.vertices])
    distances_a=np.linalg.norm(before_points[:,None]-before_points[None,:],axis=2)
    distances_b=np.linalg.norm(after_points[:,None]-after_points[None,:],axis=2)
    assert np.max(np.abs(distances_a-distances_b))<1e-5,'Rigid component distorted under rotation'
    p.rotation_quaternion=Quaternion()
# The production path solves out of process, rejects intervening artist edits
# and corrupted constraint output, and applies through its own undo operator.
job=regional_jobs.prepare(bpy.context,rig,meshes,output/'jobs',iterations=16)
regional_jobs.start(job)
while skinning.poll(job)['status']=='running': time.sleep(.05)
assert skinning.poll(job)['status']=='complete',(job/'worker.log').read_text()
regions.protect(protected,[1])
count=len(bpy.data.objects)
try: regional_jobs.apply(bpy.context,job);raise AssertionError('Stale regional artist edits accepted')
except ValueError as exc: assert 'changed during refinement' in str(exc)
regions.protect(protected,[1],False)
assert skinning._digest(rig,meshes)==before
raw=(job/'output.npz').read_bytes();metadata=(job/'result.json').read_text()
with np.load(job/'output.npz',allow_pickle=False) as archive: bad={k:archive[k].copy() for k in archive.files}
bad['1_weights'][0]=0;bad['1_weights'][0,names.index('LeftHandIndex3')]=1
np.savez_compressed(job/'output.npz',**bad)
data=json.loads(metadata);data['output_sha256']=hashlib.sha256((job/'output.npz').read_bytes()).hexdigest()
(job/'result.json').write_text(json.dumps(data))
try: regional_jobs.apply(bpy.context,job);raise AssertionError('Worker protection violation accepted')
except ValueError as exc: assert 'artist weight constraints' in str(exc)
assert len(bpy.data.objects)==count
(job/'output.npz').write_bytes(raw);(job/'result.json').write_text(metadata)
bpy.context.scene.lc_settings.region_job=str(job)
assert bpy.ops.local_character.apply_region_job()=={'FINISHED'}
assert before==skinning._digest(rig,meshes)
try: regional_jobs.apply(bpy.context,job);raise AssertionError('Duplicate regional apply accepted')
except ValueError as exc: assert 'already applied' in str(exc)
cancelled=regional_jobs.prepare(bpy.context,rig,meshes,output/'jobs',iterations=200)
regional_jobs.start(cancelled);skinning.cancel(cancelled)
assert skinning.poll(cancelled)['status']=='cancelled' and not skinning._jobs
# Conflicting exact-rigid/locked constraints fail before any copy allocation.
robot.vertex_groups['LeftArm'].lock_weight=True
count=len(bpy.data.objects)
try:
    regions.refine(bpy.context,rig,[robot]);raise AssertionError('Conflicting rigid lock accepted')
except ValueError as exc:assert 'Locked influences conflict' in str(exc)
assert len(bpy.data.objects)==count
report={'passed':True,'source_preserved':True,'digit_exclusion':True,'close_surfaces_disconnected':True,
        'verified_seams_equal':True,'opposing_contacts_disconnected':True,'locked_and_protected_exact':True,
        'rigid_ring_and_plate_distance_preserved':True,'conflicting_constraints_rejected':True,'reports':reports}
report.update(isolated_worker=True,stale_artist_edits_rejected=True,corrupt_constraints_rejected=True,
              cancellation_passed=True,public_apply_operator=True,duplicate_apply_rejected=True)
(output/'regional-results.json').write_text(json.dumps(report,indent=2))
print('LOCAL_CHARACTER_REGIONAL_PASSED',json.dumps(report))
