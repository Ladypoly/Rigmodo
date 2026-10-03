# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded SOMA motion transport, forward kinematics and contact diagnostics."""
import json
from pathlib import Path
import numpy as np

SPEC = json.loads(Path(__file__).with_name('soma30.json').read_text())
NAMES = SPEC['names']
PARENTS = SPEC['parents']
OFFSETS = np.asarray(SPEC['offsets'], dtype=np.float64)
Y_TO_Z = np.array([[1., 0, 0], [0, 0, -1.], [0, 1., 0]])
MAPPING = dict(Hips='Hips', Spine='Spine1', Spine1='Spine2', Spine2='Chest',
               Neck='Neck1', Head='Head', Jaw='Jaw', LeftEye='LeftEye', RightEye='RightEye')
for side in ('Left', 'Right'):
    MAPPING.update({side + part: side + part for part in ('Shoulder', 'Arm', 'ForeArm', 'Hand', 'Foot', 'ToeBase')})
    MAPPING[side + 'UpLeg'] = side + 'Leg'
    MAPPING[side + 'Leg'] = side + 'Shin'
DIRECTION_CHILD = dict(Hips='Spine1', Spine1='Spine2', Spine2='Chest', Chest='Neck1',
    Neck1='Neck2', Head=None, Jaw=None, LeftEye=None, RightEye=None)
for side in ('Left', 'Right'):
    for parent, child in [('Shoulder','Arm'), ('Arm','ForeArm'), ('ForeArm','Hand'),
                          ('Hand','HandMiddleEnd'), ('Leg','Shin'), ('Shin','Foot'), ('Foot','ToeBase')]:
        DIRECTION_CHILD[side + parent] = side + child
    DIRECTION_CHILD[side + 'ToeBase'] = None


def load(folder, frames):
    folder = Path(folder)
    if not isinstance(frames, int) or not 2 <= frames <= 1800:
        raise ValueError('Motion must contain 2–1800 frames')
    paths = [folder/'root_positions.f32', folder/'local_rotations_xyzw.f32']
    counts = [frames * 3, frames * 30 * 4]
    for path, count in zip(paths, counts):
        if path.stat().st_size != count * 4: raise ValueError('Motion array size does not match the request')
    root = np.fromfile(paths[0], dtype='<f4').reshape(frames, 3).astype(np.float64)
    rotations = np.fromfile(paths[1], dtype='<f4').reshape(frames, 30, 4).astype(np.float64)
    if not np.isfinite(root).all() or not np.isfinite(rotations).all(): raise ValueError('Nonfinite motion output')
    lengths = np.linalg.norm(rotations, axis=-1)
    if (np.abs(lengths - 1) > .01).any(): raise ValueError('Motion contains invalid rotation quaternions')
    if np.abs(root).max() > 1000: raise ValueError('Implausible motion coordinates')
    rotations /= lengths[..., None]
    # Quaternion sign changes represent the same rotation but cause bad curve interpolation.
    for frame in range(1, frames):
        flipped = np.sum(rotations[frame] * rotations[frame-1], axis=-1) < 0
        rotations[frame, flipped] *= -1
    return root, rotations


def matrices(xyzw):
    x,y,z,w = np.moveaxis(xyzw, -1, 0)
    result = np.empty(xyzw.shape[:-1] + (3,3))
    result[...,0,0]=1-2*(y*y+z*z); result[...,0,1]=2*(x*y-z*w); result[...,0,2]=2*(x*z+y*w)
    result[...,1,0]=2*(x*y+z*w); result[...,1,1]=1-2*(x*x+z*z); result[...,1,2]=2*(y*z-x*w)
    result[...,2,0]=2*(x*z-y*w); result[...,2,1]=2*(y*z+x*w); result[...,2,2]=1-2*(x*x+y*y)
    return result


def forward(root, xyzw):
    local = matrices(xyzw)
    global_rot = np.empty_like(local); positions = np.empty((len(root),30,3))
    for i, parent in enumerate(PARENTS):
        if parent < 0: global_rot[:,i] = local[:,i]; positions[:,i] = root
        else:
            global_rot[:,i] = global_rot[:,parent] @ local[:,i]
            positions[:,i] = positions[:,parent] + np.einsum('tij,j->ti',global_rot[:,parent],OFFSETS[i])
    return positions, global_rot


def direction(name):
    child = DIRECTION_CHILD[name]
    if child: value = OFFSETS[NAMES.index(child)]
    elif name.endswith('ToeBase'): value = np.array([0.,0.,1.])
    elif name in ('LeftEye','RightEye','Jaw'): value = np.array([0.,0.,1.])
    else: value = np.array([0.,1.,0.])
    value = Y_TO_Z @ value
    return value / np.linalg.norm(value)


def diagnostics(root, rotations):
    positions, _ = forward(root, rotations)
    feet = positions[:,[NAMES.index('LeftFoot'),NAMES.index('RightFoot')]]
    speed = np.linalg.norm(np.diff(feet,axis=0),axis=-1) * 30
    floor = float(np.percentile(feet[...,1], 5))
    contacts = (feet[:-1,:,1] < floor + .06) & (speed < .15)
    return dict(frames=len(root),fps=30, source_floor_estimate_m=floor,
                travel_m=float(np.linalg.norm((root[-1]-root[0])[[0,2]])),
                contact_frames=[int(v) for v in contacts.sum(axis=0)],
                contact_max_speed_m_s=float(speed[contacts].max()) if contacts.any() else None,
                source_height_range_m=[float(root[:,1].min()),float(root[:,1].max())])


def contact_masks(root,rotations):
    positions,_=forward(root,rotations)
    feet=positions[:,[NAMES.index('LeftFoot'),NAMES.index('RightFoot')]]
    speed=np.linalg.norm(np.diff(feet,axis=0),axis=-1)*30
    floor=np.percentile(feet[...,1],5)
    masks=np.zeros((len(root),2),dtype=bool)
    masks[:-1]=(feet[:-1,:,1]<floor+.06)&(speed<.15)
    for foot in range(2):
        indices=np.flatnonzero(masks[:,foot])
        for group in np.split(indices,np.flatnonzero(np.diff(indices)>1)+1):
            if len(group)<4:masks[group,foot]=False
    return masks
