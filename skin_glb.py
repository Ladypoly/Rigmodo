# SPDX-License-Identifier: GPL-3.0-or-later
"""Small correspondence-preserving GLB transport for a local weight worker.

This is not an asset interchange importer: materials, UVs and morphs stay in
Blender. One transport primitive keeps original vertex IDs and seam splits.
"""
import json
import math
from pathlib import Path
import struct


def write_input(path, positions, triangles, joints):
    binary, views, accessors = bytearray(), [], []

    def add(rows, fmt, component, kind, target=None):
        while len(binary) % 4: binary.append(0)
        offset = len(binary)
        for row in rows: binary.extend(struct.pack('<' + fmt, *row))
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(binary) - offset}
        if target: view["target"] = target
        views.append(view)
        accessor = {"bufferView": len(views) - 1, "componentType": component, "count": len(rows), "type": kind}
        accessors.append(accessor)
        return len(accessors) - 1

    position_id = add(positions, '3f', 5126, 'VEC3', 34962)
    accessors[position_id].update(min=[min(p[i] for p in positions) for i in range(3)],
                                  max=[max(p[i] for p in positions) for i in range(3)])
    index_id = add([(v,) for tri in triangles for v in tri], 'I', 5125, 'SCALAR', 34963)
    # Placeholder weights are ignored by the supplied-skeleton neural path.
    joint_id = add([(0, 0, 0, 0)] * len(positions), '4H', 5123, 'VEC4', 34962)
    weight_id = add([(1., 0., 0., 0.)] * len(positions), '4f', 5126, 'VEC4', 34962)
    inverse = [(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, *(-v for v in j['position']), 1) for j in joints]
    bind_id = add(inverse, '16f', 5126, 'MAT4')
    nodes = []
    for i, joint in enumerate(joints):
        parent = joint['parent']
        origin = joints[parent]['position'] if parent >= 0 else (0, 0, 0)
        node = {"name": joint['name'], "translation": [joint['position'][k] - origin[k] for k in range(3)]}
        children = [n for n, child in enumerate(joints) if child['parent'] == i]
        if children: node['children'] = children
        nodes.append(node)
    nodes.append({"name": "WeightInputMesh", "mesh": 0, "skin": 0})
    document = {"asset": {"version": "2.0", "generator": "Local Character weight transport"},
                "buffers": [{"byteLength": len(binary)}], "bufferViews": views, "accessors": accessors,
                "nodes": nodes, "scenes": [{"nodes": [0, len(joints)]}], "scene": 0,
                "meshes": [{"primitives": [{"attributes": {"POSITION": position_id, "JOINTS_0": joint_id,
                             "WEIGHTS_0": weight_id}, "indices": index_id, "mode": 4}]}],
                "skins": [{"joints": list(range(len(joints))), "skeleton": 0, "inverseBindMatrices": bind_id}]}
    encoded = json.dumps(document, allow_nan=False, separators=(',', ':')).encode()
    encoded += b' ' * (-len(encoded) % 4)
    binary += b'\0' * (-len(binary) % 4)
    length = 12 + 8 + len(encoded) + 8 + len(binary)
    Path(path).write_bytes(struct.pack('<III', 0x46546c67, 2, length) + struct.pack('<II', len(encoded), 0x4e4f534a)
                           + encoded + struct.pack('<II', len(binary), 0x004e4942) + binary)


def read_binding(path):
    try: return _read_binding(path)
    except (KeyError, IndexError, TypeError, struct.error) as exc:
        raise ValueError('Malformed worker GLB structure') from exc


