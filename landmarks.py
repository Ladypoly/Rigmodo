# SPDX-License-Identifier: GPL-3.0-or-later
"""Focused front-view landmark editor; learned placement supplies depth/fingers."""
import copy,json,math
import bpy
from bpy.types import Operator
from mathutils import Vector,Quaternion
from . import placement,skinning

STEPS=(('Hips','Pelvis / groin'),('Head','Head base / chin'),('LeftForeArm','Elbow'),('LeftHand','Wrist'),('LeftLeg','Knee'))
RIGHT=(('RightForeArm','Right elbow'),('RightHand','Right wrist'),('RightLeg','Right knee'))
LABELS={'Hips':'Pelvis','Head':'Head base','LeftForeArm':'L elbow','RightForeArm':'R elbow',
        'LeftHand':'L wrist','RightHand':'R wrist','LeftLeg':'L knee','RightLeg':'R knee'}
_sessions=[]

def validate(data,meshes):
    required={n for n,_ in STEPS}|{n for n,_ in RIGHT}
    if data.get('schema_version')!=1 or set(data.get('points',{}))!=required:raise ValueError('Set all five landmark groups first')
    if data.get('mesh_digest')!=skinning._digest(None,meshes):raise ValueError('Landmarks belong to different or edited geometry; set them again')
    points=data['points']
    if any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in points.values()):raise ValueError('Invalid landmark coordinates')
    if points['Head'][2]<=points['Hips'][2] or any(points[s+'Leg'][2]>=points['Hips'][2] for s in ('Left','Right')):
        raise ValueError('Place the head above the pelvis and knees below it')
    return data

def constrain(heads,tails,data,locked=()):
    """Front guides constrain X/Z; preserve the model's anatomical Y depth."""
    for name,point in data['points'].items():
        if name in locked:continue
        head=heads[name].copy();delta=Vector((point[0]-head.x,0,point[2]-head.z))
        heads[name]+=delta;tails[name]+=delta

def cleanup():
    for session in list(_sessions):session.finish()

