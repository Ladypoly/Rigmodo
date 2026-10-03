# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure NumPy worker. Run with Blender's isolated bundled Python, never bpy."""
import hashlib
import json
import os
from pathlib import Path
import sys
import zipfile

import numpy as np


def load_fields(folder, request):
    path = Path(folder) / 'input.npz'
    if hashlib.sha256(path.read_bytes()).hexdigest() != request['input_sha256']:
        raise ValueError('Regional input changed after preparation')
    # Refuse unexpectedly large archives and object/pickle arrays.
    with zipfile.ZipFile(path) as archive:
        if sum(entry.file_size for entry in archive.infolist()) > request['maximum_array_bytes']:
            raise ValueError('Regional input exceeds its memory budget')
    fields = []
    with np.load(path, allow_pickle=False) as arrays:
        for i, span in enumerate(request['meshes']):
            field = {key: arrays[f'{i}_{key}'] for key in (
                'original', 'edges', 'conductance', 'editable', 'locked', 'protected', 'allowed', 'rigid')}
            if field['original'].shape != (span['count'], len(request['bones'])):
                raise ValueError('Regional vertex/bone correspondence changed')
            if request.get('method') in {'GEODESIC','VOXEL'}:
                for key in ('points','heads','tails','triangles','geometry_method','voxel_resolution','digit_surface'):field[key]=arrays[f'{i}_{key}']
                triangles=field['triangles']
                if triangles.ndim!=2 or triangles.shape[1]!=3 or not np.issubdtype(triangles.dtype,np.integer) or (len(triangles) and (triangles.min()<0 or triangles.max()>=span['count'])):
                    raise ValueError('Invalid volume triangles')
            n, b = field['original'].shape
            if any(field[k].shape != (n,) for k in ('editable', 'protected', 'rigid')) or field['locked'].shape != (b,) or field['allowed'].shape != (n, b):
                raise ValueError('Regional constraints disagree')
            offsets, flat = arrays[f'{i}_seam_offsets'], arrays[f'{i}_seam_flat']
            if offsets.ndim != 1 or not len(offsets) or offsets[0] != 0 or offsets[-1] != len(flat) or (np.diff(offsets) < 0).any():
                raise ValueError('Invalid seam index offsets')
            if flat.ndim != 1 or (len(flat) and (flat.min() < 0 or flat.max() >= n)):
                raise ValueError('Seam exceeds vertex bounds')
            field['seam_groups'] = [flat[a:z] for a, z in zip(offsets[:-1], offsets[1:])]
            fields.append(field)
    return fields


def run(folder):
    # The module directory is owned extension code; isolated Python ignores cwd
    # and environment paths. No imports from job folders or model files.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from weight_math import solve_region
    folder = Path(folder).resolve()
    request = json.loads((folder / 'request.json').read_text())
    if request['provider'] != 'local_character_surface' or request['schema_version'] != 1:
        raise ValueError('Unknown regional protocol')
    fields = load_fields(folder, request)
    result, reports = {}, []
    for i, field in enumerate(fields):
        weights, report = solve_region(field, request['iterations'], request['strength'])
        result[f'{i}_weights'] = weights
        reports.append(report)
        print(f'Solved mesh {i + 1}/{len(fields)}', flush=True)
    with (folder / 'output.tmp').open('wb') as stream: np.savez_compressed(stream, **result)
    os.replace(folder / 'output.tmp', folder / 'output.npz')
    (folder / 'result.json').write_text(json.dumps({'reports': reports,
        'output_sha256': hashlib.sha256((folder / 'output.npz').read_bytes()).hexdigest()}, allow_nan=False))


if __name__ == '__main__': run(sys.argv[1])
