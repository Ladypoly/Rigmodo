# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural, exact-FK multi-effector posing. No RNA writes during a solve.

Joint rotations are optimized on the actual rest-offset tree. Pin tasks have
priority over the selected target; mobility regularizes minimum-change steps.
Unlike free particles, this representation cannot stretch or detach joints.
"""
import math
import time
from dataclasses import dataclass
import numpy as np
from mathutils import Matrix, Quaternion, Vector
from . import skeleton

BODY = tuple(skeleton.BODY) + tuple(s + n for s in ('Left', 'Right') for n in skeleton.LIMBS)
AXES = np.eye(3)


def rotvec(matrix):
    q = Matrix(matrix.tolist()).to_quaternion().normalized()
    if q.w < 0:
        q.negate()
    v = np.array((q.x, q.y, q.z))
    length = np.linalg.norm(v)
    return v * (2 * math.atan2(length, q.w) / length) if length > 1e-10 else 2 * v


def exp_rotation(v):
    angle = float(np.linalg.norm(v))
    if angle < 1e-12:
        return np.eye(3)
    return np.array(Quaternion(Vector(v / angle), angle).to_matrix(), dtype=float)


@dataclass
class PoseResult:
    bases: dict
    target_error: float
    pin_error: float
    orientation_error: float
    limited: bool
    milliseconds: float
    iterations: int


class Model:
    """Per-gesture indexed skeleton and immutable authored-pose reference."""
    def __init__(self, rig, bases, pins=None, joint_limits=True, body_follow=True):
        self.rig = rig
        self.bones = sorted(rig.data.bones, key=lambda b: len(b.parent_recursive))
        self.names = [b.name for b in self.bones]
        self.index = {n: i for i, n in enumerate(self.names)}
        self.semantic = {skeleton.canonical_name(n): i for i, n in enumerate(self.names)}
        self.parents = [self.index[b.parent.name] if b.parent else -1 for b in self.bones]
        self.rest_r = []
        self.rest_t = []
        for b in self.bones:
            relative = b.parent.matrix_local.inverted() @ b.matrix_local if b.parent else b.matrix_local
            self.rest_r.append(np.array(relative.to_3x3(), dtype=float))
            self.rest_t.append(np.array(relative.translation, dtype=float))
        self.rest_r = np.array(self.rest_r)
        self.rest_t = np.array(self.rest_t)
        self.initial = {n: b.copy() for n, b in bases.items()}
        self.reference_r = np.array([bases[n].to_3x3() for n in self.names], dtype=float)
        self.reference_t = np.array([bases[n].translation for n in self.names], dtype=float)
        self.hips = self.semantic['Hips']
        rest_height = max(b.tail_local.z for b in self.bones) - min(b.head_local.z for b in self.bones)
        self.height = max(rest_height, sum(rig.data.bones[self.names[self.semantic['Left' + s]]].length for s in ('UpLeg', 'Leg')), .01)
        self.reference = self.fk(self.reference_r, self.reference_t)
        self.pins = {self.semantic[n]: mode for n, mode in (pins or {}).items()}
        self.joint_limits = joint_limits
        self.body_follow = body_follow
        self.dofs = []
        self.mobility = []
        if self.hips not in self.pins:
            for axis in range(3):
                self.dofs.append((self.hips, axis, True))
                self.mobility.append(.18 if body_follow else 0.)
        for name in BODY:
            if name not in self.semantic:
                continue
            i = self.semantic[name]
            if i in self.pins and self.pins[i] == 'FRAME' and name == 'Hips':
                continue
            mobility = 1.
            if name in ('Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head'):
                mobility = .22 if body_follow else 0.
            elif name.endswith('Shoulder'):
                mobility = .4 if body_follow else 0.
            for axis in range(3):
                self.dofs.append((i, axis, False))
                # Axial spin in hinge-like joints is more expensive than swing.
                self.mobility.append(mobility * (.2 if axis == 1 and name.endswith(('Leg', 'ForeArm')) else 1.))
        self.mobility = np.array(self.mobility)
        self.ancestors = []
        for i in range(len(self.names)):
            chain = set()
            p = i
            while p >= 0:
                chain.add(p)
                p = self.parents[p]
            self.ancestors.append(chain)
        self.limits = [self._limits(skeleton.canonical_name(n), self.reference_r[i]) for i, n in enumerate(self.names)]

    @staticmethod
    def _limits(name, reference):
        swing, twist = (180, 180)
        if name.startswith('Spine'): swing, twist = 40, 60
        elif name == 'Neck': swing, twist = 65, 90
        elif name == 'Head': swing, twist = 55, 90
        elif name.endswith('Shoulder'): swing, twist = 65, 100
        elif name.endswith('ForeArm'): swing, twist = 165, 150
        elif name.endswith('UpLeg'): swing, twist = 135, 90
        elif name.endswith('Leg'): swing, twist = 165, 40
        elif name.endswith('Hand'): swing, twist = 85, 100
        elif name.endswith('Foot'): swing, twist = 60, 55
        elif name.endswith('ToeBase'): swing, twist = 60, 30
        q = Matrix(reference.tolist()).to_quaternion()
        sy = max(-1., min(1., float(reference[1, 1])))
        initial_swing = math.acos(sy)
        initial_twist = abs(2 * math.atan2(q.y, q.w))
        initial_twist = min(initial_twist, 2 * math.pi - initial_twist)
        # Enabling must preserve an existing authored pose, including unusual ones.
        return max(math.radians(swing), initial_swing + 1e-4), max(math.radians(twist), initial_twist + 1e-4)

    def fk(self, rotations, translations):
        rs = np.empty_like(rotations)
        ps = np.empty_like(translations)
        for i, parent in enumerate(self.parents):
            inherited = rs[parent] @ self.rest_r[i] if parent >= 0 else self.rest_r[i]
            rs[i] = inherited @ rotations[i]
            ps[i] = (ps[parent] + rs[parent] @ self.rest_t[i] if parent >= 0 else self.rest_t[i]) + inherited @ translations[i]
        return rs, ps

    def task(self, i, goal, orientation, state):
        rs, ps = state
        errors = [(np.array(goal) - ps[i]) / self.height]
        jac = np.zeros((3 if orientation is None else 6, len(self.dofs)))
        if orientation is not None:
            errors.append(rotvec(np.array(orientation) @ rs[i].T))
        for k, (joint, axis, translation) in enumerate(self.dofs):
            if joint not in self.ancestors[i]:
                continue
            if translation:
                parent = self.parents[joint]
                direction = (rs[parent] @ self.rest_r[joint] if parent >= 0 else self.rest_r[joint])[:, axis]
                jac[:3, k] = direction
            else:
                direction = rs[joint][:, axis]
                jac[:3, k] = np.cross(direction, ps[i] - ps[joint]) / self.height
                if orientation is not None:
                    jac[3:, k] = direction
        return np.concatenate(errors), jac * self.mobility

    def pin_task(self, state):
        errors, jac = [], []
        for i, mode in self.pins.items():
            e, j = self.task(i, self.reference[1][i], self.reference[0][i] if mode == 'FRAME' else None, state)
            errors.append(e); jac.append(j)
        return (np.concatenate(errors), np.vstack(jac)) if errors else (np.zeros(0), np.zeros((0, len(self.dofs))))

    def _project_limits(self, rotations):
        if not self.joint_limits:
            return
        for i in set(j for j, _, t in self.dofs if not t):
            q = Matrix(rotations[i].tolist()).to_quaternion().normalized()
            if q.w < 0: q.negate()
            norm = math.hypot(q.w, q.y)
            twist = Quaternion((q.w / norm, 0, q.y / norm, 0)) if norm > 1e-8 else Quaternion()
            swing = q @ twist.conjugated()
            swing_limit, twist_limit = self.limits[i]
            if swing.angle > swing_limit:
                swing = Quaternion(swing.axis, swing_limit)
            angle = 2 * math.atan2(twist.y, twist.w)
            twist = Quaternion((0, 1, 0), max(-twist_limit, min(twist_limit, angle)))
            rotations[i] = np.array((swing @ twist).to_matrix())

    def _step(self, rotations, translations, delta):
        deltas = np.zeros((len(self.names), 3))
        for value, (i, axis, translation) in zip(delta * self.mobility, self.dofs):
            if translation:
                translations[i, axis] += value * self.height
            else:
                deltas[i, axis] += value
        for i in np.flatnonzero(np.linalg.norm(deltas, axis=1) > 1e-12):
            rotations[i] = rotations[i] @ exp_rotation(deltas[i])
        self._project_limits(rotations)

    def _seed(self, rotations, active, goal):
        """Escape a straight-limb shortening singularity in a stable bend plane."""
        name = skeleton.canonical_name(self.names[active])
        if name.endswith('Hand'): upper, lower, preferred = 'Arm', 'ForeArm', np.array((0., 0., -1.))
        elif name.endswith('Foot'): upper, lower, preferred = 'UpLeg', 'Leg', np.array((0., -1., 0.))
        else: return
        side = 'Left' if name.startswith('Left') else 'Right'
        a, b = self.semantic[side + upper], self.semantic[side + lower]
        rs, ps = self.reference
        v1, v2 = ps[b] - ps[a], ps[active] - ps[b]
        if np.linalg.norm(np.cross(v1, v2)) > self.height ** 2 * .001 or np.linalg.norm(goal - ps[a]) >= np.linalg.norm(ps[active] - ps[a]):
            return
        axis = np.cross(v1 / np.linalg.norm(v1), preferred)
        if np.linalg.norm(axis) < 1e-5: return
        axis /= np.linalg.norm(axis)
        rotations[a] = rotations[a] @ exp_rotation(rs[a].T @ axis * -.025)
        rotations[b] = rotations[b] @ exp_rotation(rs[b].T @ axis * .05)

    def solve(self, active, target, orientation=None, iterations=32):
        start = time.perf_counter()
        i = self.semantic[active]
        goal = np.array(target, dtype=float)
        orient = np.array(orientation, dtype=float) if orientation is not None else None
        if not np.isfinite(goal).all() or (orient is not None and not np.isfinite(orient).all()):
            raise ValueError('Pose target must be finite')
        # Every mouse sample starts at the same authored pose: no drift/history dependence.
        rotations = self.reference_r.copy(); translations = self.reference_t.copy()
        best_r, best_t = rotations.copy(), translations.copy()
        best_score = float('inf')
        self._seed(rotations, i, goal)
        count = 0
        for count in range(iterations):
            state = self.fk(rotations, translations)
            pe, pj = self.pin_task(state)
            te, tj = self.task(i, goal, orient, state)
            pin_norm = max(np.abs(pe), default=0.)
            score = np.linalg.norm(te)
            if pin_norm < 1e-5 and score < best_score:
                best_r, best_t, best_score = rotations.copy(), translations.copy(), score
            if score < 2e-5 and pin_norm < 2e-6:
                break
            n = len(self.dofs)
            if not n: break
            # Hierarchical least squares: target cannot trade away explicit pins.
            if len(pe):
                inverse = np.linalg.pinv(pj, rcond=1e-5)
                primary = inverse @ pe
                null = np.eye(n) - inverse @ pj
            else:
                primary = np.zeros(n); null = np.eye(n)
            reduced = tj @ null
            damping = .002
            secondary = reduced.T @ np.linalg.solve(reduced @ reduced.T + np.eye(len(te)) * damping ** 2, te - tj @ primary)
            delta = primary + null @ secondary
            # Cap the entire step uniformly to preserve its priority projection.
            largest = max(np.abs(delta * self.mobility), default=0.)
            if largest > .18: delta *= .18 / largest
            self._step(rotations, translations, delta)
        # Project pins without a target for a bounded number of cleanup iterations.
        for _ in range(12):
            pe, pj = self.pin_task(self.fk(rotations, translations))
            if max(np.abs(pe), default=0.) < 2e-6: break
            delta = np.linalg.pinv(pj, rcond=1e-5) @ pe
            largest = max(np.abs(delta * self.mobility), default=0.)
            if largest > .12: delta *= .12 / largest
            self._step(rotations, translations, delta)
        state = self.fk(rotations, translations)
        pe, _ = self.pin_task(state)
        te, _ = self.task(i, goal, orient, state)
        if max(np.abs(pe), default=0.) > 1e-5 or not np.isfinite(rotations).all() or np.linalg.norm(te) > best_score + 1e-5:
            rotations, translations = best_r, best_t
            state = self.fk(rotations, translations)
        result_bases = {n: m.copy() for n, m in self.initial.items()}
        for j in set(k for k, _, _ in self.dofs):
            m = Matrix(rotations[j].tolist()).to_4x4()
            m.translation = Vector(translations[j])
            result_bases[self.names[j]] = m
        # Report actual FK error, in armature units, rather than a particle proxy.
        position_error = float(np.linalg.norm(goal - state[1][i]))
        pin_error = max((float(np.linalg.norm(self.reference[1][j] - state[1][j])) for j in self.pins), default=0.)
        pin_angle = max((float(np.linalg.norm(rotvec(self.reference[0][j] @ state[0][j].T))) for j, mode in self.pins.items() if mode == 'FRAME'), default=0.)
        orientation_error = float(np.linalg.norm(rotvec(orient @ state[0][i].T))) if orient is not None else 0.
        if pin_error > self.height * 2e-5 or pin_angle > 2e-5:
            raise ValueError('Pose would move a pinned joint; keep the previous valid pose')
        return PoseResult(result_bases, position_error, pin_error, orientation_error,
                          position_error > self.height * .002 or orientation_error > .01,
                          (time.perf_counter() - start) * 1000, count + 1)
