# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded, viewport-only feedback. Never polls workers or writes artist data."""
import math
import time
import uuid
from dataclasses import dataclass, field

import bpy
from bpy.app.handlers import persistent
from bpy.types import Operator
from mathutils import Vector
from . import configuration, skinning

FPS=8
MAX_BONES=192
MAX_MESHES=64
COLORS={'RIG':(.22,.82,1.),'SKIN':(.18,1.,.69),'MOTION':(.72,.49,1.),
        'IMAGE':(1.,.72,.26),'SETUP':(.22,.82,1.),'SUCCESS':(.36,1.,.61)}
_sessions={}
_handles=[]
_shaders={}
_stats={'ticks':0,'draws':0,'geometry_builds':0,'max_vertices':0,'tick_ms':0.,'draw_ms':0.,'hud_ms':0.}

@dataclass
class Session:
    scene:object
    kind:str
    folder:str
    rig:object=None
    meshes:tuple=()
    run:object=None
    started:float=field(default_factory=time.monotonic)
    cancel_requested:bool=False
    completed:float=0.
    phase:str='Working locally'
    geometry_key:tuple=()
    bones:list=field(default_factory=list)
    bounds:tuple=()
    batches:tuple=()
    last_build:float=0.

def start(context,kind,folder=None,run=None):
    """Explicit owner registration; targets are captured, never inferred each draw."""
    for token,session in list(_sessions.items()):
        if session.scene==context.scene and session.completed:_sessions.pop(token,None)
    rig=context.active_object if context.active_object and context.active_object.type=='ARMATURE' else None
    meshes=tuple(o for o in context.selected_objects if o.type=='MESH')[:MAX_MESHES]
    if rig is None:
        rigs={m.object for o in meshes for m in o.modifiers if m.type=='ARMATURE' and m.object}
        if len(rigs)==1:rig=next(iter(rigs))
    if kind=='SETUP':rig=None;meshes=()
    token=uuid.uuid4().hex
    _sessions[token]=Session(context.scene,kind,str(folder or ''),rig,meshes,run)
    if not bpy.app.background and not bpy.app.timers.is_registered(tick):
        bpy.app.timers.register(tick,first_interval=0)
    return token

def finish(token,outcome='CANCELLED'):
    session=_sessions.get(token)
    if not session:return
    enabled,reduced=preferences()
    if outcome=='FINISHED' and enabled and not reduced and not bpy.app.background:
        if session.run:
            session.rig=session.run.rig;session.meshes=tuple(session.run.meshes[:MAX_MESHES])
        elif session.kind!='SETUP' and bpy.context.scene==session.scene:
            rig=bpy.context.active_object
            if rig and rig.type=='ARMATURE':session.rig=rig
            meshes=tuple(o for o in bpy.context.selected_objects if o.type=='MESH')[:MAX_MESHES]
            if meshes:session.meshes=meshes
        session.geometry_key=()
        session.completed=time.monotonic();session.phase='Ready';session.kind='SUCCESS'
    else:_sessions.pop(token,None)
    if not _sessions:
        remove_draw_handlers()
        if bpy.app.timers.is_registered(tick):bpy.app.timers.unregister(tick)
    redraw()

def cancelled(token):
    session=_sessions.get(token)
    return bool(session and session.cancel_requested)

def preferences():
    prefs=configuration.preferences(bpy.context)
    return (getattr(prefs,'processing_visuals',True),getattr(prefs,'processing_reduced_animation',False))

def active(scene):
    return next((s for s in _sessions.values() if s.scene==scene and not s.completed),None)

def elapsed(session,now=None):
    seconds=max(0,int((time.monotonic() if now is None else now)-session.started))
    return f'{seconds//60}:{seconds%60:02d}'

def update_state(session):
    if session.completed:return
    if session.run:
        run=session.run
        session.rig=run.rig;session.meshes=tuple(run.meshes[:MAX_MESHES]);session.folder=str(run.folder or '')
        session.kind={'placement':'RIG','skin':'SKIN','refine':'SKIN','motion':'MOTION'}.get(run.stage,session.kind)
    job=skinning._jobs.get(session.folder,{})
    session.phase=job.get('phase') or {'RIG':'Placing humanoid joints','SKIN':'Refining skin weights',
        'MOTION':'Generating motion','IMAGE':'Estimating image pose','SETUP':'Installing local providers'}.get(session.kind,'Working locally')

