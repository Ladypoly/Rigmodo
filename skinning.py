# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated native inference jobs and validated, copy-only weight application."""
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import time
import uuid

import bpy
from mathutils import Matrix
from .skin_glb import write_input, read_binding

PROVIDER_REVISION = '46dbfecda3d9c2dcd87301c9f1127e1f437ed0ed'
MODEL_REVISION = '2c55d38ffe01871c6956103926cc4a40bd7acc8a'
MODEL_HASHES = {
    'mesh-encoder.gguf': '532710809e3db6c54389dd6489c2aa3c768244868b9c197198d06fa664214527',
    'skin-vae.gguf': 'dcd5859ac89bae62bcfd6b7823f9d0e2393b22364bcb19f84c1109af8e07455e',
    'tokenrig.gguf': '933529dc0e550fd499e2e1ae1c574c6d5852047c04832e7207304e184901ed82',
}
_verified_models = {}
_jobs = {}


def provider_cache():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.cache'))) / 'LocalCharacter' / 'providers' / 'skin-tokens-46dbfec'


def selection(context):
    meshes = [o for o in context.selected_objects if o.type == 'MESH']
    rigs = {o for o in context.selected_objects if o.type == 'ARMATURE'}
    rigs.update(m.object for o in meshes for m in o.modifiers if m.type == 'ARMATURE' and m.object)
    if len(rigs) != 1 or not meshes:
        raise ValueError('Select the accepted armature and meshes to skin, or already-bound meshes using one armature')
    rig = next(iter(rigs))
    helpers = {b.custom_shape for b in rig.pose.bones if b.custom_shape}
    meshes = [o for o in meshes if o not in helpers]
    if not meshes: raise ValueError('Select character geometry, not bone display helpers')
    return rig, meshes


def _digest(rig, meshes):
    digest = hashlib.sha256()
    digest.update(str(rig.as_pointer()).encode())
    for row in rig.matrix_world: digest.update(struct.pack('<4d', *row))
    for bone in rig.data.bones:
        digest.update(json.dumps((bone.name, bone.parent.name if bone.parent else None, bone.use_deform)).encode())
        for row in bone.matrix_local: digest.update(struct.pack('<4d', *row))
        digest.update(struct.pack('<3d', *bone.tail_local))
    for mesh in meshes:
        digest.update(str(mesh.as_pointer()).encode())
        digest.update(json.dumps([(g.name, g.lock_weight) for g in mesh.vertex_groups]).encode())
        digest.update(json.dumps([(m.type, m.show_viewport, m.show_render,
                                   m.object.name if m.type == 'ARMATURE' and m.object else None,
                                   m.vertex_group if m.type == 'ARMATURE' else None)
                                  for m in mesh.modifiers]).encode())
        for row in mesh.matrix_world: digest.update(struct.pack('<4d', *row))
        for vertex in mesh.data.vertices:
            digest.update(struct.pack('<3f', *vertex.co))
            for group in vertex.groups: digest.update(struct.pack('<If', group.group, group.weight))
            digest.update(b'\xff\xff\xff\xff')
        for polygon in mesh.data.polygons:
            digest.update(struct.pack('<I', len(polygon.vertices)))
            digest.update(struct.pack('<' + 'I' * len(polygon.vertices), *polygon.vertices))
        if mesh.data.shape_keys:
            for key in mesh.data.shape_keys.key_blocks:
                for vertex in key.data: digest.update(struct.pack('<3f', *vertex.co))
    return digest.hexdigest()


