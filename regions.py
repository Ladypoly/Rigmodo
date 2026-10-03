# SPDX-License-Identifier: GPL-3.0-or-later
"""Persistent regional controls and conservative surface routing."""
from collections import defaultdict
import json
import math
import uuid

import bpy
import numpy as np
from .skeleton import canonical_name, FINGERS
from . import weight_copy
from .weight_math import constrained_weights, surface_diffusion

PROTECTED = '_LC_Protected'
POLICIES = 'lc_region_policies'


def dense_weights(mesh, bone_names):
    index = {name: i for i, name in enumerate(bone_names)}
    by_group = {g.index: index[g.name] for g in mesh.vertex_groups if g.name in index}
    matrix = np.zeros((len(mesh.data.vertices), len(bone_names)), dtype=np.float32)
    for vertex in mesh.data.vertices:
        for influence in vertex.groups:
            if influence.group in by_group: matrix[vertex.index, by_group[influence.group]] = influence.weight
    return matrix


def group_mask(mesh, name):
    group = mesh.vertex_groups.get(name)
    if not group: return np.zeros(len(mesh.data.vertices), dtype=bool)
    return np.array([any(g.group == group.index and g.weight > .5 for g in v.groups) for v in mesh.data.vertices], dtype=bool)


def selected_vertices(mesh):
    if mesh.mode != 'OBJECT': raise ValueError('Return to Object Mode after selecting the region vertices')
    return [v.index for v in mesh.data.vertices if v.select]


def protect(mesh, indices, enabled=True):
    if mesh.mode != 'OBJECT': raise ValueError('Protection needs Object Mode')
    if not indices: raise ValueError('Select vertices in Edit Mode, then return to Object Mode')
    group = mesh.vertex_groups.get(PROTECTED) or mesh.vertex_groups.new(name=PROTECTED)
    if enabled: group.add(indices, 1, 'REPLACE')
    else: group.remove(indices)


def mark(mesh, indices, kind='SURFACE', bone='', digit=''):
    if not indices: raise ValueError('Select region vertices in Edit Mode, then return to Object Mode')
    if kind not in {'AUTO', 'SURFACE', 'RIGID'}: raise ValueError('Unsupported region policy')
    if digit and digit not in {s + 'Hand' + f for s in ('Left', 'Right') for f in FINGERS}:
        raise ValueError('Choose a known humanoid digit')
    policies = json.loads(mesh.get(POLICIES, '[]'))
    # Latest policy wins on overlaps, with protection/locked weights taking precedence.
    group_name = '_LC_R_' + uuid.uuid4().hex[:12]
    mesh.vertex_groups.new(name=group_name).add(indices, 1, 'REPLACE')
    policies.append({'group': group_name, 'kind': kind, 'bone': bone, 'digit': digit})
    mesh[POLICIES] = json.dumps(policies)
    return group_name


def clear(mesh, indices):
    """Remove selected vertices from policy masks without changing their weights."""
    if mesh.mode != 'OBJECT' or not indices: raise ValueError('Select vertices, then return to Object Mode')
    policies = json.loads(mesh.get(POLICIES, '[]'))
    retained = []
    for policy in policies:
        group = mesh.vertex_groups.get(policy['group'])
        if not group: continue
        group.remove(indices)
        if group_mask(mesh, group.name).any(): retained.append(policy)
        else: mesh.vertex_groups.remove(group)
    mesh[POLICIES] = json.dumps(retained)


def _digit(name):
    name = canonical_name(name)
    for side in ('Left', 'Right'):
        for finger in FINGERS:
            family = side + 'Hand' + finger
            if name.startswith(family): return family
    return ''


def digit_labels(matrix, bone_names):
    families = sorted({_digit(name) for name in bone_names} - {''})
    if not families: return np.full(len(matrix), '', dtype=object)
    sums = np.column_stack([matrix[:, [_digit(name) == family for name in bone_names]].sum(axis=1) for family in families])
    best = sums.argmax(axis=1)
    confidence = sums[np.arange(len(matrix)), best]
    sorted_sums = np.sort(sums, axis=1)
    margin = sorted_sums[:, -1] - (sorted_sums[:, -2] if len(families) > 1 else 0)
    return np.array([families[i] if c >= .2 and m >= .1 else '' for i, c, m in zip(best, confidence, margin)], dtype=object)