def capture_geometry(session):
    """Cache only bone endpoints and object bounding boxes, never mesh vertices."""
    rig=session.rig
    pose=list(rig.pose.bones)[:MAX_BONES] if rig and rig.type=='ARMATURE' else []
    key=(rig.as_pointer() if rig else 0,
        tuple(value for row in rig.matrix_world for value in row) if rig else (),
        tuple((tuple(b.head),tuple(b.tail)) for b in pose),
        tuple((o.as_pointer(),tuple(value for row in o.matrix_world for value in row)) for o in session.meshes))
    if key==session.geometry_key and session.bounds:return
    bones=[];points=[]
    if rig and rig.type=='ARMATURE':
        world=rig.matrix_world
        for bone in pose:
            if not bone.bone.use_deform:continue
            head,tail=world@bone.head,world@bone.tail
            if (tail-head).length>1e-6:bones.append((head,tail));points.extend((head,tail))
    for mesh in session.meshes:
        points.extend(mesh.matrix_world@Vector(p) for p in mesh.bound_box)
    session.bones=bones;session.geometry_key=key
    if points:
        low=Vector(tuple(min(p[i] for p in points) for i in range(3)))
        high=Vector(tuple(max(p[i] for p in points) for i in range(3)))
        session.bounds=(low,high)
    else:session.bounds=()
    _stats['geometry_builds']+=1

def geometry(session,now,reduced=False):
    """One line batch for the skeleton and one for all glints/rings/trails."""
    if not session.bounds:return ([],[],[],[])
    low,high=session.bounds;center=(low+high)*.5;height=max(high.z-low.z,.05)
    radius=max((high.x-low.x)*.24,(high.y-low.y)*.45,height*.065)
    t=0. if reduced else now-session.started
    color=COLORS[session.kind];base=[];base_colors=[];sparks=[];spark_colors=[]
    fade=max(0.,1.-(now-session.completed)/.85) if session.completed else 1.
    def line(a,b,rgb=color,alpha=1.,target=sparks,colors=spark_colors):
        target.extend((tuple(a),tuple(b)));colors.extend(((*rgb,alpha*fade),)*2)
    def glint(point,size,alpha):
        for axis in range(3):
            delta=Vector((size if axis==0 else 0,size if axis==1 else 0,size if axis==2 else 0))
            line(point-delta,point+delta,alpha=alpha)
    for index,(head,tail) in enumerate(session.bones):
        level=(head.z-low.z)/height
        wave=.5+.5*math.cos(math.tau*(level-t*.4))
        line(head,tail,alpha=.16+.12*wave,target=base,colors=base_colors)
        if reduced or session.completed:
            if index%3==0:glint(head,height*.006,.65)
        else:
            # Two short comets travel along each bone; no posed mesh evaluation.
            speed=.6 if session.kind=='MOTION' else .35
            position=(t*speed+level+index*.037)%1.
            for offset,alpha in ((0.,.95),(-.09,.32)):
                p=(position+offset)%1.
                line(head.lerp(tail,max(0.,p-.12)),head.lerp(tail,p),alpha=alpha)
            if index%3==0 and wave>.82:glint(head,height*.004*(1.+wave),wave*.65)
    if session.kind!='SETUP':
        if session.kind=='SKIN':z=low.z+height*(.5 if reduced else (t*.22)%1.)
        elif session.kind=='RIG':z=low.z+height*.12
        elif session.kind=='IMAGE':z=low.z+height*.88;radius*=.6
        else:z=low.z+height*.45
        for index in range(48):
            a=math.tau*index/48;b=math.tau*(index+1)/48
            if session.kind=='MOTION':
                a+=t*.65;b+=t*.65
                za=z+height*.12*math.sin(a*2);zb=z+height*.12*math.sin(b*2)
            else:za=zb=z
            alpha=.18 if reduced else .18+.6*max(0.,math.cos(a-t*2))**6
            line((center.x+radius*math.cos(a),center.y+radius*.72*math.sin(a),za),
                 (center.x+radius*math.cos(b),center.y+radius*.72*math.sin(b),zb),alpha=alpha)
        if session.kind=='SKIN':
            # Scan ticks emphasize the current slice without sampling the surface.
            for side in (-1,1):
                x=center.x+side*radius*1.25
                line((x,center.y,z-height*.012),(x,center.y,z+height*.012),alpha=.8)
    return base,base_colors,sparks,spark_colors

