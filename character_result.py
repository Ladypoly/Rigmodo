# SPDX-License-Identifier: GPL-3.0-or-later
"""Commit successful weight results to stable objects; purge only owned copies."""
import bpy,json
from pathlib import Path
from mathutils import Matrix


def metadata(obj):
    return {key:value for key,value in obj.id_properties_ensure().to_dict().items() if key.startswith('lc_')}


def dispose(objects):
    objects=list(dict.fromkeys(objects));blocks=[];collections=set()
    for obj in objects:
        blocks.append(obj.data);collections.update(obj.users_collection)
        bpy.data.objects.remove(obj,do_unlink=True)
    for block in dict.fromkeys(blocks):
        if block.users==0:
            database=bpy.data.armatures if isinstance(block,bpy.types.Armature) else bpy.data.meshes
            database.remove(block)
    for collection in collections:
        if collection.name.startswith(('Rigmodo','Local Character')) and not collection.objects and not collection.children:bpy.data.collections.remove(collection)


def history(context,rig,meshes):
    """Find hidden historical inputs by recorded job ID AND live object pointer."""
    candidates=set();settings=context.scene.lc_settings;current={rig,*meshes}
    records=(('motion_job',('lc_motion_job',),'request.json'),('region_job',('lc_region_job',),'request.json'),
        ('skin_job',('lc_skin_job','lc_parent_skin_job'),'request.json'),('placement_job',('lc_placement_job',),'source.json'))
    for setting,tags,filename in records:
        folder=getattr(settings,setting)
        if not folder:continue
        try:request=json.loads((Path(folder)/filename).read_text())
        except (OSError,ValueError):continue
        if not request.get('job_id') or not any(rig.get(tag)==request['job_id'] for tag in tags):continue
        entries=[dict(name=request.get('rig'),pointer=request.get('rig_pointer')),*request.get('meshes',[])]
        for entry in entries:
            obj=bpy.data.objects.get(entry.get('name') or '')
            if obj and obj not in current and str(obj.as_pointer())==entry.get('pointer') and obj.name in context.scene.objects and obj.hide_get():candidates.add(obj)
    if any(not obj.is_editable or any(scene!=context.scene for scene in obj.users_scene) or any(child not in candidates for child in obj.children) for obj in candidates):
        raise ValueError('Old versions have shared or attached objects; retain them for manual review')
    for obj in bpy.data.objects:
        if obj in candidates:continue
        if any(modifier.type=='ARMATURE' and modifier.object in candidates for modifier in obj.modifiers):
            raise ValueError('Other geometry still uses an old armature; retain it for manual review')
    return sorted(candidates,key=lambda obj:obj.name)


def clean_history(context,rig,meshes):
    objects=history(context,rig,meshes);names=[obj.name for obj in objects];dispose(objects)
    if rig.name.startswith('LC_Humanoid'):
        rig.name='Rigmodo_Rig';rig.data.name=rig.name
    for collection in rig.users_collection:
        if collection.name.startswith('Local Character') and set(collection.objects)<={rig,*meshes}:
            collection.name='Rigmodo'+collection.name[len('Local Character'):]
    for mesh in meshes:
        source=mesh.get('lc_source_mesh')
        if source and source in names and source not in bpy.data.objects:
            mesh.name=source
            if mesh.data.users==1:mesh.data.name=mesh.name
    return names