def _read_binding(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > 512 * 1024 * 1024:
        raise ValueError('Missing or oversized worker GLB')
    raw = path.read_bytes()
    if len(raw) < 28 or struct.unpack_from('<III', raw) != (0x46546c67, 2, len(raw)):
        raise ValueError('Invalid worker GLB header')
    size, kind = struct.unpack_from('<II', raw, 12)
    if kind != 0x4e4f534a or size > 16 * 1024 * 1024 or 20 + size + 8 > len(raw):
        raise ValueError('Invalid worker JSON chunk')
    document = json.loads(raw[20:20 + size])
    bin_size, bin_kind = struct.unpack_from('<II', raw, 20 + size)
    binary = memoryview(raw)[28 + size:]
    if bin_kind != 0x004e4942 or bin_size != len(binary): raise ValueError('Invalid worker binary chunk')

    def accessor(index, components, component):
        if type(index) is not int or not 0 <= index < len(document['accessors']):
            raise ValueError('Invalid worker accessor index')
        item = document['accessors'][index]
        if item.get('sparse') or item['componentType'] != component or item.get('normalized', False):
            raise ValueError('Unsupported worker accessor')
        types = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
        if types.get(item['type']) != components: raise ValueError('Worker accessor shape mismatch')
        count = item['count']
        if not isinstance(count, int) or count < 0 or count > 4_000_000:
            raise ValueError('Worker accessor count exceeds limit')
        view_id = item['bufferView']
        if type(view_id) is not int or not 0 <= view_id < len(document['bufferViews']):
            raise ValueError('Invalid worker buffer view index')
        view = document['bufferViews'][view_id]
        if view['buffer'] != 0: raise ValueError('External worker buffers are unsupported')
        fmt = {5126: 'f', 5123: 'H', 5125: 'I'}[component]
        width = struct.calcsize('<' + fmt * components)
        stride = view.get('byteStride', width)
        view_offset, item_offset, view_size = view.get('byteOffset', 0), item.get('byteOffset', 0), view['byteLength']
        if any(type(v) is not int or v < 0 for v in (stride, view_offset, item_offset, view_size)):
            raise ValueError('Invalid worker accessor offsets')
        offset = view_offset + item_offset
        end = offset + (count - 1) * stride + width if count else offset
        if stride < width or offset < 0 or end > len(binary) or end > view.get('byteOffset', 0) + view['byteLength']:
            raise ValueError('Worker accessor exceeds buffer bounds')
        return [struct.unpack_from('<' + fmt * components, binary, offset + n * stride) for n in range(count)]

    meshes, skins = document['meshes'], document['skins']
    if len(meshes) != 1 or len(meshes[0]['primitives']) != 1 or len(skins) != 1:
        raise ValueError('Worker must return one correspondence-preserving primitive and skin')
    primitive = meshes[0]['primitives'][0]
    if primitive.get('mode', 4) != 4: raise ValueError('Worker did not return triangles')
    attributes = primitive['attributes']
    positions = accessor(attributes['POSITION'], 3, 5126)
    ids = accessor(attributes['JOINTS_0'], 4, 5123)
    weights = accessor(attributes['WEIGHTS_0'], 4, 5126)
    triangles = [row[0] for row in accessor(primitive['indices'], 1, 5125)]
    nodes, skin = document['nodes'], skins[0]
    joint_nodes = skin['joints']
    if not 1 <= len(joint_nodes) <= 256 or any(type(i) is not int or not 0 <= i < len(nodes) for i in joint_nodes) or len(set(joint_nodes)) != len(joint_nodes):
        raise ValueError('Invalid worker joint list')
    by_node = {node: i for i, node in enumerate(joint_nodes)}
    parents = {}
    for index, node in enumerate(nodes):
        for child in node.get('children', []):
            if type(child) is not int or not 0 <= child < len(nodes): raise ValueError('Invalid worker child node')
            if child in parents: raise ValueError('Worker node has multiple parents')
            parents[child] = index
    joints = []
    for node_id in joint_nodes:
        node = nodes[node_id]
        if node.get('rotation', [0, 0, 0, 1]) != [0, 0, 0, 1] or node.get('scale', [1, 1, 1]) != [1, 1, 1] or 'matrix' in node:
            raise ValueError('Unexpected worker rest-frame transform')
        parent_id = parents.get(node_id)
        parent = by_node.get(parent_id, -1)
        if parent_id is not None and parent < 0: raise ValueError('Unexpected external worker parent')
        if parent >= len(joints): raise ValueError('Worker joints are not ordered parent-first')
        local = node.get('translation', [0, 0, 0])
        if len(local) != 3 or not all(math.isfinite(v) for v in local): raise ValueError('Invalid worker joint position')
        origin = joints[parent]['position'] if parent >= 0 else (0, 0, 0)
        joints.append({'name': node['name'], 'parent': parent, 'position': [local[k] + origin[k] for k in range(3)]})
    if not (len(ids) == len(weights) == len(positions)) or len(triangles) % 3:
        raise ValueError('Worker geometry/weight arrays disagree')
    if any(i >= len(positions) for i in triangles): raise ValueError('Invalid worker triangle vertex')
    if not all(math.isfinite(v) for row in positions for v in row): raise ValueError('Nonfinite worker geometry')
    return {'positions': positions, 'triangles': triangles, 'joints': joints, 'ids': ids, 'weights': weights,
            'learned': skin.get('name') == 'SkinTokens learned binding'}
