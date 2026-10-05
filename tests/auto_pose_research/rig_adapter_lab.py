# SPDX-License-Identifier: GPL-3.0-or-later
"""Background Rigmodo matrix/offset/performance probe. No live character edits."""
import importlib.util,json,math,statistics,sys,time
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix,Quaternion,Vector

ROOT=Path(__file__).resolve().parents[2]
assert bpy.app.background and '--factory-startup' in sys.argv, 'Use an isolated factory-startup background process'
spec=importlib.util.spec_from_file_location('adapter_skeleton',ROOT/'skeleton.py')
skeleton=importlib.util.module_from_spec(spec);sys.modules[spec.name]=skeleton;spec.loader.exec_module(skeleton)
spec=importlib.util.spec_from_file_location('adapter_solver',Path(__file__).with_name('solver_lab.py'))
lab=importlib.util.module_from_spec(spec);sys.modules[spec.name]=lab;spec.loader.exec_module(lab)
spec=importlib.util.spec_from_file_location('adapter_ik',ROOT/'kinematics.py')
ik=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ik;spec.loader.exec_module(ik)
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
rig=skeleton.create_armature(bpy.context,1.75,20)
bpy.ops.object.mode_set(mode='EDIT')
for i,b in enumerate(rig.data.edit_bones):b.roll+=(i%7-3)*.13
bpy.ops.object.mode_set(mode='OBJECT')
ordered=sorted(rig.data.bones,key=lambda b:len(b.parent_recursive))
initial={b.name:Matrix.Identity(4) for b in ordered}
initial['LeftForeArm']=Matrix.Rotation(.6,4,'Y')

def fk(basis):
    poses={}
    for b in ordered:
        poses[b.name]=b.convert_local_to_pose(basis[b.name],b.matrix_local,
            parent_matrix=poses[b.parent.name] if b.parent else Matrix.Identity(4),
            parent_matrix_local=b.parent.matrix_local if b.parent else Matrix.Identity(4))
    return poses

def adapt(points,basis,free_heads=False):
    poses={};bases={}
    for b in ordered:
        inherited=b.convert_local_to_pose(basis[b.name],b.matrix_local,
            parent_matrix=poses[b.parent.name] if b.parent else Matrix.Identity(4),
            parent_matrix_local=b.parent.matrix_local if b.parent else Matrix.Identity(4))
        if b.name in points:
            head,tail=points[b.name];direction=(tail-head).normalized();q=inherited.to_quaternion()
            current=q@Vector((0,1,0));rotation=current.rotation_difference(direction)@q
            desired=rotation.to_matrix().to_4x4()
            desired.translation=head if free_heads or b.name=='Hips' else inherited.translation
        else:desired=inherited
        local=b.convert_local_to_pose(desired,b.matrix_local,
            parent_matrix=poses[b.parent.name] if b.parent else Matrix.Identity(4),
            parent_matrix_local=b.parent.matrix_local if b.parent else Matrix.Identity(4),invert=True)
        # Eliminate decomposition drift; preserve only permitted translations.
        local=Matrix.LocRotScale(local.translation if free_heads or b.name in {'Root','Hips'} else Vector(),local.to_quaternion(),Vector((1,1,1)))
        bases[b.name]=local
        poses[b.name]=b.convert_local_to_pose(local,b.matrix_local,
            parent_matrix=poses[b.parent.name] if b.parent else Matrix.Identity(4),
            parent_matrix_local=b.parent.matrix_local if b.parent else Matrix.Identity(4))
    return poses,bases

def write(bases):
    for p in rig.pose.bones:p.matrix_basis=bases[p.name]

def set_global(name,desired,bases):
    poses=fk(bases);b=rig.data.bones[name]
    local=b.convert_local_to_pose(desired,b.matrix_local,
        parent_matrix=poses[b.parent.name] if b.parent else Matrix.Identity(4),
        parent_matrix_local=b.parent.matrix_local if b.parent else Matrix.Identity(4),invert=True)
    bases[name]=Matrix.LocRotScale(local.translation if name=='Hips' else Vector(),local.to_quaternion(),Vector((1,1,1)))

def set_direction(name,direction,bases):
    poses=fk(bases);old=poses[name];q=old.to_quaternion()
    q=(q@Vector((0,1,0))).rotation_difference(direction.normalized())@q
    desired=q.to_matrix().to_4x4();desired.translation=old.translation;set_global(name,desired,bases)