def joint_digit_labels(mesh, rig, matrix, names, geometry_only=False):
    """Resolve finger identity from accepted rest chains near the digit surface.

    Existing weights bound the hand scope; joint distance disambiguates wrong
    neighboring-digit predictions. Remote geometry retains its weight labels.
    """
    labels = digit_labels(matrix, names)
    points = np.array([tuple(mesh.matrix_world @ v.co) for v in mesh.data.vertices], dtype=np.float64)
    families = sorted({_digit(n) for n in names} - {''})
    if not families: return labels, 0
    distances, radii = [], []
    for family in families:
        chain = [rig.data.bones[n] for n in names if _digit(n) == family]
        segments = [(np.array(rig.matrix_world @ b.head_local), np.array(rig.matrix_world @ b.tail_local)) for b in chain]
        field = np.full(len(points), np.inf)
        for a, b in segments:
            direction = b-a; squared = float(direction @ direction)
            t = np.clip((points-a) @ direction / max(squared, 1e-12), 0, 1)
            field = np.minimum(field, np.linalg.norm(points-a-t[:,None]*direction, axis=1))
        distances.append(field); radii.append(max(sum(np.linalg.norm(b-a) for a,b in segments)*.35, 1e-6))
    distance = np.column_stack(distances); closest = distance.argmin(axis=1)
    best = distance[np.arange(len(points)),closest]
    sorted_distance = np.sort(distance,axis=1)
    relative_margin = (sorted_distance[:,1]-best)/np.maximum(sorted_distance[:,1],1e-8) if len(families)>1 else np.ones(len(points))
    finger_mass = matrix[:, [bool(_digit(n)) for n in names]].sum(axis=1)
    # Closely spaced ambiguous digits stay artist-reviewable. No nearest-point
    # surface edges are added, and remote accessories are never auto-rigid.
    confident = ((finger_mass >= .2) | (geometry_only & (matrix.sum(axis=1)==0))) & (best < np.asarray(radii)[closest]) & (relative_margin >= .15)
    changed = 0
    for vertex in np.flatnonzero(confident):
        family = families[closest[vertex]]
        changed += labels[vertex] != family
        labels[vertex] = family
    return labels, int(changed)


def surface_graph(mesh, labels, join_seams=True):
    points = np.array([tuple(mesh.matrix_world @ v.co) for v in mesh.data.vertices], dtype=np.float64)
    edges = [(e.vertices[0], e.vertices[1]) for e in mesh.data.edges]
    lengths = np.array([np.linalg.norm(points[a] - points[b]) for a, b in edges])
    extent = max(float(np.ptp(points, axis=0).max()), 1e-6)
    conductance = list(1 / np.maximum(lengths, extent * 1e-6))
    report = {'topological_edges': len(edges), 'verified_seam_edges': 0, 'ambiguous_seam_edges': 0}
    parents = list(range(len(points)))
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]; i = parents[i]
        return i
    def join(a, b): parents[root(b)] = root(a)
    if join_seams:
        # Two matching *boundary edges*, opposite winding, compatible face
        # normals and region labels are needed. Proximity alone is insufficient.
        epsilon = extent * 1e-7
        key = [tuple(np.rint(p / epsilon).astype(np.int64)) for p in points]
        edge_faces = defaultdict(list)
        for polygon in mesh.data.polygons:
            vertices = list(polygon.vertices)
            for a, b in zip(vertices, vertices[1:] + vertices[:1]): edge_faces[tuple(sorted((a, b)))].append((a, b, polygon.index))
        boundary = defaultdict(list)
        for entries in edge_faces.values():
            if len(entries) == 1:
                a, b, face = entries[0]
                if key[a] != key[b]: boundary[tuple(sorted((key[a], key[b])))].append((a, b, face))
        for entries in boundary.values():
            if len(entries) != 2:
                if len(entries) > 2: report['ambiguous_seam_edges'] += 1
                continue
            a, b, face = entries[0]; c, d, other = entries[1]
            if key[a] != key[d] or key[b] != key[c]: continue
            if np.linalg.norm(points[a] - points[d]) > epsilon or np.linalg.norm(points[b] - points[c]) > epsilon: continue
            if labels[a] != labels[d] or labels[b] != labels[c]: continue
            normal_matrix = mesh.matrix_world.to_3x3().inverted().transposed()
            a_normal = (normal_matrix @ mesh.data.polygons[face].normal).normalized()
            b_normal = (normal_matrix @ mesh.data.polygons[other].normal).normalized()
            if a_normal.dot(b_normal) < .5: continue
            for u, v in ((a, d), (b, c)):
                if u != v:
                    edges.append((u, v)); conductance.append(10 / max(extent * .01, 1e-6)); join(u, v)
            report['verified_seam_edges'] += 1
    groups = defaultdict(list)
    for i in range(len(points)): groups[root(i)].append(i)
    seam_groups = [v for v in groups.values() if len(v) > 1]
    return edges, conductance, seam_groups, report


