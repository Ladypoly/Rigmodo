# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent analytic two-bone IK; no persistent rig constraints."""
import math
from mathutils import Vector

def two_bone(hip,knee,end,goal,pole):
    hip,knee,end,goal,pole=map(Vector,(hip,knee,end,goal,pole))
    a=(knee-hip).length;b=(end-knee).length
    if min(a,b)<1e-6:raise ValueError('IK needs two nonzero limb segments')
    delta=goal-hip;requested=delta.length
    if requested<1e-8:delta=knee-hip;requested=0.
    direction=delta.normalized()
    distance=min(max(requested,abs(a-b)+1e-6),a+b-1e-6)
    along=(a*a-b*b+distance*distance)/(2*distance)
    perpendicular=knee-hip;perpendicular-=direction*perpendicular.dot(direction)
    if perpendicular.length<1e-6:perpendicular=pole-direction*pole.dot(direction)
    if perpendicular.length<1e-6:perpendicular=direction.cross(Vector((1,0,0)))
    if perpendicular.length<1e-6:perpendicular=direction.cross(Vector((0,0,1)))
    new_knee=hip+direction*along+perpendicular.normalized()*math.sqrt(max(0,a*a-along*along))
    new_end=hip+direction*distance
    return new_knee,new_end,requested<abs(a-b)+1e-6 or requested>a+b-1e-6