def harden_pins(bases,pins):
    """Limited analytic feasibility proof: hands/feet only, no angle limits.

    Clamp pelvis translation into two-link reach spheres, then exact limb IK.
    Feasible original pins; production must gate residuals and keep last valid.
    """
    bases={k:v.copy() for k,v in bases.items()};reference=fk({b.name:Matrix.Identity(4) for b in ordered})
    # This probe's pelvis pin is a FULL FRAME pin. A position-only pelvis pin
    # needs an additional angular feasibility solve, beyond this prototype.
    if 'Hips' in pins:set_global('Hips',reference['Hips'],bases)
    chains={}
    for name in pins:
        side='Left' if name.startswith('Left') else 'Right'
        if name.endswith('Foot'):chains[name]=(side+'UpLeg',side+'Leg',Vector((0,-1,0)))
        elif name.endswith('Hand'):chains[name]=(side+'Arm',side+'ForeArm',Vector((0,1,-.3)))
    for iteration in range(24):
        changed=False
        for name,(a,b,pole) in chains.items():
            poses=fk(bases);head=poses[a].translation;goal=reference[name].translation;v=goal-head
            reach=rig.data.bones[a].length+rig.data.bones[b].length-1e-6
            if v.length>reach and 'Hips' not in pins:
                desired=poses['Hips'].copy();desired.translation+=v.normalized()*(v.length-reach)
                set_global('Hips',desired,bases);changed=True
        if not changed:break
    for name,(a,b,pole) in chains.items():
        poses=fk(bases);start=poses[a].translation;knee=poses[b].translation;end=poses[name].translation
        goal=reference[name].translation;new_knee,new_end,clamped=ik.two_bone(start,knee,end,goal,pole)
        set_direction(a,new_knee-start,bases);set_direction(b,new_end-new_knee,bases)
        poses=fk(bases);desired=reference[name].copy();desired.translation=poses[name].translation
        set_global(name,desired,bases)
    return fk(bases),bases

reference=fk(initial)
points={b.name:(reference[b.name].translation,reference[b.name]@Vector((0,b.length,0))) for b in ordered}
roundtrip,bases=adapt(points,initial)
roundtrip_error=max(abs(v) for name in reference for row in reference[name]-roundtrip[name] for v in row)
assert roundtrip_error<3e-6

# Minimal world swing transports the original axial orientation rather than
# resetting roll with track_quat. No arbitrary roll axis is assumed.
name='LeftForeArm';q0=reference[name].to_quaternion();y0=q0@Vector((0,1,0));axis=(q0@Vector((1,0,0))).normalized()
desired_q=Quaternion(axis,.4)@q0
changed=dict(points);head=reference[name].translation
changed[name]=(head,head+(desired_q@Vector((0,1,0)))*rig.data.bones[name].length)
transport,_=adapt(changed,initial)
twist_transport_error=transport[name].to_quaternion().rotation_difference(desired_q).angle
assert twist_transport_error<1e-5

# Apply a graph proposal to true disconnected Rigmodo parent offsets.
model=lab.Model();proposal_rows=[];hybrid_rows=[]
for label,active,target,pins in lab.cases(model):
    solved=lab.relax(model,active,target,pins)
    end_names={'Hips':'Spine','Spine':'Spine1','Spine1':'Spine2','Spine2':'Neck','Neck':'Head','Head':'Head_end'}
    for s in ('Left','Right'):
        end_names.update({s+a:s+b for a,b in [('Shoulder','Arm'),('Arm','ForeArm'),('ForeArm','Hand'),('Hand','Hand_end'),('UpLeg','Leg'),('Leg','Foot'),('Foot','ToeBase'),('ToeBase','ToeBase_end')]})
    desired={n:(solved[model.idx(n)],solved[model.idx(e)]) for n,e in end_names.items()}
    poses,bases=adapt(desired,{b.name:Matrix.Identity(4) for b in ordered})
    _,naive=adapt(desired,{b.name:Matrix.Identity(4) for b in ordered},True)
    residual=max((poses[n].translation-desired[n][0]).length for n in desired)
    pin_residual=max([(poses[n].translation-model.rest[model.idx(n)]).length for n in pins] or [0.])
    offsets=max(naive[b.name].translation.length for b in ordered if b.name not in {'Root','Hips'})
    length_error=max(abs((poses[b.name]@Vector((0,b.length,0))-poses[b.name].translation).length-b.length) for b in ordered)
    assert length_error<2e-6
    proposal_rows.append(dict(case=label,attachment_reconstruction_residual_m=residual,after_fk_pin_error_m=pin_residual,
        naive_non_root_translation_m=offsets,rig_bone_length_error_m=length_error))
    hybrid,hybrid_bases=harden_pins(bases,pins)
    hybrid_pin_error=max([(hybrid[n].translation-model.rest[model.idx(n)]).length for n in pins] or [0.])
    hybrid_length_error=max(abs((hybrid[b.name]@Vector((0,b.length,0))-hybrid[b.name].translation).length-b.length) for b in ordered)
    hybrid_rows.append(dict(case=label,pin_error_m=hybrid_pin_error,bone_length_error_m=hybrid_length_error,
        active_target_error_m=(hybrid[active].translation-Vector(target)).length,
        pelvis_delta_m=(hybrid['Hips'].translation-model.rest[model.idx('Hips')]).length,
        safety_gate_accept=hybrid_pin_error<4e-6 and hybrid_length_error<2e-6))
    assert hybrid_length_error<2e-6
    if label in {'small_hand','far_hand','extreme_arm','pelvis_down'}:assert hybrid_pin_error<4e-6