def prepare(context, rig, meshes, parent=None, device='vulkan', beams=10):
    if context.mode != 'OBJECT': raise ValueError('Switch to Object Mode before AI skinning')
    if device not in {'vulkan', 'cpu'} or not 1 <= beams <= 10: raise ValueError('Unsupported inference settings')
    if len(meshes) != len(set(meshes)) or any(o.type != 'MESH' for o in meshes) or not meshes:
        raise ValueError('Expected distinct mesh objects')
    if rig.type != 'ARMATURE': raise ValueError('Choose an accepted armature')
    if rig.constraints or any(b.constraints for b in rig.pose.bones):
        raise ValueError('Bake a separate accepted deform rig before skinning a constrained armature')
    if rig.matrix_world.determinant() <= 1e-12: raise ValueError('Mirrored or singular armature transforms need preparation')
    for mesh in meshes:
        if mesh.parent_type != 'OBJECT' or mesh.constraints or mesh.matrix_world.determinant() <= 1e-12:
            raise ValueError(f'{mesh.name}: bone parenting, constraints and mirrored/singular transforms need preparation')
        if any(m.type != 'ARMATURE' and m.show_viewport for m in mesh.modifiers):
            raise ValueError(f'{mesh.name}: resolve visible non-armature modifiers on a working copy first')
        if any(m.type == 'ARMATURE' and m.object != rig for m in mesh.modifiers):
            raise ValueError(f'{mesh.name}: modifier uses another armature')
        if any(m.type == 'ARMATURE' and (m.vertex_group or m.use_bone_envelopes or not m.use_vertex_groups)
               for m in mesh.modifiers):
            raise ValueError(f'{mesh.name}: use an unmasked vertex-group armature modifier on a working copy')
    bones = [b for b in rig.data.bones if b.use_deform]
    if not 1 <= len(bones) <= 256: raise ValueError('The accepted rig needs 1–256 deform bones')
    # Preserve connected depth-first branches in the neural token sequence.
    # Breadth-first order is legal GLTF but fragments every limb into repeated
    # branch tokens and differs from the supplied-skeleton reference path.
    deform_names = {bone.name for bone in bones}
    ordered = []
    def visit(bone):
        if bone.name in deform_names: ordered.append(bone)
        for child in bone.children: visit(child)
    for bone in rig.data.bones:
        if bone.parent is None: visit(bone)
    bones = ordered
    index = {b.name: i for i, b in enumerate(bones)}
    scale = context.scene.unit_settings.scale_length
    if not math.isfinite(scale) or scale <= 0: raise ValueError('Scene unit scale must be positive')
    def convert(value):
        result = (value.x * scale, value.z * scale, -value.y * scale)
        if not all(math.isfinite(v) for v in result): raise ValueError('Nonfinite input geometry or joints')
        return struct.unpack('<3f', struct.pack('<3f', *result))
    joints = []
    for bone in bones:
        parent_bone = bone.parent
        while parent_bone and parent_bone.name not in index: parent_bone = parent_bone.parent
        joints.append({'name': bone.name, 'parent': index[parent_bone.name] if parent_bone else -1,
                       'position': convert(rig.matrix_world @ bone.head_local)})
    if sum(j['parent'] < 0 for j in joints) != 1:
        raise ValueError('The deform skeleton must have one root; connect separate deform roots with an accepted deform parent')
    positions, triangles, spans = [], [], []
    for mesh in meshes:
        mesh.data.calc_loop_triangles()
        start = len(positions)
        positions.extend(convert(mesh.matrix_world @ v.co) for v in mesh.data.vertices)
        triangles.extend(tuple(start + i for i in t.vertices) for t in mesh.data.loop_triangles)
        spans.append({'name': mesh.name, 'pointer': str(mesh.as_pointer()), 'start': start, 'count': len(mesh.data.vertices)})
    if not positions or not triangles or len(positions) > 4_000_000: raise ValueError('Empty geometry or vertex limit exceeded')
    directory = Path(parent) if parent else provider_cache().parent.parent / 'jobs'
    directory.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='skin-', dir=directory)).resolve()
    request = {'schema_version': 1, 'job_id': str(uuid.uuid4()), 'provider': 'skin-tokens.cpp',
               'provider_revision': PROVIDER_REVISION, 'model_revision': MODEL_REVISION,
               'rig': rig.name, 'rig_pointer': str(rig.as_pointer()), 'source_digest': _digest(rig, meshes),
               'scene_unit_scale': scale, 'meshes': spans, 'joints': joints, 'device': device, 'beams': beams,
               'vertex_count': len(positions), 'triangle_count': len(triangles),
               'coordinate_space': 'world_meters_gltf_y_up', 'fit': 'none', 'postprocess': False}
    request['joint_order'] = 'depth_first_preserve_siblings'
    request['seed'] = 0
    write_input(folder / 'input.glb', positions, triangles, joints)
    request['input_sha256'] = hashlib.sha256((folder / 'input.glb').read_bytes()).hexdigest()
    (folder / 'request.json').write_text(json.dumps(request, indent=2, allow_nan=False) + '\n')
    _state(folder, 'prepared')
    return folder


