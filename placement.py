# SPDX-License-Identifier: GPL-3.0-or-later
"""Geometry-only MIA placement jobs and editable, unbound review copies."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid
import bpy
import numpy as np
from mathutils import Matrix,Vector
from . import skeleton,skinning,hand_geometry

PIN='8fb51382ff6da556cdb95cc03a48200603f3a493'
SOURCE_HASHES={'model.py':'c8b920a35e2fcee9efcb6efeae89ed555dbd4a7ff763479f612aea214c2625da',
    'models_ae.py':'e8df87c61498de5501ada30b70406c81b89e2c3c00fa9a65aee846887ceb22da',
    'util/dataset_mixamo.py':'aec35104acff5c93ab197bc4426715f909900c7251642f745395e10ac445e917'}

def cache():return skinning.provider_cache().parent/'mia-original'

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def selected(context):
    meshes=[o for o in context.selected_objects if o.type=='MESH']
    rigs={m.object for o in meshes for m in o.modifiers if m.type=='ARMATURE' and m.object}
    rigs.update(o for o in context.selected_objects if o.type=='ARMATURE')
    if len(rigs)>1:raise ValueError('Select geometry for one character')
    rig=next(iter(rigs)) if rigs else None
    if rig:
        helpers={b.custom_shape for b in rig.pose.bones if b.custom_shape};meshes=[o for o in meshes if o not in helpers]
    if not meshes:raise ValueError('Select upright humanoid geometry for joint placement')
    return rig,meshes

def prepare(context,meshes,rig=None,parent=None,seed=0,provider=None,landmarks=None,hands_only=False,finger_guides=None):
    if context.mode!='OBJECT':raise ValueError('Return to Object Mode before joint placement')
    if len(set(meshes))!=len(meshes) or any(o.type!='MESH' for o in meshes):raise ValueError('Choose distinct character meshes')
    skinning.ensure_unique_character_meshes(meshes)
    if rig and rig.name not in context.scene.objects:raise ValueError('Return to the source character scene')
    if any(o.animation_data and (o.animation_data.action or o.animation_data.drivers or o.animation_data.nla_tracks) for o in meshes):
        raise ValueError('Use geometry without object animation or drivers for a joint proposal')
    expected={j.name for j in skeleton.template() if j.deform}
    preserve=bool(rig and (rig.get('lc_placement') or rig.get('lc_skinning')))
    if preserve and not hands_only and {b.name for b in rig.data.bones if b.use_deform}-expected:
        raise ValueError('Reuse accepted joints on rigs with extra deform bones; a core joint proposal would discard their paint')
    if hands_only:
        if not rig:raise ValueError('Select the accepted rig and its character meshes')
        from .hands import check_rig
        check_rig(rig)
    scale=context.scene.unit_settings.scale_length
    if not math.isfinite(scale) or scale<=0:raise ValueError('Scene scale must be positive')
    points=[];triangles=[]
    for mesh in meshes:
        if mesh.parent_type!='OBJECT' or mesh.constraints or mesh.matrix_world.determinant()<=1e-12:
            raise ValueError('Resolve constraints, bone parenting and mirrored transforms on a working copy')
        if any(m.type!='ARMATURE' and m.show_viewport for m in mesh.modifiers):
            raise ValueError('Resolve visible geometry modifiers on a working copy first')
        mesh.data.calc_loop_triangles();start=len(points)
        for vertex in mesh.data.vertices:
            p=mesh.matrix_world@vertex.co;points.append((p.x*scale,p.z*scale,-p.y*scale))
        triangles.extend(tuple(start+i for i in t.vertices) for t in mesh.data.loop_triangles)
    if not points or not triangles or len(points)>1_000_000 or len(triangles)>2_000_000:raise ValueError('Placement geometry is empty or exceeds its budget')
    vertices=np.asarray(points,dtype=np.float32);faces=np.asarray(triangles,dtype=np.int32)
    if not np.isfinite(vertices).all() or np.ptp(vertices,axis=0).max()<=1e-5:raise ValueError('Invalid placement geometry')
    directory=Path(parent) if parent else cache().parent.parent/'jobs';directory.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='joints-',dir=directory)).resolve()
    np.savez_compressed(folder/'input.npz',vertices=vertices,triangles=faces)
    request=dict(schema_version=1,provider='mia_original_landmarks',provider_revision=PIN,provider_cache=str(Path(provider or cache()).resolve()),
        seed=seed,source_hashes=SOURCE_HASHES,input_sha256=sha(folder/'input.npz'),
        parents={j.name:j.parent for j in skeleton.template() if j.deform})
    locks={b.name:dict(head=list(rig.matrix_world@b.head_local),tail=list(rig.matrix_world@b.tail_local))
           for b in rig.data.bones if b.get('lc_joint_locked')} if rig else {}
    source=dict(job_id=str(uuid.uuid4()),scene_unit_scale=scale,source_digest=skinning._digest(rig,meshes),
        rig=rig.name if rig else None,rig_pointer=str(rig.as_pointer()) if rig else None,
        meshes=[dict(name=o.name,pointer=str(o.as_pointer())) for o in meshes],locks=locks,preserve_weights=preserve,hands_only=hands_only)
    if landmarks:
        from .landmarks import validate
        source['landmarks']=validate(landmarks,meshes)
        for name,point in landmarks['points'].items():
            if name in locks and any(abs(locks[name]['head'][i]-point[i])>1e-6 for i in (0,2)):
                raise ValueError('Unlock '+name+' before changing its landmark')
    convert=lambda p:[p[0]*scale,p[2]*scale,-p[1]*scale]
    request['front_guides']={n:convert(p) for n,p in source.get('landmarks',{}).get('points',{}).items()}
    constraints={skeleton.canonical_name(n):{k:convert(v[k]) for k in ('head','tail')} for n,v in locks.items()}
    if hands_only:
        constraints.update({skeleton.canonical_name(b.name):{k:convert(rig.matrix_world@getattr(b,k+'_local')) for k in ('head','tail')}
            for b in rig.data.bones if skeleton.canonical_name(b.name) in expected and not hand_geometry.digit(skeleton.canonical_name(b.name))})
    request.update(joint_constraints=constraints,locked_digits=[n for n in constraints if hand_geometry.digit(n)],hand_fit=True)
    if finger_guides:
        from .hands import validate_guides
        source['finger_guides']=validate_guides(finger_guides,rig,meshes)
        request['finger_guides']={n:convert(p) for n,p in finger_guides['points'].items()}
    (folder/'request.json').write_text(json.dumps(request,indent=2,allow_nan=False))
    source['request_sha256']=sha(folder/'request.json')
    (folder/'source.json').write_text(json.dumps(source,indent=2))
    skinning._state(folder,'prepared');return folder

def finish(folder):
    result=_output(folder)
    (folder/'result.json').write_text(json.dumps(dict(output_sha256=sha(folder/'output.json'),
        elapsed_seconds=result['elapsed_seconds'],device=result['device'])))

def start(folder,python=None):
    if skinning._jobs:raise ValueError('Wait for the current local job or cancel it')
    folder=Path(folder).resolve()
    request=json.loads((folder/'request.json').read_text())
    python=Path(python or Path(request['provider_cache'])/'runtime/Scripts/python.exe').resolve()
    if request['source_hashes']!=SOURCE_HASHES or request['provider_revision']!=PIN or skinning.poll(folder)['status']!='prepared':
        raise ValueError('Prepare a new pinned placement job')
    if not python.is_file():raise ValueError('Install the isolated MIA CUDA runtime first')
    log=(folder/'worker.log').open('wb')
    try:process=subprocess.Popen([str(python),'-I',str(Path(__file__).with_name('mia_worker.py')),str(folder)],
        cwd=python.parent,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except Exception:log.close();raise
    skinning._jobs[str(folder)]=dict(process=process,log=log,started=time.monotonic(),finish=finish,phase='Placing humanoid joints')
    try:skinning._state(folder,'running',pid=process.pid)
    except OSError:skinning.cancel(folder);raise
    return process.pid

def _output(folder):
    folder=Path(folder);path=folder/'output.json'
    if path.stat().st_size>256*1024:raise ValueError('Joint result exceeds its size budget')
    result=json.loads(path.read_text());names=result['names']
    expected={j.name for j in skeleton.template() if j.deform}
    heads=np.asarray(result['heads'],dtype=np.float64);tails=np.asarray(result['tails'],dtype=np.float64)
    if result['provider']!='mia_original_landmarks' or result['coordinate_space']!='world_meters_gltf_y_up':raise ValueError('Invalid joint proposal protocol')
    if len(names)!=52 or set(names)!=expected or heads.shape!=(52,3) or tails.shape!=(52,3) or not np.isfinite(heads).all() or not np.isfinite(tails).all():
        raise ValueError('Invalid joint proposal arrays')
    if (np.linalg.norm(tails-heads,axis=1)<1e-5).any():raise ValueError('Joint proposal contains zero-length bones')
    return result

def apply(context,folder):
    folder=Path(folder).resolve()
    if context.mode!='OBJECT' or skinning.poll(folder)['status'] not in {'complete','applied'}:raise ValueError('Placement job is not ready')
    source=json.loads((folder/'source.json').read_text());request=json.loads((folder/'request.json').read_text())
    if source.get('request_sha256') and source['request_sha256']!=sha(folder/'request.json'):raise ValueError('Placement constraints changed after preparation')
    if sha(folder/'input.npz')!=request['input_sha256'] or sha(folder/'output.json')!=json.loads((folder/'result.json').read_text())['output_sha256']:
        raise ValueError('Placement input or result changed')
    result=_output(folder);rig=bpy.data.objects.get(source['rig']) if source['rig'] else None
    meshes=[bpy.data.objects.get(entry['name']) for entry in source['meshes']]
    if any(not o or str(o.as_pointer())!=entry['pointer'] or o.name not in context.scene.objects for o,entry in zip(meshes,source['meshes'])):
        raise ValueError('Placement source meshes no longer match')
    if source['rig'] and (not rig or str(rig.as_pointer())!=source['rig_pointer'] or rig.name not in context.scene.objects):raise ValueError('Placement source rig no longer matches')
    if source['source_digest']!=skinning._digest(rig,meshes) or source['scene_unit_scale']!=context.scene.unit_settings.scale_length:
        raise ValueError('Source geometry or corrected joints changed during placement')
    if rig and source['locks']!={b.name:dict(head=list(rig.matrix_world@b.head_local),tail=list(rig.matrix_world@b.tail_local)) for b in rig.data.bones if b.get('lc_joint_locked')}:
        raise ValueError('Joint locks changed during placement')
    if source.get('landmarks'):
        from .landmarks import validate
        validate(source['landmarks'],meshes)
        if json.loads(context.scene.lc_settings.landmark_data or '{}')!=source['landmarks']:raise ValueError('Landmarks changed during inference; generate the rig again')
    if source.get('finger_guides'):
        from .hands import validate_guides
        validate_guides(source['finger_guides'],rig,meshes)
        if json.loads(context.scene.lc_settings.hand_guide_data or '{}')!=source['finger_guides']:raise ValueError('Hand guides changed during inference; refine hands again')
    if any(o.get('lc_placement_job')==source['job_id'] for o in context.scene.objects):raise ValueError('Placement job already applied')
    if source.get('hands_only'):
        from .hands import apply_copy
        return apply_copy(context,folder,source,result,rig,meshes)
    scale=source['scene_unit_scale'];convert=lambda p:Vector((p[0]/scale,-p[2]/scale,p[1]/scale))
    heads={n:convert(p) for n,p in zip(result['names'],result['heads'])}
    tails={n:convert(p) for n,p in zip(result['names'],result['tails'])}
    locks={skeleton.canonical_name(n):value for n,value in source['locks'].items()}
    if source.get('landmarks'):
        from .landmarks import constrain
        constrain(heads,tails,source['landmarks'],locks)
    for n,value in locks.items():
        if n in heads:heads[n]=Vector(value['head']);tails[n]=Vector(value['tail'])
    for parent,child in [('Hips','Spine'),('Spine','Spine1'),('Spine1','Spine2'),('Spine2','Neck'),('Neck','Head')]+[
        (side+a,side+b) for side in ('Left','Right') for a,b in [('Shoulder','Arm'),('Arm','ForeArm'),('ForeArm','Hand'),('UpLeg','Leg'),('Leg','Foot'),('Foot','ToeBase')]]:
        if parent not in locks:tails[parent]=heads[child].copy()
    if any((tails[n]-heads[n]).length<1e-5 for n in heads):raise ValueError('Joint correction collapsed a bone')
    new=None;collection=None;copies=[]
    selected=list(context.selected_objects);active=context.view_layer.objects.active
    try:
        new=skeleton.create_armature(context,max(.1,(heads['Head'].z-heads['Hips'].z)*2),origin=(0,0,0))
        collection=new.users_collection[0];collection.name='Local Character Joints'
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            for name in heads:
                bone=new.data.edit_bones[name];bone.head=heads[name];bone.tail=tails[name];bone.align_roll(Vector((0,-1,0)))
            root=new.data.edit_bones['Root'];root.head=(heads['Hips'].x,heads['Hips'].y,min((o.matrix_world@v.co).z for o in meshes for v in o.data.vertices))
            root.tail=root.head+Vector((0,0,max(.01,(heads['Head'].z-heads['Hips'].z)*.1)))
        finally:bpy.ops.object.mode_set(mode='OBJECT')
        for original in meshes:
            mesh=original.copy();mesh.data=original.data.copy();copies.append(mesh);collection.objects.link(mesh)
            mesh.name=original.name+'_Joints';mesh.parent=new;mesh.matrix_parent_inverse=Matrix.Identity(4);mesh.matrix_world=original.matrix_world.copy()
            old_bones=set(rig.data.bones.keys()) if rig else set()
            for modifier in list(mesh.modifiers):
                if modifier.type=='ARMATURE':mesh.modifiers.remove(modifier)
            if source.get('preserve_weights'):
                modifier=mesh.modifiers.new('Local Character Skin','ARMATURE');modifier.object=new
            else:
                for group in list(mesh.vertex_groups):
                    if group.name in old_bones or skeleton.canonical_name(group.name) in heads:mesh.vertex_groups.remove(group)
            mesh['lc_placement_job']=source['job_id']
            mesh['lc_source_mesh']=original.get('lc_source_mesh',original.name)
        for name in locks:
            if name in new.data.bones:new.data.bones[name]['lc_joint_locked']=True
        for name in source.get('landmarks',{}).get('points',{}):new.data.bones[name]['lc_joint_locked']=True
        new['lc_placement']='mia_original_joint_proposal';new['lc_placement_job']=source['job_id']
        if source.get('preserve_weights'):new['lc_skinning']=rig.get('lc_skinning','accepted_weights')
        new['lc_joint_review']='Review ankle depth, toe direction, hip width, shoulders and fingers before accepting joints'
        new['lc_hand_report']=json.dumps(result.get('hand_report',[]))
        skinning._state(folder,'applied',collection=collection.name)
    except Exception:
        for obj in [*copies,*([new] if new else [])]:
            block=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if block.users==0:(bpy.data.armatures if isinstance(block,bpy.types.Armature) else bpy.data.meshes).remove(block)
        if collection:bpy.data.collections.remove(collection)
        for obj in context.selected_objects:obj.select_set(False)
        for obj in selected:obj.select_set(True)
        context.view_layer.objects.active=active
        raise
    return collection,new,copies,result