def shader(name):
    import gpu
    if name not in _shaders:_shaders[name]=gpu.shader.from_builtin(name)
    return _shaders[name]

def build_batches(session,now,reduced):
    from gpu_extras.batch import batch_for_shader
    positions,colors,sparks,spark_colors=geometry(session,now,reduced)
    _stats['max_vertices']=max(_stats['max_vertices'],len(positions)+len(sparks))
    program=shader('POLYLINE_SMOOTH_COLOR')
    session.batches=tuple((batch_for_shader(program,'LINES',{'pos':p,'color':c}),width)
        for p,c,width in ((positions,colors,1.5),(sparks,spark_colors,2.5)) if p)
    session.last_build=now

def visible_views():
    return [(window,area) for window in bpy.context.window_manager.windows
        for area in window.screen.areas if area.type=='VIEW_3D']

def redraw(views=None):
    for _,area in visible_views() if views is None else views:area.tag_redraw()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='PREFERENCES':area.tag_redraw()

def ensure_draw_handlers():
    if _handles or bpy.app.background:return
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw_world,(),'WINDOW','POST_VIEW'))
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(draw_hud,(),'WINDOW','POST_PIXEL'))

def remove_draw_handlers():
    for handle in _handles:bpy.types.SpaceView3D.draw_handler_remove(handle,'WINDOW')
    _handles.clear();_shaders.clear()
    for session in _sessions.values():session.batches=()

def tick():
    begin=time.perf_counter();now=time.monotonic();enabled,reduced=preferences()
    for token,session in list(_sessions.items()):
        try:
            if session.scene.name not in bpy.data.scenes or session.completed and now-session.completed>=.85:
                _sessions.pop(token,None);continue
            update_state(session)
        except (ReferenceError,AttributeError):_sessions.pop(token,None)
    if not _sessions:remove_draw_handlers();redraw();return None
    views=[(window,area) for window,area in visible_views() if area.spaces.active.overlay.show_overlays
        and any(session.scene==window.scene and targets_visible(session,window.view_layer,area.spaces.active) for session in _sessions.values())]
    if enabled and views:
        ensure_draw_handlers()
        for session in _sessions.values():
            try:
                if not any(window.scene==session.scene for window,_ in views):continue
                capture_geometry(session)
                build_batches(session,now,reduced)
            except (ReferenceError,RuntimeError,ValueError):session.batches=()
    else:remove_draw_handlers()
    redraw(views if enabled else []);_stats['ticks']+=1;_stats['tick_ms']=max(_stats['tick_ms'],(time.perf_counter()-begin)*1000)
    return 1. if reduced else 1/FPS if enabled and views else .5

def targets_visible(session,view_layer,space):
    try:
        targets=([session.rig] if session.rig else [])+list(session.meshes)
        return not targets or any(o.visible_get(view_layer=view_layer,viewport=space) for o in targets)
    except ReferenceError:return False

def drawable_sessions(context):
    if context.space_data.type!='VIEW_3D' or not context.space_data.overlay.show_overlays:return []
    sessions=[]
    for session in _sessions.values():
        if session.scene!=context.scene:continue
        if not targets_visible(session,context.view_layer,context.space_data):continue
        sessions.append(session)
    return sessions

