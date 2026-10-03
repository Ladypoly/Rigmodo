# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent rest-geometry edge strain probes for learned binding review."""
import numpy as np
from mathutils import Matrix
from . import skeleton,regions

def inspect(rig,meshes):
    if sum(len(m.data.vertices) for m in meshes)>250000:
        return [dict(mesh='selection',probes=[],skipped='Automatic strain review exceeds 250,000 vertices; review smaller mesh scopes')]
    names=[b.name for b in rig.data.bones if b.use_deform];mapping={skeleton.canonical_name(n):n for n in names}
    from . import twists
    modules=twists.modules(rig)
    results=[]
    for mesh in meshes:
        matrix=np.array(mesh.matrix_world);points=np.array([tuple(v.co) for v in mesh.data.vertices]);points=points@matrix[:3,:3].T+matrix[:3,3]
        edges=np.array([tuple(e.vertices) for e in mesh.data.edges],dtype=np.int64).reshape((-1,2))
        extent=float(np.ptp(points,axis=0).max());lengths=np.linalg.norm(points[edges[:,0]]-points[edges[:,1]],axis=1)
        edges=edges[lengths>max(extent*1e-4,1e-7)];lengths=lengths[lengths>max(extent*1e-4,1e-7)]
        weights=regions.dense_weights(mesh,names);probes=[]
        for canonical in [s+p for s in ('Left','Right') for p in ('ForeArm','Leg','HandIndex1')]+['Head']:
            if canonical not in mapping or not len(edges):continue
            bone=rig.data.bones[mapping[canonical]];branch={bone.name,*[b.name for b in bone.children_recursive]}
            # A pure local-X probe is full swing, so the optional sibling
            # forearm helper follows its source exactly despite sibling ancestry.
            branch.update(m['helper'] for m in modules if m['source'] in branch)
            influence=weights[:,[i for i,n in enumerate(names) if n in branch]].sum(axis=1)
            rest=rig.matrix_world@bone.matrix_local
            transform=np.array(rest@Matrix.Rotation(np.deg2rad(60),4,'X')@rest.inverted())
            rotated=points@transform[:3,:3].T+transform[:3,3];posed=points+influence[:,None]*(rotated-points)
            ratio=np.linalg.norm(posed[edges[:,0]]-posed[edges[:,1]],axis=1)/lengths
            probes.append(dict(joint=canonical,maximum_edge_stretch=float(ratio.max()),p99_edge_stretch=float(np.percentile(ratio,99)),
                fraction_over_2=float(np.mean(ratio>2)),fraction_over_5=float(np.mean(ratio>5))))
        results.append(dict(mesh=mesh.name,vertices=len(points),probes=probes))
    return results

def findings(report):
    severe=[];warnings=[]
    for mesh in report:
        if mesh.get('skipped'):severe.append(mesh['skipped'])
        for probe in mesh['probes']:
            text=f"{mesh['mesh']}: {probe['joint']} probe stretches edges up to {probe['maximum_edge_stretch']:.1f}×"
            if probe['fraction_over_5']>=.005 or probe['p99_edge_stretch']>3:severe.append(text)
            elif probe['maximum_edge_stretch']>5:warnings.append(text)
    return severe,warnings
