# SPDX-License-Identifier: GPL-3.0-or-later
"""UniRig creature proposals using the existing geometry transport and job owner."""
import json,math,os,subprocess,tempfile,time
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix,Vector
from . import placement,skinning

def cache():return skinning.provider_cache().parent/'unirig-69ee59d'
def is_creature(rig):return bool(rig and rig.get('lc_rig_type')=='CREATURE')
def ready(provider):
    try:
        root=Path(bpy.path.abspath(provider));record=json.loads((root/'installation.json').read_text())
        return Path(record['checkpoint']).is_file() and (root/'python/transformers').is_dir()
    except (OSError,ValueError,KeyError,TypeError):return False

def prepare(context,meshes,rig=None,parent=None,provider=None,seed=101):
    # Reuse validated world-metre geometry export; this is a fresh topology proposal.
    folder=placement.prepare(context,meshes,None,parent=parent)
    request=dict(schema_version=1,provider='unirig',provider_cache=str(Path(provider or cache()).resolve()),
        seed=seed,input_sha256=placement.sha(folder/'input.npz'))
    source=json.loads((folder/'source.json').read_text())
    source.update(rig=rig.name if rig else None,rig_pointer=str(rig.as_pointer()) if rig else None,
        source_digest=skinning._digest(rig,meshes))
    (folder/'request.json').write_text(json.dumps(request,indent=2))
    source['request_sha256']=placement.sha(folder/'request.json')
    (folder/'source.json').write_text(json.dumps(source,indent=2));return folder