class LC_OT_landmark_editor(Operator):
    bl_idname='local_character.edit_landmarks'
    bl_label='Set Landmarks'
    bl_description='Front-view editor: click pelvis, head base, elbow, wrist and knee; mirrored pairs are automatic'
    bl_options={'UNDO'}
    @classmethod
    def poll(cls,context):
        from . import hands
        return context.mode=='OBJECT' and context.area and context.area.type=='VIEW_3D' and not skinning._jobs and not _sessions and not hands._sessions
    def invoke(self,context,event):
        try:
            _,self.meshes=placement.selected(context)
            if not self.meshes:raise ValueError('Select the avatar mesh first')
            self.area=context.area;self.region=next(r for r in self.area.regions if r.type=='WINDOW');self.view=self.area.spaces.active.region_3d
            points=[m.matrix_world@Vector(c) for m in self.meshes for c in m.bound_box]
            lo=Vector([min(p[i] for p in points) for i in range(3)]);hi=Vector([max(p[i] for p in points) for i in range(3)])
            self.center=(lo+hi)/2;self.extent=max((hi-lo).z,(hi-lo).x)
            if self.extent<1e-5:raise ValueError('Selected mesh has no usable bounds')
            self.saved=(self.view.view_rotation.copy(),self.view.view_location.copy(),self.view.view_distance,self.view.view_perspective)
            space=self.area.spaces.active
            self.saved_display=(space.overlay.show_overlays,space.show_gizmo,space.show_region_toolbar)
            space.overlay.show_overlays=False;space.show_gizmo=False;space.show_region_toolbar=False
            self.view.view_rotation=Quaternion((math.sqrt(.5),math.sqrt(.5),0,0));self.view.view_location=self.center
            aspect=self.region.width/max(self.region.height,1)
            self.view.view_distance=max((hi-lo).z,(hi-lo).x/max(aspect,.2))*1.6;self.view.view_perspective='ORTHO'
            self.mirror=context.scene.lc_settings.landmark_symmetry;self.steps=STEPS if self.mirror else STEPS+RIGHT
            self.data=dict(schema_version=1,mesh_digest=skinning._digest(None,self.meshes),points={})
            try:
                existing=json.loads(context.scene.lc_settings.landmark_data)
                if existing.get('mesh_digest')==self.data['mesh_digest']:self.data=existing
            except (ValueError,TypeError):pass
            self.history=[];self.drag=None;self.scene=context.scene;self.handle=None
            self.handle=bpy.types.SpaceView3D.draw_handler_add(self.draw_overlay,(),'WINDOW','POST_PIXEL');_sessions.append(self)
            context.window_manager.modal_handler_add(self);self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        except (ValueError,RuntimeError,StopIteration) as error:self.finish();self.report({'ERROR'},str(error));return {'CANCELLED'}
    def next_step(self):return next(((n,t) for n,t in self.steps if n not in self.data['points']),None)
    def point(self,event):
        from bpy_extras import view3d_utils
        return view3d_utils.region_2d_to_location_3d(self.region,self.view,(event.mouse_x-self.region.x,event.mouse_y-self.region.y),self.center)
    def assign(self,name,point):
        center=self.data['points'].get('Hips',list(self.center))[0]
        if name in {'Hips','Head'}:point.x=center if name=='Head' else point.x
        elif self.mirror:point.x=center+abs(point.x-center)
        self.data['points'][name]=list(point)
        if self.mirror:
            if name=='Hips':
                if 'Head' in self.data['points']:self.data['points']['Head'][0]=point.x
                for bone,_ in STEPS[2:]:
                    if bone in self.data['points']:
                        p=self.data['points'][bone];self.data['points'][bone.replace('Left','Right')]=[2*point.x-p[0],p[1],p[2]]
            elif name.startswith('Left'):self.data['points'][name.replace('Left','Right')]=[2*center-point.x,point.y,point.z]
    def modal(self,context,event):
        try:return self.handle_event(context,event)
        except (ValueError,RuntimeError,ReferenceError,TypeError) as error:
            self.finish();self.report({'ERROR'},str(error));return {'CANCELLED'}
    def handle_event(self,context,event):
        if getattr(self,'closed',False):return {'CANCELLED'}
        if context.scene!=self.scene or not any(a==self.area for a in context.screen.areas):self.finish();return {'CANCELLED'}
        if event.type in {'ESC','RIGHTMOUSE'}:self.finish();return {'CANCELLED'}
        if event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS':
            try:validate(self.data,self.meshes)
            except ValueError as error:self.report({'WARNING'},str(error));return {'RUNNING_MODAL'}
            self.scene.lc_settings.landmark_data=json.dumps(self.data);self.scene.lc_settings.ui_rig_mode='ASSISTED'
            self.finish();return {'FINISHED'}
        if event.type=='BACK_SPACE' and event.value=='PRESS':
            if self.history:self.data=self.history.pop()
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        inside=self.region.x<=event.mouse_x<self.region.x+self.region.width and self.region.y<=event.mouse_y<self.region.y+self.region.height
        if event.type=='LEFTMOUSE' and event.value=='PRESS' and inside:
            from bpy_extras import view3d_utils
            nearest=None;distance=16
            for name,p in self.data['points'].items():
                if self.mirror and name.startswith('Right'):continue
                screen=view3d_utils.location_3d_to_region_2d(self.region,self.view,Vector(p))
                if screen:
                    d=(screen-Vector((event.mouse_x-self.region.x,event.mouse_y-self.region.y))).length
                    if d<distance:nearest=name;distance=d
            step=self.next_step();self.drag=nearest or (step[0] if step else None)
            if self.drag:self.history.append(copy.deepcopy(self.data));self.assign(self.drag,self.point(event))
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='MOUSEMOVE' and self.drag:self.assign(self.drag,self.point(event));self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':self.drag=None;return {'RUNNING_MODAL'}
        # Keep the front plane fixed while editing; sidebar controls remain usable.
        if inside:return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}
    def draw_overlay(self):
        if bpy.context.area!=self.area:return
        import blf,gpu
        from gpu_extras.batch import batch_for_shader
        from bpy_extras import view3d_utils
        shader=gpu.shader.from_builtin('UNIFORM_COLOR');gpu.state.blend_set('ALPHA')
        try:
            width=self.region.width;height=self.region.height
            shader.bind();shader.uniform_float('color',(.025,.03,.04,.94))
            batch_for_shader(shader,'TRI_FAN',{'pos':[(16,height-140),(min(width-16,650),height-140),(min(width-16,650),height-62),(16,height-62)]}).draw(shader)
            step=self.next_step();title='Drag markers to adjust. Enter: accept' if not step else f"{sum(n in self.data['points'] for n,_ in self.steps)+1}/{len(self.steps)}  Click {step[1]}"+(' (either side)' if self.mirror and step[0].startswith('Left') else '')
            blf.size(0,18);blf.color(0,.92,.96,1,1);blf.position(0,30,height-93,0);blf.draw(0,title)
            blf.size(0,13);blf.color(0,.63,.7,.8,1);blf.position(0,30,height-119,0);blf.draw(0,'Left click / drag   |   Backspace: undo   |   Esc: cancel')
            for name,p in self.data['points'].items():
                point=view3d_utils.location_3d_to_region_2d(self.region,self.view,Vector(p))
                if point is None:continue
                circle=[(point.x+9*math.cos(i*math.tau/32),point.y+9*math.sin(i*math.tau/32)) for i in range(33)]
                shader.bind();shader.uniform_float('color',(.25,.77,1,1));gpu.state.line_width_set(2)
                batch_for_shader(shader,'LINE_STRIP',{'pos':circle}).draw(shader)
                blf.size(0,12);blf.color(0,.9,.96,1,1);blf.position(0,point.x+13,point.y-4,0);blf.draw(0,LABELS[name])
        finally:gpu.state.blend_set('NONE');gpu.state.line_width_set(1)
    def finish(self):
        self.closed=True
        if getattr(self,'handle',None):bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW');self.handle=None
        if getattr(self,'saved',None):
            try:
                self.view.view_rotation,self.view.view_location,self.view.view_distance,self.view.view_perspective=self.saved
                space=self.area.spaces.active;space.overlay.show_overlays,space.show_gizmo,space.show_region_toolbar=self.saved_display
                self.area.tag_redraw()
            except ReferenceError:pass
            self.saved=None
        if self in _sessions:_sessions.remove(self)
    def cancel(self,context):self.finish()

CLASSES=(LC_OT_landmark_editor,)