def draw_world():
    import gpu
    context=bpy.context;sessions=drawable_sessions(context)
    if not sessions:return
    begin=time.perf_counter()
    blend,depth,mask=gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
    try:
        gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE');gpu.state.depth_mask_set(False)
        program=shader('POLYLINE_SMOOTH_COLOR');program.bind()
        program.uniform_float('viewportSize',(context.region.width,context.region.height))
        for session in sessions:
            for batch,width in session.batches:program.uniform_float('lineWidth',width);batch.draw(program)
        _stats['draws']+=1
    finally:
        gpu.state.blend_set(blend);gpu.state.depth_test_set(depth);gpu.state.depth_mask_set(mask)
        _stats['draw_ms']=max(_stats['draw_ms'],(time.perf_counter()-begin)*1000)

def draw_hud():
    import blf,gpu
    from gpu_extras.batch import batch_for_shader
    sessions=drawable_sessions(bpy.context)
    if not sessions:return
    session=sessions[0];region=bpy.context.region
    if region.width<280 or region.height<120:return
    begin=time.perf_counter()
    _,reduced=preferences();now=time.monotonic();color=COLORS[session.kind]
    width=min(390,region.width-40);x,y=24,36
    blend=gpu.state.blend_get()
    try:
        gpu.state.blend_set('ALPHA');program=shader('UNIFORM_COLOR');program.bind()
        program.uniform_float('color',(.025,.035,.052,.88))
        batch_for_shader(program,'TRIS',{'pos':[(x,y),(x+width,y),(x+width,y+65),(x,y),(x+width,y+65),(x,y+65)]}).draw(program)
        program.uniform_float('color',(*color,.95))
        batch_for_shader(program,'TRIS',{'pos':[(x,y),(x+3,y),(x+3,y+65),(x,y),(x+3,y+65),(x,y+65)]}).draw(program)
        points=[];colors=[];angle=0. if reduced else (now-session.started)*2
        for k in range(24):
            a=angle+math.tau*k/24;b=angle+math.tau*(k+1)/24
            points.extend(((x+25+8*math.cos(a),y+38+8*math.sin(a),0),(x+25+8*math.cos(b),y+38+8*math.sin(b),0)))
            colors.extend(((*color,.2+.8*k/24),)*2)
        program=shader('POLYLINE_SMOOTH_COLOR');program.bind();program.uniform_float('viewportSize',(region.width,region.height));program.uniform_float('lineWidth',2.)
        batch_for_shader(program,'LINES',{'pos':points,'color':colors}).draw(program)
        title=session.phase;blf.size(0,13)
        while blf.dimensions(0,title)[0]>width-60 and len(title)>3:title=title[:-4]+'…'
        blf.color(0,.93,.96,1.,1.);blf.position(0,x+45,y+34,0);blf.draw(0,title)
        subtitle='Ready for review' if session.completed else f'Local processing   ·   {elapsed(session,now)}   ·   Cancel in Rigmodo'
        blf.size(0,11);blf.color(0,.58,.68,.77,1.);blf.position(0,x+16,y+12,0);blf.draw(0,subtitle)
    finally:
        gpu.state.blend_set(blend)
        _stats['hud_ms']=max(_stats['hud_ms'],(time.perf_counter()-begin)*1000)

def draw_panel(layout,context):
    session=active(context.scene)
    if not session:return
    update_state(session)
    box=layout.box();box.label(text='Working locally',icon='TIME')
    from .ui import message
    message(box,session.phase)
    row=box.row(align=True);row.label(text='Elapsed '+elapsed(session))
    if session.cancel_requested:row.label(text='Cancelling…')
    else:row.operator('local_character.cancel_processing',text='Cancel',icon='X')

class LC_OT_cancel_processing(Operator):
    bl_idname='local_character.cancel_processing';bl_label='Cancel Processing'
    bl_description='Cancel the current local job through its owning workflow'
    @classmethod
    def poll(cls,context):return active(context.scene) is not None
    def execute(self,context):
        session=active(context.scene)
        if session:session.cancel_requested=True;redraw()
        return {'FINISHED'}

@persistent
def reset(*_):
    _sessions.clear()
    if bpy.app.timers.is_registered(tick):bpy.app.timers.unregister(tick)
    remove_draw_handlers();redraw()

def register():
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if reset not in handlers:handlers.append(reset)

def unregister():
    reset()
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if reset in handlers:handlers.remove(reset)

CLASSES=(LC_OT_cancel_processing,)
