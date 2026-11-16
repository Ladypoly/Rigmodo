# SPDX-License-Identifier: GPL-3.0-or-later
"""Publish complete Action assets in an isolated Blender worker."""
import os,re,uuid,tempfile
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix
from . import motion_store,motion_retarget


def selected_keys(context,root):
    selected=getattr(context,'selected_assets',[]) or [getattr(context,'asset',None)]
    keys=[]
    for asset in selected:
        if not asset or asset.id_type!='ACTION':continue
        path=Path(asset.full_library_path).resolve()
        if path.parent==(Path(root)/'Assets').resolve() and re.fullmatch('[a-f0-9]{32}',path.stem):keys.append(path.stem)
    return keys


def selected_key(context,root):
    asset=getattr(context,'asset',None)
    if not asset or asset.id_type!='ACTION':return None
    path=Path(asset.full_library_path).resolve()
    if path.parent!=(Path(root)/'Assets').resolve() or not re.fullmatch('[a-f0-9]{32}',path.stem):return None
    return path.stem


def source_rig(context,data,name='Motion source'):
    """Reconstruct a data-only motion skeleton; never require an avatar mesh."""
    from . import rig_mapping
    motion_store.validate(data)
    if context.mode!='OBJECT':raise ValueError('Return to Object Mode before creating a source skeleton')
    armature=bpy.data.armatures.new(name);rig=bpy.data.objects.new(name,armature)
    context.scene.collection.objects.link(rig)
    for obj in context.selected_objects:obj.select_set(False)
    context.view_layer.objects.active=rig;rig.select_set(True)
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        for i,name in enumerate(data['names']):
            bone=armature.edit_bones.new(str(name));children=np.flatnonzero(data['parents']==i)
            length=float(data['lengths'][i]) if 'lengths' in data else min((np.linalg.norm(data['rest'][j,:3,3]-data['rest'][i,:3,3]) for j in children),default=.08)
            bone.length=max(length,.001);bone.matrix=Matrix(data['rest'][i].tolist())
            role=str(data.get('roles',data['names'])[i]);bone.use_deform=rig_mapping.canonical(role)!='Root'
        for i,parent in enumerate(data['parents']):
            if parent>=0:armature.edit_bones[str(data['names'][i])].parent=armature.edit_bones[str(data['names'][parent])]
        bpy.ops.object.mode_set(mode='OBJECT')
        overrides={str(role):str(name) for role,name in zip(data.get('roles',[]),data['names']) if str(role) in rig_mapping.ROLES}
        if overrides:rig['lc_humanoid_roles']=__import__('json').dumps(overrides)
        for name,label in zip(data['names'],data['labels']):
            if label:
                bone=armature.bones[str(name)]
                if hasattr(bone,'lc_unimate_label'):bone.lc_unimate_label=str(label)
                else:bone['lc_unimate_label']=str(label)
        return rig
    except Exception:
        if rig.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.data.objects.remove(rig,do_unlink=True)
        if armature.users==0:bpy.data.armatures.remove(armature)
        raise


def publish(root,entry):
    root=Path(root);folder=root/'Assets';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(entry['id']+'.blend')
    if path.is_file():return
    data=motion_store.read(root,entry['id'])
    rig=source_rig(bpy.context,data);armature=rig.data
    action=None
    try:
        # Imported glTF rest matrices can contain tiny shear; Blender normalizes reconstructed bones.
        data=dict(data,rest=np.array([rig.data.bones[str(n)].matrix_local for n in data['names']],dtype=np.float32))
        action=motion_retarget.apply(bpy.context,rig,data,entry['name'],loop=entry['loop'])
        if hasattr(action,'lc_clip_owner'):action.lc_clip_owner=None
        if hasattr(action,'lc_contact_source'):action.lc_contact_source=None
        action['lc_library_id']=entry['id'];action['lc_library_source']=entry['source'];action['lc_library_license']=entry['license'];action.asset_mark()
        meta=action.asset_data;meta.author=entry['source'];meta.license=entry['license']
        meta.description=f"{entry['duration']:.2f} s · {entry['bones']} bones. Select as a source in Rigmodo → Retarget."
        meta.catalog_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'rigmodo/motions/'+entry['family']))
        for tag in ['Rigmodo',entry['family'],*re.split(r'[,\s]+',entry.get('tags',''))]:
            if tag:meta.tags.new(tag,skip_if_exists=True)
        preview=motion_store.clip_dir(root,entry['id'])/'preview.png'
        if preview.is_file():
            with bpy.context.temp_override(id=action):bpy.ops.ed.lib_id_load_custom_preview(filepath=str(preview))
        fd,filename=tempfile.mkstemp(prefix='.'+entry['id'],suffix='.pending',dir=folder);os.close(fd)
        try:
            bpy.data.libraries.write(filename,{action},fake_user=True,compress=True)
            os.replace(filename,path)
        finally:
            if os.path.exists(filename):os.unlink(filename)
    finally:
        if rig.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        bpy.data.objects.remove(rig,do_unlink=True);bpy.data.armatures.remove(armature)
        if action:bpy.data.actions.remove(action)


def publish_all(root,progress=None):
    root=Path(root);entries=motion_store.catalog(root)['clips'];folder=root/'Assets';folder.mkdir(parents=True,exist_ok=True)
    for i,entry in enumerate(entries):
        if progress:progress(i,len(entries),entry['name'])
        publish(root,entry)
    # Preserve catalogs users create in Blender; only append missing Rigmodo families.
    path=folder/'blender_assets.cats.txt'
    with motion_store.locked(root):
        text=path.read_text(encoding='utf-8') if path.exists() else '# Rigmodo motion catalogs\nVERSION 1\n'
        for family in sorted({e['family'] for e in entries}):
            key=str(uuid.uuid5(uuid.NAMESPACE_URL,'rigmodo/motions/'+family))
            if key not in text:text+=f'{key}:Rigmodo/{family}:{family}\n'
        temporary=path.with_suffix('.pending');temporary.write_text(text,encoding='utf-8');os.replace(temporary,path)
    return len(entries)