def rigid_components(weights,edges,scope,locked):
    """An explicit rigid-mesh mode: suggest single joints only for clear islands."""
    adjacency=[[] for _ in range(len(weights))]
    for a,b in edges:adjacency[a].append(int(b));adjacency[b].append(int(a))
    visited=np.zeros(len(weights),dtype=bool);assign=np.full(len(weights),-1,dtype=np.int32)
    accepted=ambiguous=0
    for start in range(len(weights)):
        if visited[start] or not scope[start]:continue
        stack=[start];visited[start]=True;vertices=[]
        while stack:
            vertex=stack.pop();vertices.append(vertex)
            for neighbor in adjacency[vertex]:
                if scope[neighbor] and not visited[neighbor]:visited[neighbor]=True;stack.append(neighbor)
        ids=np.asarray(vertices);rows=weights[ids];mean=rows.mean(axis=0);bone=int(mean.argmax())
        incompatible=locked.copy();incompatible[bone]=False
        # Neural certainty suggests a parent, not material rigidity. The artist
        # explicitly declares these meshes rigid by choosing this mode.
        if len(ids)<3 or mean[bone]<.82 or np.mean(rows[:,bone]>=.6)<.8 or np.any(rows[:,incompatible]>0) or (locked[bone] and np.any(rows[:,bone]!=1)):
            ambiguous+=1;continue
        assign[ids]=bone;accepted+=1
    return assign,dict(rigid_components_assigned=accepted,ambiguous_components_preserved=ambiguous)


