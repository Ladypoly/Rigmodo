"""Closed/open surfaces, close digits, unbound geometry, paint and rigid pieces."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import bpy
import numpy as np

root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import regional_jobs,skinning,regions,geometry_math
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
data=bpy.data.armatures.new('GeometryRig');rig=bpy.data.objects.new('GeometryRig',data);bpy.context.scene.collection.objects.link(rig)
rig.select_set(True);bpy.context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='EDIT')
for name,z in [('Lower',0),('Upper',1)]:
    bone=data.edit_bones.new(name);bone.head=(0,0,z);bone.tail=(0,0,z+1)
data.edit_bones['Upper'].parent=data.edit_bones['Lower'];bpy.ops.object.mode_set(mode='OBJECT')
def cylinder(name,offset=0,radius=.15,length=2,closed=True):
    positions=[(offset+radius*math.cos(i*math.tau/16),radius*math.sin(i*math.tau/16),j*length/10) for j in range(11) for i in range(16)]
    faces=[]
    for j in range(10):
        for i in range(16):
            a=j*16+i;b=j*16+(i+1)%16;faces.extend([(a,b,b+16),(a,b+16,a+16)])
    if closed:
        positions.extend([(offset,0,0),(offset,0,length)])
        for i in range(16):faces.extend([(176,(i+1)%16,i),(177,160+i,160+(i+1)%16)])
    block=bpy.data.meshes.new(name);block.from_pydata(positions,[],faces);block.update()
    mesh=bpy.data.objects.new(name,block);bpy.context.scene.collection.objects.link(mesh);return mesh
closed=cylinder('ClosedOrganic');open_mesh=cylinder('OpenOrganic',closed=False)
original=skinning._digest(rig,[closed,open_mesh])
job=regional_jobs.prepare(bpy.context,rig,[closed,open_mesh],output,method='VOXEL',iterations=40,strength=1.)
regional_jobs.start(job)
while skinning.poll(job)['status']=='running':time.sleep(.05)
assert skinning.poll(job)['status']=='complete',(job/'worker.log').read_text()
(collection,copied,copies),reports=regional_jobs.apply(bpy.context,job)
assert original==skinning._digest(rig,[closed,open_mesh])
assert reports[0]['geometry_method']=='VOXEL_WITH_SURFACE_DETAILS',reports
assert 'open or nonmanifold' in reports[1]['volume_fallback_reason'],reports
for mesh in copies:
    weights=regions.dense_weights(mesh,['Lower','Upper']);assert np.max(abs(weights.sum(axis=1)-1))<1e-5
    assert weights[:16,0].mean()>.8 and weights[160:176,1].mean()>.8
    assert abs(weights[80:96,0].mean()-.5)<.15,weights[80:96]
# Locked paint and a protected complete row survive geometric rebuilding.
paint=copies[0];accepted=copied;weights=regions.dense_weights(paint,['Lower','Upper'])
paint.vertex_groups['Lower'].lock_weight=True;regions.protect(paint,[83])
locked_before=skinning._digest(accepted,[paint])
job=regional_jobs.prepare(bpy.context,accepted,[paint],output,method='GEODESIC',iterations=8,strength=1.)
regional_jobs.start(job)
while skinning.poll(job)['status']=='running':time.sleep(.05)
(_,rerig,refined),_=regional_jobs.apply(bpy.context,job)
after=regions.dense_weights(refined[0],['Lower','Upper'])
assert np.array_equal(after[:,0],weights[:,0]) and np.array_equal(after[83],weights[83])
assert locked_before==skinning._digest(accepted,[paint])
# Neighboring disconnected digits retain exclusive bone families, including
# new unweighted geometry. Volume routing explicitly leaves these on surface.
bpy.ops.object.select_all(action='DESELECT');rig.select_set(True);bpy.context.view_layer.objects.active=rig
bpy.ops.object.mode_set(mode='EDIT')
for name,x in [('LeftHandIndex1',0),('LeftHandMiddle1',.025)]:
    b=rig.data.edit_bones.new(name);b.head=(x,0,0);b.tail=(x,0,.2)
bpy.ops.object.mode_set(mode='OBJECT')
digits=[cylinder('Index',0,.009,.2),cylinder('Middle',.025,.009,.2)]
job=regional_jobs.prepare(bpy.context,rig,digits,output,method='VOXEL',iterations=20,strength=1.)
regional_jobs.start(job)
while skinning.poll(job)['status']=='running':time.sleep(.05)
(_,digit_rig,digit_copies),digit_reports=regional_jobs.apply(bpy.context,job)
names=[b.name for b in rig.data.bones if b.use_deform]
for mesh,name,report in zip(digit_copies,['LeftHandIndex1','LeftHandMiddle1'],digit_reports):
    field=regions.dense_weights(mesh,names)
    assert np.all(field[:,names.index(name)]==1),field
    assert report['surface_detail_vertices']==len(mesh.data.vertices),report
# A ring is marked as rigid, independent of organic solver choice.
ring=cylinder('FingerRing',0,.012,.02,closed=False)
regions.mark(ring,list(range(len(ring.data.vertices))),'RIGID','LeftHandIndex1')
job=regional_jobs.prepare(bpy.context,rig,[ring],output,method='GEODESIC',iterations=4,strength=1.)
regional_jobs.start(job)
while skinning.poll(job)['status']=='running':time.sleep(.05)
(_,ring_rig,ring_copy),ring_report=regional_jobs.apply(bpy.context,job)
assert np.all(regions.dense_weights(ring_copy[0],names)[:,names.index('LeftHandIndex1')]==1)
# Closed shells that overlap are rejected rather than carving clothing holes.
points=np.asarray([tuple(v.co) for v in closed.data.vertices]);closed.data.calc_loop_triangles()
faces=np.asarray([tuple(t.vertices) for t in closed.data.loop_triangles])
valid,reason=geometry_math.closed_mesh(np.vstack((points,points*.9+[0,0,.1])),np.vstack((faces,faces+len(points))))
assert not valid and 'overlapping' in reason,reason
summary=dict(passed=True,reports=reports,digit_reports=digit_reports,rigid_report=ring_report,
             paint_protection_exact=True,locked_column_exact=True,overlapping_shell_rejection=reason)
(output/'results.json').write_text(json.dumps(summary,indent=2));print('GEOMETRY_ACCEPTANCE',json.dumps(summary))