# 29 point solver plus the whole 53-bone write, one update per mouse sample.
_,active,target,pins=lab.cases(model)[0];times=[];write_times=[];update_times=[];solver_times=[]
for sample in range(100):
    start=time.perf_counter();solved=lab.relax(model,active,target,pins);a=time.perf_counter()
    desired={n:(solved[model.idx(n)],solved[model.idx(e)]) for n,e in end_names.items()}
    poses,bases=adapt(desired,initial);poses,bases=harden_pins(bases,pins);write(bases);b=time.perf_counter();bpy.context.view_layer.update();c=time.perf_counter()
    solver_times.append((a-start)*1000);write_times.append((b-a)*1000);update_times.append((c-b)*1000);times.append((c-start)*1000)

# Uniform object translation/rotation/scale does not change armature-space solve.
rig.matrix_world=Matrix.LocRotScale(Vector((2,-3,.7)),Quaternion((0,0,1),.6),Vector((2,2,2)))
world_error=max((rig.matrix_world.inverted()@(rig.matrix_world@p)-p).length for p in model.rest)
rig.scale=(1,2,1);bpy.context.view_layer.update();s=rig.matrix_world.to_scale();nonuniform_rejected=max(s)-min(s)>1e-5
assert nonuniform_rejected

def timing(data):return dict(median_ms=statistics.median(data),p95_ms=float(np.percentile(data,95)))
fixture_benchmark=None
if len(sys.argv[sys.argv.index('--')+1:])>1:
    fixture=Path(sys.argv[sys.argv.index('--')+2])
    with bpy.data.libraries.load(str(fixture),link=False) as (library_source,library_dest):library_dest.objects=library_source.objects
    objects=[o for o in library_dest.objects if o]
    for obj in objects:
        if obj.name not in bpy.context.scene.objects:bpy.context.scene.collection.objects.link(obj)
        obj.hide_set(False)
    avatar=next(o for o in objects if o.type=='ARMATURE')
    meshes=[o for o in objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==avatar for m in o.modifiers)]
    bpy.context.view_layer.update();timings=[]
    _,benchmark_active,benchmark_goal,benchmark_pins=lab.cases(model)[0]
    for sample in range(100):
        start=time.perf_counter();lab.relax(model,benchmark_active,benchmark_goal,benchmark_pins)
        for p in avatar.pose.bones:
            if skeleton.canonical_name(p.name) in skeleton.BODY or skeleton.canonical_name(p.name) in {s+a for s in ('Left','Right') for a in skeleton.LIMBS}:
                p.rotation_mode='QUATERNION';p.rotation_quaternion=Quaternion((1,0,0),math.sin(sample*.1)*.03)
        bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
        vertices=sum(len(mesh.evaluated_get(dg).data.vertices) for mesh in meshes)
        timings.append((time.perf_counter()-start)*1000)
    fixture_benchmark=dict(samples=100,base_vertices=sum(len(m.data.vertices) for m in meshes),evaluated_vertices=vertices,
        total=timing(timings),scope='graph prototype plus direct body-bone writes and actual skinned mesh evaluation; no anatomical-quality or viewport-draw claim')
report=dict(passed=True,blender=bpy.app.version_string,rig_bones=len(ordered),solver_joints=len(model.names),
    matrix_roundtrip_max_error=roundtrip_error,preserved_roll_and_transport_twist_error_rad=twist_transport_error,
    all_hybrid_cases_feasible=all(r['safety_gate_accept'] for r in hybrid_rows),hybrid_pelvis_pin_mode='full_frame',
    uniform_world_roundtrip_error_m=world_error,nonuniform_rejected=nonuniform_rejected,
    disconnected_rig_proposals=proposal_rows,hybrid_analytic_pin_projection=hybrid_rows,private_avatar_evaluation_benchmark=fixture_benchmark,
    benchmark=dict(samples=100,mesh_vertices=0,solver=timing(solver_times),adapter_write=timing(write_times),depsgraph_update=timing(update_times),total=timing(times),
        limit='CPU, bare armature; not real-avatar viewport/frame-rate acceptance'))
(out/'adapter-results.json').write_text(json.dumps(report,indent=2)+'\n')
print('RIG_ADAPTER_LAB_COMPLETE',json.dumps(report),flush=True)
