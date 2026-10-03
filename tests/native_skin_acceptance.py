"""Private fixed-skeleton skinning acceptance; never saves source avatars."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import struct
import sys
import time

import bpy

extension = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('local_character', extension / '__init__.py', submodule_search_locations=[str(extension)])
addon = importlib.util.module_from_spec(spec); sys.modules[spec.name] = addon; spec.loader.exec_module(addon)
from local_character import skinning, preflight, exporter, skeleton, regions
arguments = sys.argv[sys.argv.index('--') + 1:]
output = Path(arguments[0]).resolve(); output.mkdir(parents=True, exist_ok=True)
source = Path(r'R:\BLENDER\BANTER_Avatars\Shane.glb')
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.read_factory_settings(use_empty=True)
addon.register()
bpy.ops.import_scene.gltf(filepath=str(source))
rig = next(o for o in bpy.context.scene.objects if o.type == 'ARMATURE')
if '--core-skeleton' in arguments:
    for bone in rig.data.bones: bone.use_deform = bone.name in skeleton.HUMAN_MAPPING
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and any(m.type == 'ARMATURE' and m.object == rig for m in o.modifiers)]
if '--protected' in arguments:
    for mesh in meshes:
        regions.protect(mesh, list(range(min(12,len(mesh.data.vertices)))))
        mesh.vertex_groups['LeftHandIndex1'].lock_weight=True
for obj in bpy.context.scene.objects: obj.select_set(obj in meshes or obj == rig)
bpy.context.view_layer.objects.active = rig
before = skinning._digest(rig, meshes)
weights = [[[g.group, g.weight] for g in v.groups] for mesh in meshes for v in mesh.data.vertices]
jobs = skinning.prepare(bpy.context, rig, meshes, output / 'jobs', beams=10)
(output / 'prepared-job.txt').write_text(str(jobs))
if '--prepare-only' in arguments:
    print('LOCAL_CHARACTER_SKIN_PREPARED', jobs, flush=True)
else:
    cache = skinning.provider_cache()
    if '--reuse-result' in arguments:
        previous = Path(arguments[arguments.index('--reuse-result') + 1])
        assert hashlib.sha256((previous / 'input.glb').read_bytes()).hexdigest() == hashlib.sha256((jobs / 'input.glb').read_bytes()).hexdigest()
        shutil.copyfile(previous / 'output.glb', jobs / 'output.glb')
        skinning._state(jobs, 'complete', reused_result=str(previous))
    else:
        skinning.start(jobs, cache / 'bin/skintokens-cli.exe', cache / 'models/F16')
        while skinning.poll(jobs)['status'] == 'running':
            time.sleep(.5)
    inference_state = skinning.poll(jobs)
    request, rows = skinning.validate(jobs)
    assert skinning._digest(rig, meshes) == before, 'Inference changed source geometry/rig'
    # Stale requests must fail before allocating a collection or replacing weights.
    head = rig.data.bones[0]
    original_mesh_position = meshes[0].data.vertices[0].co.copy()
    meshes[0].data.vertices[0].co.x += .01
    count = len(bpy.data.objects)
    try:
        skinning.apply(bpy.context, jobs)
        raise AssertionError('Stale geometry accepted')
    except ValueError as exc:
        assert 'changed during inference' in str(exc)
    assert len(bpy.data.objects) == count
    meshes[0].data.vertices[0].co = original_mesh_position
    # Intervening weight painting must not silently disappear in an accepted result.
    vertex = next(v for v in meshes[0].data.vertices if len(v.groups))
    influence = vertex.groups[0]; old_weight = influence.weight
    group = meshes[0].vertex_groups[influence.group]
    group.add([vertex.index], old_weight * .5, 'REPLACE')
    try:
        skinning.apply(bpy.context, jobs)
        raise AssertionError('Stale painted weights accepted')
    except ValueError as exc: assert 'changed during inference' in str(exc)
    group.add([vertex.index], old_weight, 'REPLACE')
    assert skinning._digest(rig, meshes) == before
    def alter_joint(amount):
        for obj in bpy.context.selected_objects: obj.select_set(False)
        rig.select_set(True); bpy.context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        rig.data.edit_bones['LeftHand'].head.x += amount
        bpy.ops.object.mode_set(mode='OBJECT')
    saved_hand = rig.data.bones['LeftHand'].head_local.copy()
    alter_joint(.01)
    try:
        skinning.apply(bpy.context, jobs)
        raise AssertionError('Stale accepted joints used')
    except ValueError as exc: assert 'changed during inference' in str(exc)
    bpy.ops.object.mode_set(mode='EDIT')
    rig.data.edit_bones['LeftHand'].head = saved_hand
    bpy.ops.object.mode_set(mode='OBJECT')
    assert skinning._digest(rig, meshes) == before
    # Reject corrupt weights and nonexistent bone IDs before scene allocation.
    raw = (jobs / 'output.glb').read_bytes()
    document_size = struct.unpack_from('<I', raw, 12)[0]
    document = json.loads(raw[20:20 + document_size])
    attributes = document['meshes'][0]['primitives'][0]['attributes']
    for semantic, fmt, bad in [('WEIGHTS_0', 'f', float('nan')), ('JOINTS_0', 'H', 65535)]:
        accessor = document['accessors'][attributes[semantic]]
        view = document['bufferViews'][accessor['bufferView']]
        offset = 28 + document_size + view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        corrupt = bytearray(raw); struct.pack_into('<' + fmt, corrupt, offset, bad)
        (jobs / 'output.glb').write_bytes(corrupt)
        try:
            skinning.apply(bpy.context, jobs)
            raise AssertionError('Corrupt neural influences accepted')
        except ValueError as exc: assert 'Invalid neural influence' in str(exc)
        assert len(bpy.data.objects) == count
        (jobs / 'output.glb').write_bytes(raw)
    # Exercise the installed public operator used by the asynchronous job's finish.
    bpy.context.scene.lc_settings.skin_job = str(jobs)
    assert bpy.ops.local_character.apply_skin_job() == {'FINISHED'}
    copied_rig = bpy.context.view_layer.objects.active
    copies = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    copies.sort(key=lambda o: next(i for i, mesh in enumerate(meshes) if o.data.name.startswith(mesh.data.name)))
    assert skinning._digest(rig, meshes) == before, 'Applying proposal changed original geometry/rig'
    assert weights == [[[g.group, g.weight] for g in v.groups] for mesh in meshes for v in mesh.data.vertices], 'Applying proposal changed source weights'
    assert len(copies) == len(meshes)
    if '--protected' in arguments:
        import numpy as np
        names=[j['name'] for j in request['joints']]
        for original,copied in zip(meshes,copies):
            a,b=regions.dense_weights(original,names),regions.dense_weights(copied,names)
            assert np.array_equal(a[:12],b[:12]),'AI overwrote protected rows'
            assert np.array_equal(a[:,names.index('LeftHandIndex1')],b[:,names.index('LeftHandIndex1')]),'AI overwrote locked influence'
            assert copied.vertex_groups['LeftHandIndex1'].lock_weight
    try:
        skinning.apply(bpy.context, jobs)
        raise AssertionError('Duplicate application accepted')
    except ValueError as exc: assert 'already exists' in str(exc)
    for original, copied in zip(meshes, copies):
        assert [v.co[:] for v in original.data.vertices] == [v.co[:] for v in copied.data.vertices]
        assert [[v.uv[:] for v in layer.data] for layer in original.data.uv_layers] == [[v.uv[:] for v in layer.data] for layer in copied.data.uv_layers]
        assert list(original.data.materials) == list(copied.data.materials)
        if original.data.shape_keys:
            assert [[v.co[:] for v in key.data] for key in original.data.shape_keys.key_blocks] == [[v.co[:] for v in key.data] for key in copied.data.shape_keys.key_blocks]
    assert [(b.name, b.parent.name if b.parent else None, [list(r) for r in b.matrix_local]) for b in rig.data.bones] == [(b.name, b.parent.name if b.parent else None, [list(r) for r in b.matrix_local]) for b in copied_rig.data.bones]
    report = preflight.inspect(copied_rig, copies)
    assert report['ready'], report['errors']
    for obj in bpy.context.scene.objects: obj.select_set(obj in copies or obj == copied_rig)
    bpy.context.view_layer.objects.active = copied_rig
    bundle = exporter.export_bundle(bpy.context, copied_rig, copies, str(output), 'ShaneAISkin')
    manifest = json.loads((bundle / 'ShaneAISkin.character.json').read_text())
    assert manifest['provenance']['skinning'] == 'skin_tokens_cpp_f16'
    # A posed deformation comparison diagnoses quality; the imported weights are
    # a reference, not a universal correctness label or a pass threshold.
    import statistics
    from mathutils import Quaternion, Vector
    pose_cases = [('forearm', 'LeftForeArm', (0, 0, 1), 60),
                  ('index', 'LeftHandIndex1', (1, 0, 0), 55),
                  ('knee', 'LeftLeg', (1, 0, 0), 70)]
    quality = []
    for name, bone, axis, angle in pose_cases:
        for armature in (rig, copied_rig):
            armature.pose.bones[bone].rotation_mode = 'QUATERNION'
            armature.pose.bones[bone].rotation_quaternion = Quaternion(Vector(axis), math.radians(angle))
        bpy.context.view_layer.update()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        errors = []
        for original, copied in zip(meshes, copies):
            a, b = original.evaluated_get(depsgraph), copied.evaluated_get(depsgraph)
            errors.extend(((a.matrix_world @ va.co) - (b.matrix_world @ vb.co)).length
                          for va, vb in zip(a.data.vertices, b.data.vertices))
        quality.append({'pose': name, 'reference_difference_mean_m': statistics.mean(errors),
                        'reference_difference_max_m': max(errors), 'finite': all(math.isfinite(v) for v in errors)})
        for armature in (rig, copied_rig): armature.pose.bones[bone].matrix_basis.identity()
    # Save only the private test scene for visual inspection, never the source file.
    bpy.ops.wm.save_as_mainfile(filepath=str(output / 'ai-skin-review.blend'))
    cancelled = skinning.prepare(bpy.context, rig, meshes, output / 'jobs')
    pid = skinning.start(cancelled, cache / 'bin/skintokens-cli.exe', cache / 'models/F16')
    skinning.cancel(cancelled)
    assert skinning.poll(cancelled)['status'] == 'cancelled' and not skinning._jobs
    assert skinning._digest(rig, meshes) == before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    summary = {'status': 'pass', 'provider_revision': skinning.PROVIDER_REVISION, 'model_revision': skinning.MODEL_REVISION,
               'job': str(jobs), 'bundle': str(bundle), 'vertices': len(rows), 'joints': len(request['joints']),
               'source_preserved': True, 'accepted_joints_preserved': True, 'materials_morphs_preserved': True,
               'maximum_influences': max(map(len, rows)), 'preflight': report}
    summary.update(inference=inference_state, quality_diagnostics=quality,
                   protected_and_locked_preserved='--protected' in arguments,
                   stale_geometry_rejected=True, stale_weights_rejected=True,
                   stale_joints_rejected=True, corrupt_weights_rejected=True,
                   cancellation_passed=True, duplicate_application_rejected=True,
                   public_apply_operator=True)
    (output / 'skin-results.json').write_text(json.dumps(summary, indent=2))
    print('LOCAL_CHARACTER_SKIN_ACCEPTANCE', json.dumps(summary), flush=True)
