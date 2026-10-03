# SPDX-License-Identifier: GPL-3.0-or-later
"""Artist-placed optional bones; accepted core and paint remain unchanged."""
import json
import math
import re
import bpy
from mathutils import Vector
from . import skeleton,regions,weight_copy

def add(context,rig,meshes,kind,parent_name='',socket_name='Socket'):
    if context.mode!='OBJECT':raise ValueError('Return to Object Mode')
    mapping={skeleton.canonical_name(b.name):b.name for b in rig.data.bones}
    if kind not in {'LEFT_EYE','RIGHT_EYE','JAW','SOCKET'}:raise ValueError('Unknown optional bone')
    name={'LEFT_EYE':'LeftEye','RIGHT_EYE':'RightEye','JAW':'Jaw'}.get(kind,socket_name.strip())
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}',name):raise ValueError('Use a simple, unique bone name of at most 64 characters')
    if name in rig.data.bones or skeleton.canonical_name(name) in mapping:raise ValueError('This optional bone already exists')
    parent=parent_name if kind=='SOCKET' else mapping.get('Head')
    if parent not in rig.data.bones:raise ValueError('Choose an existing parent bone')
    cursor=rig.matrix_world.inverted()@context.scene.cursor.location
    if not all(math.isfinite(v) for v in cursor):raise ValueError('Cursor position must be finite')
    # Facing direction comes from accepted anatomy, not the rig object's rotation.
    left=rig.data.bones[mapping['LeftArm']].head_local-rig.data.bones[mapping['RightArm']].head_local
    up=rig.data.bones[mapping['Head']].head_local-rig.data.bones[mapping['Hips']].head_local
    forward=left.cross(up).normalized()
    length=max(up.length*.035,1e-4)
    names,fields,_=regions.prepare_fields(context,rig,meshes,'SURFACE')
    copied=weight_copy.create(context,rig,meshes,names,[f['original'] for f in fields],label=name,method=rig.get('lc_skinning','accepted_weights'))
    collection,target,copies=copied
    try:
        for o in context.selected_objects:o.select_set(False)
        target.select_set(True);context.view_layer.objects.active=target;bpy.ops.object.mode_set(mode='EDIT')
        try:
            bone=target.data.edit_bones.new(name);bone.parent=target.data.edit_bones[parent]
            bone.head=cursor;bone.tail=cursor+forward*length;bone.use_deform=kind!='SOCKET';bone.use_connect=False
            bone.align_roll(up.normalized())
        finally:bpy.ops.object.mode_set(mode='OBJECT')
        if kind!='SOCKET':
            for mesh in copies:mesh.vertex_groups.new(name=name)
        specs=json.loads(rig.get('lc_optional_bones','[]'));specs.append(dict(name=name,kind=kind,parent=parent))
        target['lc_optional_bones']=json.dumps(specs)
        for mesh in copies:mesh.select_set(True)
        return copied
    except Exception:
        for obj in [target,*copies]:
            data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if data.users==0:(bpy.data.armatures if isinstance(data,bpy.types.Armature) else bpy.data.meshes).remove(data)
        bpy.data.collections.remove(collection);raise
