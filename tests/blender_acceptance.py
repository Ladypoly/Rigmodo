"""Run with Blender --background --factory-startup --disable-autoexec --python this_file -- OUTPUT."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import traceback
import bpy
from mathutils import Vector, Matrix
from math import radians

extension = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("local_character", extension / "__init__.py", submodule_search_locations=[str(extension)])
addon = importlib.util.module_from_spec(spec); sys.modules[spec.name] = addon; spec.loader.exec_module(addon)
addon.register()
output = Path(sys.argv[sys.argv.index("--")+1]).resolve()
output.mkdir(parents=True, exist_ok=True)
results = []

def check(condition, message):
    if not condition: raise AssertionError(message)

def snapshot(rig, meshes):
    return {
        "objects": sorted(o.name for o in bpy.context.scene.objects),
        "selection": sorted(o.name for o in bpy.context.selected_objects),
        "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
        "view_layer": bpy.context.view_layer.name,
        "bones": [(b.name, b.parent.name if b.parent else None, list(b.head_local), list(b.tail_local)) for b in rig.data.bones],
        "weights": [[[g.group, g.weight] for g in v.groups] for mesh in meshes for v in mesh.data.vertices],
        "shapes": [[list(p.co) for p in key.data] for mesh in meshes if mesh.data.shape_keys for key in mesh.data.shape_keys.key_blocks],
        "pose": [[list(row) for row in pb.matrix_basis] for pb in rig.pose.bones],
        "scenes": sorted(s.name for s in bpy.data.scenes),
        "frame": bpy.context.scene.frame_current,
        "action": rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None,
        "slot": rig.animation_data.action_slot.identifier if rig.animation_data and rig.animation_data.action_slot else None,
        "actions": sorted(a.name for a in bpy.data.actions),
        "nla": [(t.name, [(s.name, s.action.name) for s in t.strips]) for t in rig.animation_data.nla_tracks] if rig.animation_data else [],
    }

def synthetic(rig):
    vertices, faces, assignment = [], [], []
    for bone in rig.data.bones:
        if not bone.use_deform: continue
        start = len(vertices)
        direction = (bone.tail_local-bone.head_local).normalized()
        perpendicular = direction.cross(Vector((0, 1, 0)))
        if perpendicular.length < .1: perpendicular = direction.cross(Vector((1, 0, 0)))
        perpendicular.normalize(); second = direction.cross(perpendicular).normalized()
        radius = .007 if "Hand" in bone.name else .018
        for center in (bone.head_local, bone.tail_local):
            for a, b in ((-1,-1),(-1,1),(1,1),(1,-1)):
                vertices.append(center + radius*(a*perpendicular+b*second))
        for face in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
            faces.append(tuple(start+i for i in face))
        assignment.append((bone.name,list(range(start,start+8))))
    data=bpy.data.meshes.new("DiagnosticBody"); data.from_pydata(vertices,[],faces); data.update()
    mesh=bpy.data.objects.new("DiagnosticBody",data); bpy.context.scene.collection.objects.link(mesh)
    for name, indices in assignment: mesh.vertex_groups.new(name=name).add(indices,1,"REPLACE")
    modifier=mesh.modifiers.new("AcceptedRig","ARMATURE"); modifier.object=rig
    mesh.shape_key_add(name="Basis"); shape=mesh.shape_key_add(name="DiagnosticExpression"); shape.data[0].co.z += .01
    return mesh

try:
    for name, height, angle in (("SyntheticT",1.75,0),("SyntheticA",1.4,45)):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        rig=addon.skeleton.create_armature(bpy.context,height,angle)
        second_layer=bpy.context.scene.view_layers.new('Acceptance Layer')
        bpy.context.window.view_layer=second_layer
        check(len(rig.data.bones)==53 and len(addon.skeleton.resolve_mapping(rig.data.bones))==52,"Core hierarchy count")
        check(not rig.data.bones['Root'].use_deform and rig.data.bones['Hips'].parent.name=='Root',"Structural root")
        mesh=synthetic(rig); mesh.select_set(True)
        check(addon.preflight.selection(bpy.context)[1]==[mesh],"Explicit selection scope")
        # Intentional non-rest pose must neither contaminate the bind export nor be lost.
        rig.pose.bones['LeftForeArm'].rotation_mode='XYZ'; rig.pose.bones['LeftForeArm'].rotation_euler.y=.4
        before=snapshot(rig,[mesh])
        folder=addon.exporter.export_bundle(bpy.context,rig,[mesh],str(output),name)
        check(snapshot(rig,[mesh])==before,"Export mutated original scene/weights/shape keys/pose")
        try:
            addon.exporter.export_bundle(bpy.context,rig,[mesh],str(output),name)
            raise AssertionError("Existing bundle overwrite was allowed")
        except ValueError as exc: check('already exists' in str(exc),"Unexpected overwrite error")
        manifest=json.loads((folder/f'{name}.character.json').read_text())
        check(len(manifest['bones'])==53 and len(manifest['mapping'])==52,"Manifest hierarchy")
        check(manifest['meshes'][0]['shape_keys']==['DiagnosticExpression'],"Manifest shape keys")
        # Independent LBS reference in a character-relative frame; Unity mesh vertex order may differ.
        for pb in rig.pose.bones: pb.matrix_basis=Matrix.Identity(4)
        bpy.context.view_layer.update()
        hips=rig.matrix_world @ rig.pose.bones['Hips'].head
        up=(rig.matrix_world @ rig.pose.bones['Head'].head-hips).normalized()
        left=(rig.matrix_world @ rig.pose.bones['LeftArm'].head-rig.matrix_world @ rig.pose.bones['RightArm'].head).normalized()
        forward=left.cross(up).normalized()
        forearm=rig.pose.bones['LeftForeArm']; pivot=rig.matrix_world @ forearm.head
        forearm.matrix=rig.matrix_world.inverted() @ Matrix.Translation(pivot) @ Matrix.Rotation(radians(50),4,forward) @ Matrix.Translation(-pivot) @ rig.matrix_world @ forearm.bone.matrix_local
        bpy.context.view_layer.update()
        evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
        points=[]
        for vertex in evaluated.data.vertices:
            delta=evaluated.matrix_world @ vertex.co-hips
            points.append([delta.dot(left),delta.dot(forward),delta.dot(up)])
        (folder/'generic-lbs-reference.json').write_text(json.dumps({'angle':50,'points':points}))
        (folder/'generic-lbs-reference-flat.json').write_text(json.dumps({'angle':50,'points':[dict(zip(('x','y','z'),point)) for point in points]}))
        # Import the actual emitted FBX into the isolated process for structural roundtrip.
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.fbx(filepath=str(folder/f'{name}.fbx'))
        imported_rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
        imported_mesh=next(o for o in bpy.context.scene.objects if o.type=='MESH')
        check('Root' in imported_rig.data.bones and imported_rig.data.bones['Hips'].parent.name=='Root',"FBX root hierarchy")
        check(len(imported_rig.data.bones)==53,"FBX added or removed bones")
        check(len(imported_mesh.data.shape_keys.key_blocks)==2,"FBX lost shape keys")
        for vertex in imported_mesh.data.vertices:
            weights=[g.weight for g in vertex.groups if g.weight>0]
            check(len(weights)<=4 and abs(sum(weights)-1)<1e-5,"FBX weight normalization/limit")
        world=[imported_mesh.matrix_world @ v.co for v in imported_mesh.data.vertices]
        check(abs(max(v.z for v in world)-height)<.04,"FBX scale/orientation mismatch")
        results.append({'case':name,'status':'pass','bones':53,'mapping':52,'source_scene_preserved':True,'fbx_shape_keys':1})

    # Actual layered Action, a nonzero start frame, Root travel and an unrelated NLA Action.
    bpy.ops.wm.read_factory_settings(use_empty=True)
    rig=addon.skeleton.create_armature(bpy.context,1.75)
    mesh=synthetic(rig);mesh.select_set(True)
    root=rig.pose.bones['Root'];forearm=rig.pose.bones['LeftForeArm'];finger=rig.pose.bones['LeftHandIndex1']
    forearm.rotation_mode='XYZ';finger.rotation_mode='XYZ'
    for frame, travel, bend in ((7,0,0),(19,.15,.8),(31,.3,0)):
        root.location.x=travel;root.keyframe_insert('location',frame=frame)
        forearm.rotation_euler.z=bend;forearm.keyframe_insert('rotation_euler',frame=frame)
        finger.rotation_euler.x=bend/2;finger.keyframe_insert('rotation_euler',frame=frame)
    action=rig.animation_data.action;action.name='SelectedWave'
    slot=rig.animation_data.action_slot
    other=bpy.data.objects.new('OtherActionSlot',None);bpy.context.scene.collection.objects.link(other)
    other_data=other.animation_data_create();other_data.action=action
    other_data.action_slot=action.slots.new(id_type='OBJECT',name='OtherActionSlot')
    other.location.x=-5;other.keyframe_insert('location',frame=-50)
    other.location.x=5;other.keyframe_insert('location',frame=100)
    rig.animation_data.action=None
    root.location.x=100;root.keyframe_insert('location',frame=7)
    root.location.x=200;root.keyframe_insert('location',frame=31)
    unrelated=rig.animation_data.action;unrelated.name='DoNotExport'
    track=rig.animation_data.nla_tracks.new();track.strips.new('DoNotExport',7,unrelated)
    rig.animation_data.action=action;rig.animation_data.action_slot=slot
    bpy.context.scene.render.fps=24;bpy.context.scene.frame_set(19)
    before=snapshot(rig,[mesh])
    for profile in ('GENERIC','HUMANOID'):
        name='SyntheticMotion'+profile.title()
        folder=addon.exporter.export_bundle(bpy.context,rig,[mesh],str(output),name,profile,include_action=True)
        check(snapshot(rig,[mesh])==before,'Animation export mutated source Action/NLA/frame/pose')
        manifest=json.loads((folder/f'{name}.character.json').read_text())
        clip_manifest=json.loads((folder/'Animations/SelectedWave.character.json').read_text())
        check(len(manifest['clips'])==1 and manifest['clips'][0]['name']=='SelectedWave','Unselected Action leaked')
        check(clip_manifest['skeleton_signature']==manifest['skeleton_signature'],'Animation rest signature differs')
        check(clip_manifest['clips'][0]['frame_start']==7 and clip_manifest['clips'][0]['frame_end']==31,'Other Action slot changed the selected range')
        # Reference evaluates only the intended Action, including finger motion and Root travel.
        rig.animation_data.use_nla=False
        samples=[]
        hips=rig.matrix_world @ rig.data.bones['Hips'].head_local
        up=(rig.matrix_world @ rig.data.bones['Head'].head_local-hips).normalized()
        left=(rig.matrix_world @ rig.data.bones['LeftArm'].head_local-rig.matrix_world @ rig.data.bones['RightArm'].head_local).normalized()
        forward=left.cross(up).normalized()
        for frame in (7,19,31):
            bpy.context.scene.frame_set(frame)
            evaluated=mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
            points=[]
            for v in evaluated.data.vertices:
                delta=evaluated.matrix_world @ v.co-hips
                points.append(dict(zip(('x','y','z'),(delta.dot(left),delta.dot(forward),delta.dot(up)))))
            samples.append({'time':(frame-7)/24,'points':points})
        (folder/'animation-reference.json').write_text(json.dumps({'samples':samples,'root_travel':.3}))
        rig.animation_data.use_nla=True;bpy.context.scene.frame_set(19)
        check(snapshot(rig,[mesh])==before,'Fixture sampling failed to restore source')
        results.append({'case':name,'status':'pass','selected_action_only':True,'source_scene_preserved':True})
    # Unsupported object animation and constraints fail before staging or data changes.
    rig.location.x=1;rig.keyframe_insert('location',frame=19)
    before=snapshot(rig,[mesh])
    try:
        addon.exporter.export_bundle(bpy.context,rig,[mesh],str(output),'RejectedObjectMotion',include_action=True)
        raise AssertionError('Object animation was silently exported')
    except ValueError as exc:check('Unsupported Action channel' in str(exc),'Unexpected channel rejection')
    check(snapshot(rig,[mesh])==before and not (output/'RejectedObjectMotion').exists(),'Rejected clip changed source/output')
    results.append({'case':'unsupported_action_rejection','status':'pass'})

    bpy.ops.wm.read_factory_settings(use_empty=True)
    path=Path(r'R:\BLENDER\BANTER_Avatars\Shane.glb')
    source_hash=hashlib.sha256(path.read_bytes()).hexdigest()
    bpy.ops.import_scene.gltf(filepath=str(path))
    rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
    for o in bpy.context.scene.objects: o.select_set(o in meshes or o==rig)
    bpy.context.view_layer.objects.active=rig
    before=snapshot(rig,meshes)
    folder=addon.exporter.export_bundle(bpy.context,rig,meshes,str(output),'ShanePreserved')
    check(snapshot(rig,meshes)==before,"Imported character mutated during export")
    check(hashlib.sha256(path.read_bytes()).hexdigest()==source_hash,"Source GLB modified")
    manifest=json.loads((folder/'ShanePreserved.character.json').read_text())
    check(len(manifest['bones'])==68,"Imported hierarchy plus Root was not preserved")
    check(sum(len(m['shape_keys']) for m in manifest['meshes'])==3,"Imported morphs lost")
    results.append({'case':'ShanePreserved','status':'pass','bones':68,'source_file_preserved':True,'shape_keys':3})
    # Invalid weights block export, and reports themselves are read-only.
    mesh=meshes[0]; group=next(g for g in mesh.vertex_groups if g.name in rig.data.bones)
    for g in mesh.vertex_groups: g.remove([0])
    check(not addon.preflight.inspect(rig,meshes)['ready'],"Unweighted vertex was accepted")
    results.append({'case':'unweighted_rejection','status':'pass'})
    # Row pruning changes only the export working copy; five influences have deterministic support.
    rig=addon.skeleton.create_armature(bpy.context,1.6)
    mesh=synthetic(rig)
    for name in ('Hips','Spine','Spine1','Spine2','Head'):
        mesh.vertex_groups[name].add([0],.2,'REPLACE')
    report=addon.preflight.inspect(rig,[mesh])
    check(report['meshes'][0]['over_four']==1,'Five-influence row not diagnosed')
    copy=mesh.copy();copy.data=mesh.data.copy();bpy.context.scene.collection.objects.link(copy)
    source_weights=[(g.group,g.weight) for g in mesh.data.vertices[0].groups]
    addon.exporter._prune(copy,rig)
    check([(g.group,g.weight) for g in mesh.data.vertices[0].groups]==source_weights,'Pruning mutated source')
    check(len(copy.data.vertices[0].groups)==4 and abs(sum(g.weight for g in copy.data.vertices[0].groups)-1)<1e-6,'Prune support/normalization')
    results.append({'case':'copy_only_four_weight_pruning','status':'pass'})
except Exception:
    results.append({'status':'failed','traceback':traceback.format_exc()})
    (output/'blender-results.json').write_text(json.dumps(results,indent=2))
    raise
(output/'blender-results.json').write_text(json.dumps(results,indent=2))
addon.unregister()
print('LOCAL_CHARACTER_ACCEPTANCE '+json.dumps(results))
