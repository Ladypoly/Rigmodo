# SPDX-License-Identifier: GPL-3.0-or-later
"""Original Rigmodo interchange; Meta code and checkpoints stay in an external provider."""
import hashlib
from pathlib import Path

SAM_REV = 'b5c765a0d89d789985e186d396315e7590887b94'
DINO_REV = '6876159a11b4df116f30f667f8c9888617df0751'
HF_REV = '11aaa346c7204874a1cbafe3d39a979080b2c55a'
MODEL_REPO = 'facebook/sam-3d-body-dinov3'
MODELS = {'model.ckpt': 'b5a2f9d305dd02626b967aa2e86021fba07065df66ce7a7e00ffb9664f150abf',
          'assets/mhr_model.pt': '352e271a6c42729c68554ceaea0c955e866970160c31e35506d782dc0f7377bc'}
ARCHIVES = {
    'source': ('sam-3d-body', SAM_REV, '58886285808df91b36f27216a58f76af7fc4770e1f94a3be612334ca69d64ef1'),
    'dinov3': ('dinov3', DINO_REV, '8f3ba3a5e4f017c4ae209cf3052ac3ffae714bc8308d1e541db7c6050294ece2')}
# Canonical target -> MHR joint with the accumulated anatomical rotation.
# Wrist twist and the ankle's collapsed joints must be included in lower-arm/foot rotation.
MAPPING = {'Hips':'root', 'Spine':'c_spine0', 'Spine1':'c_spine2', 'Spine2':'c_spine3',
           'Neck':'c_neck', 'Head':'c_head'}
DIRECTIONS = {}
for side, prefix in (('Left','l_'), ('Right','r_')):
    for target, source in (('Shoulder','clavicle'), ('Arm','uparm'), ('ForeArm','wrist_twist'),
                           ('Hand','wrist'), ('UpLeg','upleg'), ('Leg','lowleg'),
                           ('Foot','transversetarsal'), ('ToeBase','ball')):
        MAPPING[side+target] = prefix+source
    for target, start, end in (('Shoulder','clavicle','uparm'), ('Arm','uparm','lowarm'),
                              ('ForeArm','lowarm','wrist'), ('Hand','wrist','middle1')):
        DIRECTIONS[side+target] = (prefix+start, prefix+end)
    for finger in ('Thumb','Index','Middle','Ring','Pinky'):
        for i in (1,2,3):
            target = f'{side}Hand{finger}{i}'
            MAPPING[target] = f'{prefix}{finger.lower()}{i}'
            DIRECTIONS[target] = (MAPPING[target], prefix+finger.lower()+(str(i+1) if i<3 else '_null'))

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def source_files(provider):
    return {str(p.relative_to(provider)).replace('\\','/'):sha(p)
            for folder in ('source','dinov3') for p in sorted((provider/folder).rglob('*'))
            if p.is_file() and p.suffix in {'.py','.yaml','.yml','.json','.toml'}
            and '.git' not in p.parts and '__pycache__' not in p.parts}