def _state(folder, status, **values):
    path = Path(folder) / 'status.json'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'schema_version': 1, 'status': status, **values}, indent=2, allow_nan=False) + '\n')
    os.replace(temporary, path)


def start(folder, executable, models):
    folder, executable, models = Path(folder).resolve(), Path(executable).resolve(), Path(models).resolve()
    request = json.loads((folder / 'request.json').read_text())
    if request['provider_revision'] != PROVIDER_REVISION or request['model_revision'] != MODEL_REVISION:
        raise ValueError('Job uses a different provider or model revision')
    if not executable.is_file(): raise ValueError('Choose the installed skintokens-cli executable')
    for name, expected in MODEL_HASHES.items():
        path = models / name
        if not path.is_file(): raise ValueError(f'Missing model component: {name}')
        stamp = (str(path), path.stat().st_size, path.stat().st_mtime_ns)
        if stamp not in _verified_models:
            with path.open('rb') as stream: actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != expected: raise ValueError(f'{name}: model hash differs from the pinned F16 release')
            _verified_models[stamp] = True
    if hashlib.sha256((folder / 'input.glb').read_bytes()).hexdigest() != request['input_sha256']:
        raise ValueError('Job input changed after preparation')
    if str(folder) in _jobs or (folder / 'output.glb').exists(): raise ValueError('Job was already started; prepare a new request')
    runtime = {'executable': str(executable), 'sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
               'model_hashes': MODEL_HASHES}
    (folder / 'runtime.json').write_text(json.dumps(runtime, indent=2) + '\n')
    log = (folder / 'worker.log').open('wb')
    command = [str(executable), 'skin', str(models), str(folder / 'input.glb'), str(folder / 'input.glb'),
               str(folder / 'output.glb'), '--device', request['device'], '--fit', 'none', '--beams', str(request['beams'])]
    environment = os.environ.copy()
    # Avoid inherited diagnostic overrides bypassing neural generation.
    for key in list(environment):
        if key.startswith('SKINTOKENS_'): environment.pop(key)
    environment['SKINTOKENS_PROFILE'] = '1'
    try:
        process = subprocess.Popen(command, cwd=executable.parent, stdout=log, stderr=subprocess.STDOUT,
                                   env=environment, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except Exception:
        log.close(); raise
    _jobs[str(folder)] = {'process': process, 'log': log, 'started': time.monotonic()}
    try: _state(folder, 'running', pid=process.pid, provider_executable=str(executable))
    except OSError:
        cancel(folder); raise
    return process.pid


def poll(folder):
    folder = Path(folder).resolve()
    job = _jobs.get(str(folder))
    if not job: return json.loads((folder / 'status.json').read_text())
    code = job['process'].poll()
    if code is None: return {'status': 'running', 'elapsed_seconds': time.monotonic() - job['started']}
    job['log'].close()
    _jobs.pop(str(folder))
    _state(folder, 'complete' if code == 0 else 'failed', exit_code=code,
           elapsed_seconds=time.monotonic() - job['started'])
    return json.loads((folder / 'status.json').read_text())


def cancel(folder):
    folder = Path(folder).resolve()
    job = _jobs.pop(str(folder), None)
    if job:
        job['process'].terminate()
        try: job['process'].wait(timeout=3)
        except subprocess.TimeoutExpired: job['process'].kill(); job['process'].wait(timeout=3)
        job['log'].close()
        _state(folder, 'cancelled')


def cancel_all():
    for folder in list(_jobs): cancel(folder)


def validate(folder):
    folder = Path(folder)
    request = json.loads((folder / 'request.json').read_text())
    if poll(folder)['status'] not in {'complete', 'applied'}: raise ValueError('Inference has not completed successfully')
    if hashlib.sha256((folder / 'input.glb').read_bytes()).hexdigest() != request['input_sha256']:
        raise ValueError('Job input changed after preparation')
    original, result = read_binding(folder / 'input.glb'), read_binding(folder / 'output.glb')
    if not result['learned']: raise ValueError('Worker returned a geometric baseline instead of learned weights')
    if result['positions'] != original['positions'] or result['triangles'] != original['triangles']:
        raise ValueError('Worker changed vertex positions/order or triangle correspondence')
    if len(result['joints']) != len(request['joints']): raise ValueError('Worker changed the accepted joint count')
    for expected, actual in zip(request['joints'], result['joints']):
        if expected['name'] != actual['name'] or expected['parent'] != actual['parent'] or any(
                not math.isfinite(b) or abs(a - b) > 1e-5 for a, b in zip(expected['position'], actual['position'])):
            raise ValueError('Worker changed the accepted skeleton')
    rows = []
    for ids, weights in zip(result['ids'], result['weights']):
        if any(i >= len(request['joints']) for i in ids) or any(not math.isfinite(w) or w < 0 for w in weights):
            raise ValueError('Invalid neural influence row')
        total = sum(weights)
        if abs(total - 1) > 1e-4: raise ValueError('Neural weights are not normalized')
        combined = {}
        for i, weight in zip(ids, weights):
            if weight > 0: combined[i] = combined.get(i, 0) + weight
        rows.append(sorted(((i, weight / total) for i, weight in combined.items()), key=lambda p: (-p[1], p[0])))
    return request, rows


def apply(context, folder):
    if context.mode != 'OBJECT': raise ValueError('Switch to Object Mode before creating the weighted copy')
    request, rows = validate(folder)
    rig = bpy.data.objects.get(request['rig'])
    meshes = [bpy.data.objects.get(span['name']) for span in request['meshes']]
    if not rig or any(mesh is None for mesh in meshes) or str(rig.as_pointer()) != request['rig_pointer']:
        raise ValueError('Source objects no longer match this job')
    if rig.name not in context.scene.objects or any(mesh.name not in context.scene.objects for mesh in meshes):
        raise ValueError('Return to the scene containing the source character')
    if context.scene.unit_settings.scale_length != request['scene_unit_scale'] or _digest(rig, meshes) != request['source_digest']:
        raise ValueError('Source mesh or accepted joints changed during inference; prepare a new job')
    if any(o.get('lc_skin_job') == request['job_id'] for o in context.scene.objects):
        raise ValueError('A weighted copy from this job already exists; undo/remove it before reapplying')
    collection = bpy.data.collections.new('Local Character AI Skin')
    created, copied_data = [], []
    try:
        copied_rig = rig.copy(); copied_rig.data = rig.data.copy()
        created.append(copied_rig); copied_data.append(copied_rig.data)
        copied_rig.name = rig.name + '_AI_Skin'
        copied_rig.parent = None; copied_rig.matrix_world = rig.matrix_world.copy()
        collection.objects.link(copied_rig)
        for source, span in zip(meshes, request['meshes']):
            mesh = source.copy(); mesh.data = source.data.copy()
            created.append(mesh); copied_data.append(mesh.data)
            mesh.name = source.name + '_AI_Skin'
            mesh.parent = copied_rig; mesh.parent_type = 'OBJECT'
            mesh.matrix_parent_inverse = Matrix.Identity(4); mesh.matrix_world = source.matrix_world.copy()
            collection.objects.link(mesh)
            modifiers = [m for m in mesh.modifiers if m.type == 'ARMATURE']
            if not modifiers: modifiers = [mesh.modifiers.new('Local Character Skin', 'ARMATURE')]
            for modifier in modifiers: modifier.object = copied_rig
            for group in list(mesh.vertex_groups):
                if group.name in rig.data.bones: mesh.vertex_groups.remove(group)
            groups = {i: mesh.vertex_groups.new(name=j['name']) for i, j in enumerate(request['joints'])}
            for vertex in range(span['count']):
                for i, weight in rows[span['start'] + vertex]: groups[i].add([vertex], weight, 'REPLACE')
            mesh['lc_skin_job'] = request['job_id']
        copied_rig['lc_skinning'] = 'skin_tokens_cpp_f16'
        copied_rig['lc_skin_job'] = request['job_id']
        copied_rig['lc_skin_provider_revision'] = request['provider_revision']
        copied_rig['lc_skin_model_revision'] = request['model_revision']
        context.scene.collection.children.link(collection)
    except Exception:
        for obj in created: bpy.data.objects.remove(obj, do_unlink=True)
        for data in copied_data:
            if data.users == 0:
                if isinstance(data, bpy.types.Armature): bpy.data.armatures.remove(data)
                else: bpy.data.meshes.remove(data)
        bpy.data.collections.remove(collection)
        raise
    previous = json.loads((Path(folder) / 'status.json').read_text())
    _state(folder, 'applied', collection=collection.name, job_id=request['job_id'],
           elapsed_seconds=previous.get('elapsed_seconds'))
    return collection, copied_rig, created[1:]