def start(folder,python):
    if skinning._jobs:raise ValueError('Wait for the current local job or cancel it')
    folder=Path(folder).resolve();request=json.loads((folder/'request.json').read_text())
    provider=Path(request['provider_cache'])
    if request.get('provider')!='unirig' or skinning.poll(folder)['status']!='prepared':raise ValueError('Prepare a new creature job')
    if not ready(str(provider)):raise ValueError('Install Creature Rigging in Extension Settings → Setup')
    if not Path(python).is_file():raise ValueError('Install the MIA Python runtime first; UniRig reuses its PyTorch')
    log=(folder/'worker.log').open('wb')
    try:
        process=subprocess.Popen([str(python),'-I',str(Path(__file__).with_name('unirig_worker.py')),str(folder)],
            stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except Exception:log.close();raise
    skinning._jobs[str(folder)]=dict(process=process,log=log,started=time.monotonic(),finish=finish,phase='Generating creature joints · UniRig')
    try:skinning._state(folder,'running',pid=process.pid)
    except OSError:skinning.cancel(folder);raise
    return process.pid

def output(folder):
    folder=Path(folder);path=folder/'output.json'
    if not path.is_file() or path.stat().st_size>512*1024:raise ValueError('Missing or oversized creature skeleton')
    result=json.loads(path.read_text())
    if not isinstance(result,dict) or not isinstance(result.get('parents'),list):raise ValueError('Invalid creature skeleton structure')
    heads=np.asarray(result['heads'],dtype=np.float64);parents=result['parents']
    if result.get('provider')!='unirig' or result.get('coordinate_space')!='world_meters_gltf_y_up':raise ValueError('Wrong creature result protocol')
    if not 2<=len(parents)<=256 or heads.shape!=(len(parents),3) or not np.isfinite(heads).all():raise ValueError('Invalid creature joints')
    if any(type(p)is not int or p< -1 or p>=len(parents) for p in parents) or parents.count(-1)!=1:raise ValueError('Creature skeleton must have one root')
    for index in range(len(parents)):
        visited=set();p=index
        while p!=-1:
            if p in visited:raise ValueError('Creature skeleton contains a cycle')
            visited.add(p);p=parents[p]
    if result.get('tails') is not None:
        tails=np.asarray(result['tails'],dtype=np.float64)
        if tails.shape!=heads.shape or not np.isfinite(tails).all():raise ValueError('Invalid creature bone tails')
    if result.get('request_sha256')!=placement.sha(folder/'request.json'):raise ValueError('Creature request changed')
    with np.load(folder/'input.npz',allow_pickle=False) as data:vertices=data['vertices']
    center=(vertices.min(0)+vertices.max(0))*.5;extent=float(np.ptp(vertices,axis=0).max())
    if np.max(np.abs(heads-center))>extent*.6:raise ValueError('Creature joints exceed the input normalization cube')
    return result

def finish(folder):
    result=output(folder)
    (Path(folder)/'result.json').write_text(json.dumps(dict(output_sha256=placement.sha(Path(folder)/'output.json'),
        joints=len(result['parents']),elapsed_seconds=result['elapsed_seconds'],peak_gpu_bytes=result['peak_gpu_bytes'])))

def apply(context,folder):
    folder=Path(folder).resolve()
    if context.mode!='OBJECT' or skinning.poll(folder)['status']!='complete':raise ValueError('Creature job is not ready')
    source=json.loads((folder/'source.json').read_text());request=json.loads((folder/'request.json').read_text())
    if placement.sha(folder/'request.json')!=source['request_sha256'] or placement.sha(folder/'input.npz')!=request['input_sha256']:
        raise ValueError('Creature request or input changed')
    if placement.sha(folder/'output.json')!=json.loads((folder/'result.json').read_text())['output_sha256']:raise ValueError('Creature result changed')
    result=output(folder);rig=bpy.data.objects.get(source['rig']) if source['rig'] else None
    meshes=[bpy.data.objects.get(entry['name']) for entry in source['meshes']]
    if any(not mesh or str(mesh.as_pointer())!=entry['pointer'] or mesh.name not in context.scene.objects for mesh,entry in zip(meshes,source['meshes'])):
        raise ValueError('Creature source meshes no longer match')
    if source['rig'] and (not rig or str(rig.as_pointer())!=source['rig_pointer'] or rig.name not in context.scene.objects):raise ValueError('Creature source rig no longer matches')
    scale=source['scene_unit_scale']
    if scale!=context.scene.unit_settings.scale_length or skinning._digest(rig,meshes)!=source['source_digest']:
        raise ValueError('Source geometry or rig changed during creature inference')
    if any(obj.get('lc_creature_job')==source['job_id'] for obj in context.scene.objects):raise ValueError('Creature result already applied')
    heads=[Vector((p[0]/scale,-p[2]/scale,p[1]/scale)) for p in result['heads']];parents=result['parents']
    extent=max((max(h[i] for h in heads)-min(h[i] for h in heads)) for i in range(3))
    if extent<1e-5:raise ValueError('Creature skeleton collapsed to one point')
    tails=[]
    for index,head in enumerate(heads):
        children=[heads[n] for n,p in enumerate(parents) if p==index and (heads[n]-head).length>1e-6]
        if result.get('tails') is not None:
            p=result['tails'][index];tail=Vector((p[0]/scale,-p[2]/scale,p[1]/scale))
        elif children:tail=max(children,key=lambda p:(p-head).length).copy()
        else:
            direction=head-heads[parents[index]] if parents[index]>=0 else Vector((0,0,1))
            if direction.length<1e-6:direction=Vector((0,0,1))
            tail=head+direction.normalized()*max(extent*.005,min(direction.length*.25,extent*.05))
        if (tail-head).length<1e-6:tail=head+Vector((0,0,extent*.005))
        tails.append(tail)
    selected=list(context.selected_objects);active=context.active_object
    collection=bpy.data.collections.new('Rigmodo Creature');data=bpy.data.armatures.new('Rigmodo_Creature_Rig')
    target=bpy.data.objects.new('Rigmodo_Creature_Rig',data);created=[target];blocks=[data]
    try:
        context.scene.collection.children.link(collection);collection.objects.link(target)
        for obj in selected:obj.select_set(False)
        target.select_set(True);context.view_layer.objects.active=target;bpy.ops.object.mode_set(mode='EDIT')
        root=data.edit_bones.new('Root');root.head=(0,0,0);root.tail=(0,0,extent*.05);root.use_deform=False
        bones=[]
        for n,(head,tail) in enumerate(zip(heads,tails)):
            bone=data.edit_bones.new(f'Creature_{n:03}');bone.head=head;bone.tail=tail;bones.append(bone)
        for n,parent in enumerate(parents):bones[n].parent=bones[parent] if parent>=0 else root
        bpy.ops.object.mode_set(mode='OBJECT');target.show_in_front=True
        for original in meshes:
            mesh=original.copy();mesh.data=original.data.copy();created.append(mesh);blocks.append(mesh.data)
            mesh.name=original.name+'_Creature';collection.objects.link(mesh)
            for modifier in list(mesh.modifiers):
                if modifier.type=='ARMATURE':mesh.modifiers.remove(modifier)
            for group in list(mesh.vertex_groups):
                if rig and group.name in rig.data.bones or group.name in data.bones:mesh.vertex_groups.remove(group)
            mesh.parent=target;mesh.parent_type='OBJECT';mesh.matrix_parent_inverse=Matrix.Identity(4);mesh.matrix_world=original.matrix_world.copy()
            mesh.modifiers.new('Rigmodo Skin','ARMATURE').object=target
            mesh['lc_source_mesh']=original.get('lc_source_mesh',original.name)
        target['lc_rig_type']='CREATURE';target['lc_placement']='unirig';target['lc_creature_job']=source['job_id']
        skinning._state(folder,'applied',rig=target.name)
    except Exception:
        if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in created:bpy.data.objects.remove(obj,do_unlink=True)
        for block in blocks:
            if block.users==0:(bpy.data.armatures if isinstance(block,bpy.types.Armature) else bpy.data.meshes).remove(block)
        bpy.data.collections.remove(collection)
        for obj in selected:obj.select_set(True)
        context.view_layer.objects.active=active
        raise
    return collection,target,created[1:],result
