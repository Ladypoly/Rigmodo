# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic editable finger controls; motion model supplies no fingers."""
import math
from . import skeleton

PRESETS={'OPEN':(0,0,0,0,0),'RELAXED':(.2,.2,.3,.35,.4),'FIST':(.85,1,1,1,1),
         'POINT':(.55,0,.9,.9,.9),'GRIP':(.65,.6,.7,.75,.75)}

def angles(canonical,controls):
    if not controls:return None
    for side in ('Left','Right'):
        for finger in skeleton.FINGERS:
            prefix=side+'Hand'+finger
            if canonical.startswith(prefix) and canonical[-1:] in '123':
                value=float(controls.get(side,{}).get(finger,0))
                if not math.isfinite(value) or not 0<=value<=1:raise ValueError('Finger curl must be 0–1')
                return math.radians((45,65,45)[int(canonical[-1])-1])*value
    return None

def settings(settings):
    return {side:{finger:getattr(settings,'hand_'+side.lower()+'_'+finger.lower()) for finger in skeleton.FINGERS}
            for side in ('Left','Right')}
