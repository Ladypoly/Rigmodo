# SPDX-License-Identifier: GPL-3.0-or-later
"""Contact discs and labels; no scene objects, pose writes or model inference."""
import json,math
import bpy
from mathutils import Vector
from . import character_context,motion_contacts,rig_mapping,processing_visuals

COLORS={'PLANTED':(.18,.88,.49,.30),'ROLLING':(1.,.62,.12,.22),'SLIDING':(1.,.62,.12,.22),'OFF FLOOR':(1.,.22,.22,.25),'AIRBORNE':(.50,.57,.65,.0)}
_handles=[]
_cache={}
_stats={'draws':0,'maximum_vertices':0}


def clear(*args):_cache.clear()


def sample(context,rig=None):
    settings=getattr(context.scene,'lc_settings',None)
    if not settings or not settings.show_contact_indicators:return []
    if rig is None:
        try:
            pinned=character_context.resolve(context)
            rig=pinned[0] if pinned else context.active_object
        except ValueError:return []
        if rig and rig.type=='MESH':rig=rig.find_armature()
    if not rig or rig.type!='ARMATURE' or not rig.visible_get():return []
    roles={r:b.name for r,b in zip(rig_mapping.names(rig),rig.data.bones)}
    if any(s+'Foot' not in roles for s in ('Left','Right')):return []
    action=rig.animation_data.action if rig.animation_data else None
    report=action.get('lc_contact_report','{}') if action else '{}';manual=rig.get('lc_sole_markers','{}')
    key=(rig.as_pointer(),action.as_pointer() if action else 0,report,manual,tuple(v for s in ('Left','Right') for row in rig.data.bones[roles[s+'Foot']].matrix_local for v in row))
    if _cache.get('key')!=key:
        if len(report)>1024**2:return []
        diagnostics=json.loads(report);supports=diagnostics.get('sole_markers',{})
        if manual!='{}' or any(s not in supports or supports[s].get('bone')!=roles[s+'Foot'] for s in ('Left','Right')):
            markers=motion_contacts.soles(context,rig,roles)
        else:markers={s:[Vector(p) for p in supports[s]['points']] for s in ('Left','Right')}
        _cache.clear();_cache.update(key=key,markers=markers,diagnostics=diagnostics)
    ground=settings.ground_height;fps=context.scene.render.fps/context.scene.render.fps_base
    seconds=(context.scene.frame_current+context.scene.frame_subframe-action.frame_start)/fps if action else 0.
    if action:seconds=max(0.,min(seconds,(action.frame_end-action.frame_start)/fps))
    edits=json.loads(action.get('lc_contact_overrides','[]')) if action else [];items=[]
    for side in ('Left','Right'):
        foot=rig.pose.bones[roles[side+'Foot']];points=[rig.matrix_world@foot.matrix@p for p in _cache['markers'][side]]
        height=min(p.z for p in points)-ground;spread=abs(points[1].z-points[0].z)
        intervals=_cache['diagnostics'].get('intervals',[])
        expected=next((p['mode'] for p in intervals if p['side']==side and p['start']-1e-4<=seconds<=p['end']+1e-4),None)
        for edit in edits:
            if edit['side']==side and edit['start']<=seconds<=edit['end']:expected=edit['mode']
        if height<-.012 or (expected in {'PLANT','SLIDE'} and height>.015):state='OFF FLOOR'
        elif abs(height)<=.012:state='SLIDING' if expected=='SLIDE' else 'ROLLING' if spread>.018 else 'PLANTED'
        else:state='AIRBORNE'
        center=(points[0]+points[1])*.5;center.z=ground+.002
        forward=points[1]-points[0];forward.z=0
        if forward.length<1e-5:forward=Vector((0,-1,0))
        radius=max(.06,min(.3,forward.length*.5+.025));forward.normalize();across=forward.cross(Vector((0,0,1)))
        ring=[center+forward*(radius*math.cos(i*math.tau/32))+across*(radius*.55*math.sin(i*math.tau/32)) for i in range(32)]
        items.append(dict(side=side,state=state,height=height,center=center,ring=ring,color=COLORS[state]))
    return items


def draw_world():
    context=bpy.context
    if not context.space_data or context.space_data.type!='VIEW_3D' or not context.space_data.overlay.show_overlays:return
    try:items=sample(context)
    except (ValueError,KeyError,TypeError,IndexError,ReferenceError,AttributeError):return
    if not items:return
    import gpu
    from gpu_extras.batch import batch_for_shader
    blend,depth,mask=gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
    try:
        gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE');gpu.state.depth_mask_set(False)
        fill=processing_visuals.shader('UNIFORM_COLOR');line=processing_visuals.shader('POLYLINE_SMOOTH_COLOR')
        for item in items:
            ring=item['ring'];vertices=[p for i in range(32) for p in (item['center'],ring[i],ring[(i+1)%32])]
            if item['color'][3]:
                fill.bind();fill.uniform_float('color',item['color']);batch_for_shader(fill,'TRIS',{'pos':vertices}).draw(fill)
            vertices=[p for i in range(32) if item['state']!='AIRBORNE' or i%2==0 for p in (ring[i],ring[(i+1)%32])]
            line.bind();line.uniform_float('viewportSize',gpu.state.viewport_get()[2:]);line.uniform_float('lineWidth',2.)
            batch_for_shader(line,'LINES',{'pos':vertices,'color':[(*item['color'][:3],.95)]*len(vertices)}).draw(line)
            _stats['maximum_vertices']=max(_stats['maximum_vertices'],96+len(vertices))
        _stats['draws']+=1
    finally:gpu.state.blend_set(blend);gpu.state.depth_test_set(depth);gpu.state.depth_mask_set(mask)


def draw_hud():
    context=bpy.context
    if not context.space_data or context.space_data.type!='VIEW_3D' or not context.space_data.overlay.show_overlays:return
    try:items=sample(context)
    except (ValueError,KeyError,TypeError,IndexError,ReferenceError,AttributeError):return
    if not items:return
    import blf
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    for item in items:
        xy=location_3d_to_region_2d(context.region,context.region_data,item['center'])
        if xy is None:continue
        text=('L' if item['side']=='Left' else 'R')+' · '+item['state'].title()
        blf.size(0,11);blf.color(0,*item['color'][:3],1.);blf.position(0,xy.x+8,xy.y-18,0);blf.draw(0,text)


def register():
    if bpy.app.background or _handles:return
    _handles.extend((bpy.types.SpaceView3D.draw_handler_add(draw_world,(),'WINDOW','POST_VIEW'),bpy.types.SpaceView3D.draw_handler_add(draw_hud,(),'WINDOW','POST_PIXEL')))


def unregister():
    for handle in _handles:bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
    _handles.clear();clear()
