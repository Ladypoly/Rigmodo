# SPDX-License-Identifier: GPL-3.0-or-later
"""Owned, cancellable CPU surface jobs with stale-input and result checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

import bpy
import numpy as np
from . import skinning, regions, weight_copy
from .surface_worker import load_fields


def python_executable():
    directory = Path(bpy.app.binary_path).parent / f'{bpy.app.version[0]}.{bpy.app.version[1]}' / 'python'
    candidates = [directory / 'bin/python.exe', directory / 'bin/python3', Path(sys.prefix) / 'bin/python3']
    for candidate in candidates:
        if candidate.is_file(): return candidate.resolve()
    raise ValueError('Bundled Python runtime was not found')


def prepare(context, rig, meshes, parent=None, method='AUTO', iterations=12, strength=.35,
            selected_only=False, join_seams=True):
    if not 1 <= iterations <= 200 or not 0 < strength <= 1: raise ValueError('Invalid refinement settings')
    names, fields, reports = regions.prepare_fields(context, rig, meshes, method, selected_only, join_seams)
    arrays = {}
    for i, field in enumerate(fields):
        for key, value in field.items():
            if key != 'seam_groups': arrays[f'{i}_{key}'] = np.asarray(value)
        seams = field['seam_groups']
        arrays[f'{i}_seam_flat'] = np.asarray([v for group in seams for v in group], dtype=np.int64)
        arrays[f'{i}_seam_offsets'] = np.cumsum([0] + [len(group) for group in seams], dtype=np.int64)
    total_bytes = sum(a.nbytes for a in arrays.values())
    if total_bytes > 512 * 1024 ** 2: raise ValueError('Refine smaller mesh selections; dense fields exceed the 512 MiB input budget')
    directory = Path(parent) if parent else skinning.provider_cache().parent.parent / 'jobs'
    directory.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='surface-', dir=directory)).resolve()
    np.savez_compressed(folder / 'input.npz', **arrays)
    request = dict(schema_version=1, provider='local_character_surface', job_id=str(uuid.uuid4()),
                   rig=rig.name, rig_pointer=str(rig.as_pointer()), bones=names,
                   source_digest=skinning._digest(rig, meshes), scene_unit_scale=context.scene.unit_settings.scale_length,
                   meshes=[dict(name=o.name, pointer=str(o.as_pointer()), count=len(o.data.vertices)) for o in meshes],
                   iterations=iterations, strength=strength, reports=reports,
                   maximum_array_bytes=total_bytes + len(arrays) * 4096,
                   input_sha256=hashlib.sha256((folder / 'input.npz').read_bytes()).hexdigest())
    (folder / 'request.json').write_text(json.dumps(request, indent=2, allow_nan=False))
    skinning._state(folder, 'prepared')
    return folder


def start(folder):
    folder = Path(folder).resolve()
    if skinning._jobs: raise ValueError('Wait for the current local job or cancel it')
    request = json.loads((folder / 'request.json').read_text())
    if request['provider'] != 'local_character_surface' or skinning.poll(folder)['status'] != 'prepared':
        raise ValueError('Prepare a new surface job')
    load_fields(folder, request)
    executable, worker = python_executable(), Path(__file__).with_name('surface_worker.py')
    log = (folder / 'worker.log').open('wb')
    try:
        process = subprocess.Popen([str(executable), '-I', str(worker), str(folder)], stdout=log,
            stderr=subprocess.STDOUT, cwd=executable.parent,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    except Exception: log.close(); raise
    skinning._jobs[str(folder)] = dict(process=process, log=log, started=time.monotonic())
    try: skinning._state(folder, 'running', pid=process.pid)
    except OSError: skinning.cancel(folder); raise
    return process.pid


def apply(context, folder):
    folder = Path(folder).resolve()
    if context.mode != 'OBJECT': raise ValueError('Return to Object Mode to create the review copies')
    if skinning.poll(folder)['status'] not in {'complete', 'applied'}: raise ValueError('Surface worker has not completed')
    request = json.loads((folder / 'request.json').read_text())
    if request['provider'] != 'local_character_surface': raise ValueError('This is not a surface job')
    inputs = load_fields(folder, request)
    rig = bpy.data.objects.get(request['rig'])
    meshes = [bpy.data.objects.get(s['name']) for s in request['meshes']]
    if not rig or any(o is None for o in meshes) or str(rig.as_pointer()) != request['rig_pointer'] or any(
            str(o.as_pointer()) != span['pointer'] for o, span in zip(meshes, request['meshes'])):
        raise ValueError('Regional source objects no longer match')
    if rig.name not in context.scene.objects or any(o.name not in context.scene.objects for o in meshes):
        raise ValueError('Return to the source character scene')
    if context.scene.unit_settings.scale_length != request['scene_unit_scale'] or skinning._digest(rig, meshes) != request['source_digest']:
        raise ValueError('Source geometry, joints or weights changed during refinement; prepare a new job')
    if any(o.get('lc_region_job') == request['job_id'] for o in context.scene.objects): raise ValueError('Regional job already applied')
    result = json.loads((folder / 'result.json').read_text())
    path = folder / 'output.npz'
    if hashlib.sha256(path.read_bytes()).hexdigest() != result['output_sha256']: raise ValueError('Regional result changed')
    with zipfile.ZipFile(path) as archive:
        if sum(e.file_size for e in archive.infolist()) > sum(f['original'].nbytes for f in inputs) + len(inputs) * 4096:
            raise ValueError('Regional output exceeds its memory budget')
    fields, reports = [], []
    with np.load(path, allow_pickle=False) as arrays:
        for i, (field, report, solve) in enumerate(zip(inputs, request['reports'], result['reports'])):
            weights = arrays[f'{i}_weights']
            original, protected, locked, rigid = (field[k] for k in ('original', 'protected', 'locked', 'rigid'))
            if weights.shape != original.shape or not np.isfinite(weights).all() or (weights < 0).any() or np.max(np.abs(weights.sum(axis=1) - 1)) > 1e-4:
                raise ValueError('Invalid regional weight output')
            if not np.array_equal(weights[protected], original[protected]) or not np.array_equal(weights[:, locked], original[:, locked]):
                raise ValueError('Worker violated artist weight constraints')
            ids = np.flatnonzero(rigid >= 0)
            if len(ids) and (not np.all(weights[ids, rigid[ids]] == 1) or not np.all(weights[ids].sum(axis=1) == 1)):
                raise ValueError('Worker violated rigid binding')
            editable = field['editable'] & ~protected
            if (weights[editable] * ~field['allowed'][editable])[:, ~locked].any(): raise ValueError('Worker violated digit exclusions')
            unchanged = ~field['editable'] & (rigid < 0)
            if not np.array_equal(weights[unchanged], original[unchanged]): raise ValueError('Worker altered preserved body weights')
            fields.append(weights.copy()); report.update(solve); reports.append(report)
    if len(fields) != len(meshes): raise ValueError('Regional result omitted meshes')
    copied = weight_copy.create(context, rig, meshes, request['bones'], fields,
        method=rig.get('lc_skinning', 'accepted_weights') + '+regional_surface', metadata=json.dumps(reports))
    for obj in [copied[1], *copied[2]]: obj['lc_region_job'] = request['job_id']
    state = skinning.poll(folder)
    skinning._state(folder, 'applied', collection=copied[0].name, elapsed_seconds=state.get('elapsed_seconds'))
    return copied, reports