def prepare_fields(context, rig, meshes, method='AUTO', selected_only=False, join_seams=True,voxel_resolution=48):
    if context.mode != 'OBJECT' or not meshes: raise ValueError('Select an accepted rig and character meshes in Object Mode')
    names = [b.name for b in rig.data.bones if b.use_deform]
    if not names: raise ValueError('No accepted deform bones')
    if rig.matrix_world.determinant() <= 1e-12 or any(m.parent_type != 'OBJECT' or m.matrix_world.determinant() <= 1e-12 for m in meshes):
        raise ValueError('Prepare bone-parented, mirrored or singular transforms on a working copy')
    if sum(len(m.data.vertices) for m in meshes) * len(names) * 6 > 512 * 1024 ** 2:
        raise ValueError('Refine smaller selections; dense fields exceed the 512 MiB input budget')
    if rig.constraints or any(b.constraints for b in rig.pose.bones): raise ValueError('Refine an accepted unconstrained deform rig')
    fields, reports = [], []
    for mesh in meshes:
        if not len(mesh.data.vertices): raise ValueError(f'{mesh.name}: empty geometry')
        if mesh.constraints or any(m.type != 'ARMATURE' and m.show_viewport for m in mesh.modifiers):
            raise ValueError(f'{mesh.name}: prepare constraints/modifiers on a working copy')
        if any(m.type == 'ARMATURE' and (m.object != rig or m.vertex_group or m.use_bone_envelopes or not m.use_vertex_groups)
               for m in mesh.modifiers): raise ValueError(f'{mesh.name}: use one unmasked vertex-group armature binding')
        original = dense_weights(mesh, names)
        geometric=method in {'GEODESIC','VOXEL'}
        totals=original.sum(axis=1);unbound=totals<=0
        if not np.isfinite(original).all() or (original < 0).any() or (unbound.any() and not geometric):
            raise ValueError(f'{mesh.name}: surface refinement needs existing valid weights; bind with AI or a baseline first')
        if np.max(np.abs(totals[~unbound] - 1),initial=0) > 1e-4:
            raise ValueError(f'{mesh.name}: normalize accepted weights before refinement')
        protected = group_mask(mesh, PROTECTED)
        locked = np.array([bool(mesh.vertex_groups.get(name) and mesh.vertex_groups[name].lock_weight) for name in names])
        labels, relabeled = joint_digit_labels(mesh, rig, original, names,geometric)
        selected = np.array([v.select for v in mesh.data.vertices]) if selected_only else np.ones(len(original), dtype=bool)
        editable = selected & ~protected
        if method == 'AUTO': editable &= labels != ''
        elif method=='RIGID_PARTS':editable[:]=False
        elif method not in {'SURFACE','GEODESIC','VOXEL'}: raise ValueError('Unsupported refinement method')
        rigid = np.full(len(original), -1, dtype=np.int32)
        for policy in json.loads(mesh.get(POLICIES, '[]')):
            mask = group_mask(mesh, policy['group']) & selected & ~protected
            if policy['kind'] == 'RIGID':
                if policy['bone'] not in names: raise ValueError(f"{mesh.name}: rigid region references a missing/nondeform bone")
                rigid[mask] = names.index(policy['bone']); editable[mask] = False
            else:
                rigid[mask] = -1
                editable[mask] = (labels[mask] != '') if policy['kind'] == 'AUTO' and method == 'AUTO' else True
                if policy.get('digit'): labels[mask] = policy['digit']
        allowed = np.ones(original.shape, dtype=bool)
        for family in set(labels) - {''}:
            side = 'Left' if family.startswith('Left') else 'Right'
            columns = [_digit(name) == family or canonical_name(name) in {side + 'Hand', side + 'ForeArm'} for name in names]
            if not any(columns): raise ValueError('Region digit is absent from the accepted rig')
            allowed[labels == family] = columns
        graph, conductance, seams, report = surface_graph(mesh, labels, join_seams)
        if method=='RIGID_PARTS':
            explicit=np.zeros(len(original),dtype=bool)
            for policy in json.loads(mesh.get(POLICIES,'[]')):explicit|=group_mask(mesh,policy['group'])
            suggested,diagnostic=rigid_components(original,graph,selected&~protected&~explicit,locked)
            chosen=suggested>=0;rigid[chosen]=suggested[chosen];report.update(diagnostic)
        if (unbound & (protected | (~editable & (rigid<0)))).any():raise ValueError('Unweighted protected or excluded vertices need an initial binding before regional refinement')
        field=dict(original=original, edges=graph, conductance=conductance, editable=editable,
                   locked=locked, protected=protected, allowed=allowed, rigid=rigid, seam_groups=seams)
        if geometric:
            mesh.data.calc_loop_triangles()
            field.update(points=np.array([tuple(mesh.matrix_world@v.co) for v in mesh.data.vertices]),
                heads=np.array([tuple(rig.matrix_world@rig.data.bones[n].head_local) for n in names]),
                tails=np.array([tuple(rig.matrix_world@rig.data.bones[n].tail_local) for n in names]),
                triangles=np.array([tuple(t.vertices) for t in mesh.data.loop_triangles],dtype=np.int64).reshape((-1,3)),
                geometry_method=np.array(2 if method=='VOXEL' else 1),voxel_resolution=np.array(voxel_resolution),digit_surface=labels!='')
        fields.append(field)
        report.update(mesh=mesh.name, method=method, digit_vertices=int(np.count_nonzero(labels != '')),
                      joint_evidence_relabels=relabeled,
                      rigid_vertices=int(np.count_nonzero(rigid >= 0)), protected_vertices=int(protected.sum()),
                      locked_bones=int(locked.sum()), body_policy='preserve_AI' if method == 'AUTO' else ('rigid_parts_preserve_ambiguous' if method=='RIGID_PARTS' else 'surface'))
        reports.append(report)
    return names, fields, reports


def refine(context, rig, meshes, method='AUTO', iterations=12, strength=.35, selected_only=False, join_seams=True):
    """Synchronous fixture/API entry; the interactive operator uses a worker."""
    from .weight_math import solve_region
    names, inputs, reports = prepare_fields(context, rig, meshes, method, selected_only, join_seams)
    fields = []
    for input_field, report in zip(inputs, reports):
        result, solve = solve_region(input_field, iterations, strength)
        report.update(solve)
        fields.append(result)
    method_name = rig.get('lc_skinning', 'accepted_weights') + '+regional_surface'
    return weight_copy.create(context, rig, meshes, names, fields, method=method_name, metadata=json.dumps(reports)), reports