def skin(context,original,meshes,result,result_meshes,owned=None):
    """Keep source object identities, names, rig data and Actions unchanged."""
    if context.mode!='OBJECT' or len(meshes)!=len(result_meshes):raise ValueError('Skin result scope changed')
    if any(not obj.is_editable for obj in [original,*meshes]):raise ValueError('Use editable character objects before applying skinning')
    if original==result or set(original.data.bones.keys())!=set(result.data.bones.keys()):raise ValueError('Skin result must retain the accepted rig')
    for bone in original.data.bones:
        other=result.data.bones[bone.name]
        if max(abs(v) for row in bone.matrix_local-other.matrix_local for v in row)>1e-6 or (bone.tail_local-other.tail_local).length>1e-6 or bone.use_deform!=other.use_deform or (bone.parent.name if bone.parent else None)!=(other.parent.name if other.parent else None):
            raise ValueError('Skinning changed accepted joints; retain the review result')
    owned=list(dict.fromkeys(owned or [result,*result_meshes]));owned_set=set(owned)
    if set([original,*meshes])&owned_set:raise ValueError('Source objects cannot be temporary results')
    if any(child not in owned_set for obj in owned for child in obj.children):raise ValueError('A temporary result has attached objects; retain review copies')
    if any(scene!=context.scene for obj in owned for scene in obj.users_scene):raise ValueError('A temporary result is shared with another scene')
    for source,target in zip(meshes,result_meshes):
        if source==target or max(abs(v) for row in source.matrix_world-target.matrix_world for v in row)>1e-5 or len(source.data.vertices)!=len(target.data.vertices) or [tuple(p.vertices) for p in source.data.polygons]!=[tuple(p.vertices) for p in target.data.polygons]:
            raise ValueError('Skin result geometry correspondence changed')
    snapshots=[];rig_metadata=metadata(original);scratch=bpy.data.meshes.new('Rigmodo Commit')
    def groups(obj,rows):
        obj.data=scratch
        obj.vertex_groups.clear()
        for name,locked in rows:obj.vertex_groups.new(name=name).lock_weight=locked
    try:
        for source,target in zip(meshes,result_meshes):
            snapshot=dict(obj=source,data=source.data,data_pointer=source.data.as_pointer(),data_name=source.data.name,groups=[(g.name,g.lock_weight) for g in source.vertex_groups],active=source.vertex_groups.active_index,
                parent=source.parent,inverse=source.matrix_parent_inverse.copy(),world=source.matrix_world.copy(),metadata=metadata(source),added=[])
            snapshots.append(snapshot)
            groups(source,[(g.name,g.lock_weight) for g in target.vertex_groups]);source.data=target.data
            source.vertex_groups.active_index=min(snapshot['active'],max(0,len(source.vertex_groups)-1))
            source.parent=original;source.matrix_parent_inverse=Matrix.Identity(4);source.matrix_world=snapshot['world']
            if not any(m.type=='ARMATURE' for m in source.modifiers):
                modifier=source.modifiers.new('Rigmodo Skin','ARMATURE');modifier.object=original;snapshot['added'].append(modifier)
            for key,value in metadata(target).items():source[key]=value
        for key,value in metadata(result).items():original[key]=value
        # AUTO refinement moves the AI marker to lc_parent_skin_job. Keep the
        # consumed job marker on the stable rig for duplicate-apply rejection.
        skin_job=result.get('lc_skin_job') or result.get('lc_parent_skin_job')
        if skin_job:original['lc_skin_job']=skin_job
        context.view_layer.update()
    except Exception:
        for snapshot in reversed(snapshots):
            source=snapshot['obj'];groups(source,snapshot['groups']);source.data=snapshot['data'];source.vertex_groups.active_index=snapshot['active']
            source.parent=snapshot['parent'];source.matrix_parent_inverse=snapshot['inverse'];source.matrix_world=snapshot['world']
            for modifier in snapshot['added']:source.modifiers.remove(modifier)
            for key in metadata(source):del source[key]
            for key,value in snapshot['metadata'].items():source[key]=value
        for key in metadata(original):del original[key]
        for key,value in rig_metadata.items():original[key]=value
        raise
    finally:
        if scratch.users==0:bpy.data.meshes.remove(scratch)
    dispose(owned)
    removed=set()
    for snapshot in snapshots:
        old=snapshot['data'];current=snapshot['obj'].data
        if snapshot['data_pointer'] not in removed and old.users==0:
            bpy.data.meshes.remove(old);removed.add(snapshot['data_pointer'])
        current.name=snapshot['data_name']
    for obj in [original,*meshes]:obj.hide_set(False)
    return original,meshes
