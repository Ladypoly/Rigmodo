# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent CPU diffusion and exact protection constraints (NumPy only)."""
import numpy as np


def solve_region(field, iterations=12, strength=.35):
    original, locked, protected, rigid = (np.asarray(field[k]) for k in ('original', 'locked', 'protected', 'rigid'))
    result, report = surface_diffusion(original, field['edges'], field['conductance'], field['editable'],
                                      locked, protected, field['allowed'], iterations, strength, field['seam_groups'])
    for vertex in np.flatnonzero(rigid >= 0):
        bone = int(rigid[vertex])
        if protected[vertex]: raise ValueError('Protected region cannot be rebound')
        if bone >= original.shape[1]: raise ValueError('Rigid bone exceeds accepted skeleton')
        if any(original[vertex, i] > 0 for i in np.flatnonzero(locked) if i != bone):
            raise ValueError('Locked influences conflict with exact rigid binding; unlock or protect this region')
        if locked[bone] and original[vertex, bone] != 1: raise ValueError('Locked target weight prevents exact rigid binding')
        result[vertex] = 0; result[vertex, bone] = 1
    if not np.array_equal(result[protected], original[protected]): raise RuntimeError('Protected weights changed')
    if locked.any() and not np.array_equal(result[:, locked], original[:, locked]): raise RuntimeError('Locked weights changed')
    report['maximum_weight_change'] = float(np.max(np.abs(result - original))) if len(original) else 0
    return result, report


def constrained_weights(proposal, original, locked, protected, allowed=None):
    proposal = np.asarray(proposal, dtype=np.float32).copy()
    original = np.asarray(original, dtype=np.float32)
    locked = np.asarray(locked, dtype=bool)
    protected = np.asarray(protected, dtype=bool)
    if proposal.shape != original.shape or locked.shape != (proposal.shape[1],) or protected.shape != (proposal.shape[0],):
        raise ValueError('Weight constraint arrays disagree')
    if not np.isfinite(proposal).all() or not np.isfinite(original).all() or (original < 0).any():
        raise ValueError('Nonfinite or negative weight data')
    proposal = np.maximum(proposal, 0)
    if allowed is not None:
        if allowed.shape != proposal.shape: raise ValueError('Region/bone mask shape mismatch')
        proposal *= allowed
    proposal[:, locked] = 0
    frozen = original[:, locked].sum(axis=1)
    if (frozen[~protected] > 1 + 1e-6).any(): raise ValueError('Locked weights exceed one; correct them before refinement')
    remaining = np.maximum(1 - frozen, 0)
    total = proposal.sum(axis=1)
    missing = (total <= 1e-12) & (remaining > 1e-6) & ~protected
    fallback = original.copy()
    if allowed is not None: fallback *= allowed
    fallback[:, locked] = 0
    proposal[missing] = fallback[missing]
    total = proposal.sum(axis=1)
    if ((total <= 1e-12) & (remaining > 1e-6) & ~protected).any():
        raise ValueError('Region excludes every available influence; choose a binding baseline or correct its bone mask')
    proposal *= (remaining / np.maximum(total, 1e-12))[:, None]
    proposal[:, locked] = original[:, locked]
    proposal[protected] = original[protected]
    return proposal


def surface_diffusion(original, edges, conductance, editable, locked, protected, allowed,
                      iterations=12, strength=.35, seam_groups=()):
    """Bounded graph heat steps anchored to the accepted input field.

    Edges describe actual surface adjacency, plus independently verified seams.
    There are no spatial nearest-neighbor edges between disconnected surfaces.
    """
    original = np.asarray(original, dtype=np.float32)
    editable = np.asarray(editable, dtype=bool)
    protected = np.asarray(protected, dtype=bool) | ~editable
    edges = np.asarray(edges, dtype=np.int64).reshape((-1, 2))
    conductance = np.asarray(conductance, dtype=np.float32)
    if not 1 <= iterations <= 200 or not 0 < strength <= 1: raise ValueError('Invalid diffusion settings')
    if len(edges) != len(conductance) or (conductance <= 0).any() or not np.isfinite(conductance).all():
        raise ValueError('Invalid surface graph conductance')
    if len(edges) and (edges.min() < 0 or edges.max() >= len(original)): raise ValueError('Surface graph exceeds vertex bounds')
    source = np.concatenate((edges[:, 0], edges[:, 1]))
    target = np.concatenate((edges[:, 1], edges[:, 0]))
    weight = np.concatenate((conductance, conductance))
    degree = np.zeros(len(original), dtype=np.float32)
    np.add.at(degree, target, weight)
    active = editable & (degree > 0)
    protected |= ~active
    current = constrained_weights(original, original, locked, protected, allowed)
    seam_conflicts = 0
    compatible_seams = []
    for group in seam_groups:
        group = np.asarray(group, dtype=np.int64)
        if not np.all(allowed[group] == allowed[group[0]]): continue
        if locked.any() and np.max(np.abs(original[group][:, locked] - original[group[0], locked])) > 1e-6:
            seam_conflicts += 1; continue
        fixed = group[protected[group]]
        if len(fixed) > 1 and np.max(np.abs(original[fixed] - original[fixed[0]])) > 1e-6:
            seam_conflicts += 1; continue
        compatible_seams.append((group, fixed))
    for _ in range(iterations):
        neighbors = np.zeros_like(current)
        # Bound temporary gather/scatter memory on dense production meshes.
        for start in range(0, len(source), 32768):
            end = start + 32768
            np.add.at(neighbors, target[start:end], current[source[start:end]] * weight[start:end, None])
        neighbors /= np.maximum(degree, 1e-12)[:, None]
        proposal = current.copy()
        proposal[active] = (1 - strength) * current[active] + strength * neighbors[active]
        proposal[active] = .95 * proposal[active] + .05 * original[active]
        current = constrained_weights(proposal, original, locked, protected, allowed)
        for group, fixed in compatible_seams:
            shared = original[fixed[0]] if len(fixed) else current[group].mean(axis=0)
            current[group[~protected[group]]] = shared
    return current, {'iterations': iterations, 'editable_vertices': int(active.sum()),
                     'seam_constraint_conflicts': seam_conflicts,
                     'maximum_weight_change': float(np.max(np.abs(current - original))) if len(original) else 0}
