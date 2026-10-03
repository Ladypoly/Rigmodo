"""Optional helper weighting, anatomical swing/twist, source preservation and FBX."""
import importlib.util
import json
import math
from pathlib import Path
import sys
import bpy
import numpy as np
from mathutils import Quaternion,Vector

extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import skeleton,regions,skinning,twists,exporter
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.context.scene.render.fps=24
rig=skeleton.create_armature(bpy.context,1.75,55)
points=[];faces=[]
for side in ('Left','Right'):
    bone=rig.data.bones[side+'ForeArm'];start=len(points)
    for level in range(9):
        for i in range(12):
            angle=i*math.tau/12;local=Vector((math.cos(angle)*.035,bone.length*level/8,math.sin(angle)*.035))
            points.append(tuple(bone.matrix_local@local))
    for level in range(8):
        for i in range(12):
            a=start+level*12+i;b=start+level*12+(i+1)%12;faces.append((a,b,b+12,a+12))
block=bpy.data.meshes.new('ForearmSleeves');block.from_pydata(points,[],faces);block.update()
mesh=bpy.data.objects.new('ForearmSleeves',block);bpy.context.scene.collection.objects.link(mesh);mesh.parent=rig
mesh.modifiers.new('Skin','ARMATURE').object=rig
for side,span in [('Left',range(108)),('Right',range(108,216))]:
    mesh.vertex_groups.new(name=side+'ForeArm').add(list(span),.9,'REPLACE')
    hand=mesh.vertex_groups.new(name=side+'Hand');hand.add(list(span),.1,'REPLACE');hand.lock_weight=True
regions.protect(mesh,[9]);regions.mark(mesh,[0,1,2],'RIGID','LeftForeArm')
rig.animation_data_create();action=bpy.data.actions.new('AxialTwist');rig.animation_data.action=action
for frame,angle in [(1,0),(73,140)]:
    for side in ('Left','Right'):
        forearm=rig.pose.bones[side+'ForeArm'];forearm.rotation_mode='QUATERNION'
        forearm.rotation_quaternion=Quaternion((0,1,0),math.radians(angle))
        forearm.keyframe_insert('rotation_quaternion',frame=frame)
        upper=rig.pose.bones[side+'Arm'];upper.rotation_mode='QUATERNION';upper.rotation_quaternion=Quaternion((1,0,0),math.radians(angle*.2))
        upper.keyframe_insert('rotation_quaternion',frame=frame)
    rig.pose.bones['Root'].location=(angle/140*.4,0,0);rig.pose.bones['Root'].keyframe_insert('location',frame=frame)
action['lc_explicit_root_motion']=True
bpy.context.scene.frame_set(1)
before=skinning._digest(rig,[mesh]);source_keys=[(c.data_path,c.array_index,[(tuple(k.co),k.interpolation) for k in c.keyframe_points]) for l in action.layers for s in l.strips for b in s.channelbags for c in b.fcurves]
original=regions.dense_weights(mesh,[b.name for b in rig.data.bones if b.use_deform])
collection,target,copies=twists.add(bpy.context,rig,[mesh])
assert len(target.data.bones)==55 and target.animation_data.action!=action
assert before==skinning._digest(rig,[mesh])
for bone in rig.data.bones:assert target.data.bones[bone.name].matrix_local==bone.matrix_local
names=[b.name for b in target.data.bones if b.use_deform];field=regions.dense_weights(copies[0],names)
assert abs(field.sum(axis=1)-1).max()<1e-5
for side in ('Left','Right'):
    assert np.array_equal(field[:,names.index(side+'Hand')],regions.dense_weights(mesh,names)[:,names.index(side+'Hand')])
assert np.array_equal(field[9],regions.dense_weights(mesh,names)[9])
assert not field[:3,names.index('LeftForeArmTwist')].any()
maximum=0.
for frame in (1,13,25,49,73):
    bpy.context.scene.frame_set(frame)
    for side in ('Left','Right'):
        source=target.pose.bones[side+'ForeArm'];helper=target.pose.bones[side+'ForeArmTwist']
        expected=Quaternion((0,1,0),source.rotation_quaternion.angle*.5)
        error=helper.rotation_quaternion.rotation_difference(expected).angle;maximum=max(maximum,error)
assert maximum<.001,maximum
assert source_keys==[(c.data_path,c.array_index,[(tuple(k.co),k.interpolation) for k in c.keyframe_points]) for l in action.layers for s in l.strips for b in s.channelbags for c in b.fcurves]
generic=exporter.export_bundle(bpy.context,target,copies,str(output),'TwistGeneric',profile='GENERIC',include_action=True)
human=exporter.export_bundle(bpy.context,target,copies,str(output),'TwistHuman',include_action=True)
for copy in copies:exporter._prune(copy,target)
for bundle in (generic,human):motion_reference.write(target,copies,bundle)
summary=dict(passed=True,bones=55,original_data_preserved=True,protected_weights_exact=True,locked_weights_exact=True,
             maximum_helper_rotation_error_radians=maximum,bundles=[str(generic),str(human)])
(output/'results.json').write_text(json.dumps(summary,indent=2));print('TWIST_ACCEPTANCE',json.dumps(summary))
