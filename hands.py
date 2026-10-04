# SPDX-License-Identifier: GPL-3.0-or-later
"""Accepted-body hand refinement and a small orbitable joint guide editor."""
import copy,json,math
import bpy
from bpy.types import Operator
from mathutils import Vector,Matrix
from . import hand_geometry,skeleton,skinning,placement,landmarks

_sessions=[]

def check_rig(rig):
    mapping={skeleton.canonical_name(b.name):b for b in rig.data.bones}
    required={j.name for j in skeleton.template() if j.deform}
    if not required<=mapping.keys() or len(mapping)!=len(rig.data.bones):raise ValueError('Hand refinement needs an unambiguous Mixamo-style humanoid rig')
    if rig.animation_data and (rig.animation_data.action or rig.animation_data.drivers or rig.animation_data.nla_tracks):raise ValueError('Refine hands before adding animation; use an unanimated working copy')
    if rig.constraints or any(b.constraints for b in rig.pose.bones):raise ValueError('Use an unconstrained working rig for hand refinement')
    if any(max(abs(b.matrix_basis[i][j]-(1 if i==j else 0)) for i in range(4) for j in range(4))>1e-6 for b in rig.pose.bones):raise ValueError('Clear the pose before refining hand rest joints')
    if abs(rig.matrix_world.determinant())<1e-10:raise ValueError('The rig has a singular transform')
    for name,bone in mapping.items():
        if hand_geometry.digit(name) and any(not hand_geometry.digit(skeleton.canonical_name(c.name)) for c in bone.children):
            raise ValueError('Remove finger helper bones on a working copy before refining hands')

def character(context):
    try:rig,meshes=placement.selected(context)
    except ValueError:
        rig=context.active_object if context.active_object and context.active_object.type=='ARMATURE' else None
        meshes=[]
    if rig and not meshes:
        helpers={b.custom_shape for b in rig.pose.bones if b.custom_shape}
        meshes=[o for o in context.view_layer.objects if o.type=='MESH' and o not in helpers and o.visible_get() and
                (o.parent==rig or any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers))]
    if not rig or not meshes:raise ValueError('Select the accepted rig and its character meshes')
    check_rig(rig);return rig,meshes

def validate_guides(data,rig,meshes):
    if data.get('schema_version')!=1 or data.get('source_digest')!=skinning._digest(rig,meshes):raise ValueError('Hand guides belong to different or edited joints; set them again')
    allowed={side+'Hand'+finger+suffix for side in ('Left','Right') for finger in hand_geometry.FINGERS for suffix in ('1','2','3','Tip')}
    points=data.get('points',{})
    if not isinstance(points,dict) or not set(points)<=allowed or any(not isinstance(p,(list,tuple)) or len(p)!=3 or not all(isinstance(v,(float,int)) and math.isfinite(v) for v in p) for p in points.values()):raise ValueError('Invalid hand guide coordinates')
    for bone in rig.data.bones:
        name=skeleton.canonical_name(bone.name)
        if not hand_geometry.digit(name) or not bone.get('lc_joint_locked'):continue
        for key,point in ((name,rig.matrix_world@bone.head_local),(name[:-1]+('Tip' if name.endswith('3') else str(int(name[-1])+1)),rig.matrix_world@bone.tail_local)):
            if key in points and (Vector(points[key])-point).length>1e-6:raise ValueError('Unlock '+bone.name+' before moving its hand guide')
    return data

def saved_guides(context,rig,meshes):
    raw=context.scene.lc_settings.hand_guide_data
    if not raw:return None
    data=json.loads(raw)
    # Changing character makes stored guides irrelevant, never transferable.
    if data.get('source_digest')!=skinning._digest(rig,meshes):return None
    return validate_guides(data,rig,meshes)

def apply_copy(context,folder,source,result,rig,meshes):
    """Clone the accepted rig; only digit rest positions are edited."""
    check_rig(rig);scale=source['scene_unit_scale'];inverse=rig.matrix_world.inverted()
    convert=lambda p:inverse@Vector((p[0]/scale,-p[2]/scale,p[1]/scale))
    mapping={skeleton.canonical_name(b.name):b.name for b in rig.data.bones}
    new=None;collection=None;copies=[];selected=list(context.selected_objects);active=context.active_object
    try:
        collection=bpy.data.collections.new('Local Character Hands');context.scene.collection.children.link(collection)
        new=rig.copy();new.data=rig.data.copy();collection.objects.link(new);new.name=rig.name+'_Hands';new.hide_set(False)
        for obj in context.selected_objects:obj.select_set(False)
        new.select_set(True);context.view_layer.objects.active=new;bpy.ops.object.mode_set(mode='EDIT')
        try:
            for i,name in enumerate(result['names']):
                if not hand_geometry.digit(name):continue
                bone=new.data.edit_bones[mapping[name]]
                if rig.data.bones[bone.name].get('lc_joint_locked'):continue
                bone.use_connect=False;bone.head=convert(result['heads'][i]);bone.tail=convert(result['tails'][i])
                # Keep the artist's local roll convention; Blender updates its
                # direction from the new segment while retaining that roll.
        finally:bpy.ops.object.mode_set(mode='OBJECT')
        for original in meshes:
            mesh=original.copy();mesh.data=original.data.copy();copies.append(mesh);collection.objects.link(mesh)
            mesh.name=original.name+'_Hands'
            if original.parent==rig:mesh.parent=new;mesh.matrix_world=original.matrix_world.copy()
            for modifier in mesh.modifiers:
                if modifier.type=='ARMATURE' and modifier.object==rig:modifier.object=new
            mesh['lc_placement_job']=source['job_id'];mesh['lc_source_mesh']=original.get('lc_source_mesh',original.name)
            mesh.hide_set(False)
        new['lc_placement']='mia_original_hand_refinement';new['lc_placement_job']=source['job_id']
        new['lc_hand_report']=json.dumps(result.get('hand_report',[]));new['lc_joint_review']='Inspect finger articulation; skin again after changing rest joints'
        for key in ('lc_deformation_qa','lc_deformation_report'):
            if key in new:del new[key]
        skinning._state(folder,'applied',collection=collection.name)
    except Exception:
        if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in [*copies,*([new] if new else [])]:
            block=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if block.users==0:(bpy.data.armatures if isinstance(block,bpy.types.Armature) else bpy.data.meshes).remove(block)
        if collection:bpy.data.collections.remove(collection)
        for obj in context.selected_objects:obj.select_set(False)
        for obj in selected:obj.select_set(True)
        context.view_layer.objects.active=active;raise
    return collection,new,copies,result

def cleanup():
    for session in list(_sessions):session.finish()

class LC_OT_hand_guides(Operator):
    bl_idname='local_character.edit_hand_guides'
    bl_label='Edit Hand Guides'
    bl_description='Drag finger tips or knuckles, orbit to adjust depth; guides constrain the next hand refinement'
    bl_options={'UNDO'}
    @classmethod
    def poll(cls,context):return context.mode=='OBJECT' and context.area and context.area.type=='VIEW_3D' and not skinning._jobs and not _sessions and not landmarks._sessions
    def invoke(self,context,event):
        try:
            self.rig,self.meshes=character(context);self.scene=context.scene;self.area=context.area
            self.region=next(r for r in self.area.regions if r.type=='WINDOW');self.view=self.area.spaces.active.region_3d
            self.saved=(self.view.view_rotation.copy(),self.view.view_location.copy(),self.view.view_distance,self.view.view_perspective)
            space=self.area.spaces.active;self.saved_display=(space.overlay.show_overlays,space.show_gizmo,space.show_region_toolbar)
            space.overlay.show_overlays=False;space.show_gizmo=False;space.show_region_toolbar=False
            self.base={};mapping={skeleton.canonical_name(b.name):b for b in self.rig.data.bones}
            for side in ('Left','Right'):
                for finger in hand_geometry.FINGERS:
                    for i in (1,2,3):
                        name=side+'Hand'+finger+str(i);bone=mapping[name];self.base[name]=list(self.rig.matrix_world@bone.head_local)
                        if i==3:self.base[name[:-1]+'Tip']=list(self.rig.matrix_world@bone.tail_local)
            self.data=saved_guides(context,self.rig,self.meshes) or dict(schema_version=1,source_digest=skinning._digest(self.rig,self.meshes),points={})
            self.data=copy.deepcopy(self.data);self.history=[];self.drag=None;self.finger=None;self.side=context.scene.lc_settings.hand_side
            self.frame_hand();self.handle=bpy.types.SpaceView3D.draw_handler_add(self.draw_overlay,(),'WINDOW','POST_PIXEL');_sessions.append(self)
            context.window_manager.modal_handler_add(self);self.area.tag_redraw();return {'RUNNING_MODAL'}
        except (ValueError,RuntimeError,StopIteration) as error:self.finish();self.report({'ERROR'},str(error));return {'CANCELLED'}
    def frame_hand(self):
        points=[Vector(p) for n,p in self.base.items() if n.startswith(self.side)]
        self.view.view_location=sum(points,Vector())/len(points)
        self.view.view_distance=max((p-self.view.view_location).length for p in points)*3
        self.view.view_perspective='ORTHO';self.area.tag_redraw()
    def displayed(self):
        keys=[self.side+'Hand'+finger+'Tip' for finger in hand_geometry.FINGERS]
        if self.finger:keys += [self.side+'Hand'+self.finger+str(i) for i in (1,2,3)]
        return {n:self.data['points'].get(n,self.base[n]) for n in keys}
    def modal(self,context,event):
        try:return self.event(context,event)
        except (ValueError,RuntimeError,ReferenceError,TypeError) as error:self.finish();self.report({'ERROR'},str(error));return {'CANCELLED'}
    def event(self,context,event):
        if getattr(self,'closed',False):return {'CANCELLED'}
        if context.scene!=self.scene or not any(a==self.area for a in context.screen.areas):self.finish();return {'CANCELLED'}
        if event.type=='ESC':self.finish();return {'CANCELLED'}
        if event.type in {'RET','NUMPAD_ENTER'} and event.value=='PRESS':
            try:validate_guides(self.data,self.rig,self.meshes)
            except ValueError as error:self.report({'WARNING'},str(error));return {'RUNNING_MODAL'}
            self.scene.lc_settings.hand_guide_data=json.dumps(self.data)
            self.scene.lc_settings.placement_status='Hand guides saved. Press Refine Hands to create a corrected copy.'
            self.finish();return {'FINISHED'}
        inside=self.region.x<=event.mouse_x<self.region.x+self.region.width and self.region.y<=event.mouse_y<self.region.y+self.region.height
        if not inside and self.drag is None:return {'PASS_THROUGH'}
        if event.type=='TAB' and event.value=='PRESS':self.side='Right' if self.side=='Left' else 'Left';self.finger=None;self.frame_hand();return {'RUNNING_MODAL'}
        if event.type in {'ONE','TWO','THREE','FOUR','FIVE'} and event.value=='PRESS':self.finger=hand_geometry.FINGERS[('ONE','TWO','THREE','FOUR','FIVE').index(event.type)];self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='BACK_SPACE' and event.value=='PRESS':
            if self.history:self.data=self.history.pop()
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='PRESS' and inside:
            from bpy_extras import view3d_utils
            position=Vector((event.mouse_x-self.region.x,event.mouse_y-self.region.y));nearest=None;distance=18
            for name,p in self.displayed().items():
                screen=view3d_utils.location_3d_to_region_2d(self.region,self.view,Vector(p))
                if screen is not None and (screen-position).length<distance:nearest=name;distance=(screen-position).length
            if nearest:
                self.history.append(copy.deepcopy(self.data));self.drag=nearest;self.depth=Vector(self.displayed()[nearest]);self.finger=next(f for f in hand_geometry.FINGERS if f in nearest)
            self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='MOUSEMOVE' and self.drag:
            from bpy_extras import view3d_utils
            p=view3d_utils.region_2d_to_location_3d(self.region,self.view,(event.mouse_x-self.region.x,event.mouse_y-self.region.y),self.depth)
            self.data['points'][self.drag]=list(p);self.area.tag_redraw();return {'RUNNING_MODAL'}
        if event.type=='LEFTMOUSE' and event.value=='RELEASE':self.drag=None;return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}
    def draw_overlay(self):
        if bpy.context.area!=self.area:return
        import blf,gpu
        from gpu_extras.batch import batch_for_shader
        from bpy_extras import view3d_utils
        shader=gpu.shader.from_builtin('UNIFORM_COLOR');gpu.state.blend_set('ALPHA')
        try:
            height=self.region.height;shader.bind();shader.uniform_float('color',(.025,.03,.04,.94))
            batch_for_shader(shader,'TRI_FAN',{'pos':[(16,height-140),(min(self.region.width-16,760),height-140),(min(self.region.width-16,760),height-62),(16,height-62)]}).draw(shader)
            blf.size(0,18);blf.color(0,.92,.96,1,1);blf.position(0,30,height-93,0);blf.draw(0,self.side+' hand — drag tips; select a finger for knuckles')
            blf.size(0,12);blf.color(0,.65,.75,.85,1);blf.position(0,30,height-119,0);blf.draw(0,'Orbit to adjust depth | Tab: other hand | 1–5: finger | Backspace: undo | Enter: save | Esc: cancel')
            points={**self.base,**self.data['points']}
            if self.finger:
                prefix=self.side+'Hand'+self.finger;chain=[prefix+str(i) for i in (1,2,3)]+[prefix+'Tip']
                screen=[view3d_utils.location_3d_to_region_2d(self.region,self.view,Vector(points[n])) for n in chain]
                if all(p is not None for p in screen):
                    shader.bind();shader.uniform_float('color',(.3,.8,1,1));batch_for_shader(shader,'LINE_STRIP',{'pos':screen}).draw(shader)
            for name,p in self.displayed().items():
                point=view3d_utils.location_3d_to_region_2d(self.region,self.view,Vector(p))
                if point is None:continue
                circle=[(point.x+8*math.cos(i*math.tau/32),point.y+8*math.sin(i*math.tau/32)) for i in range(33)]
                shader.bind();shader.uniform_float('color',(.25,.77,1,1));batch_for_shader(shader,'LINE_STRIP',{'pos':circle}).draw(shader)
                label=name.replace(self.side+'Hand','').replace('Tip',' tip');blf.size(0,12);blf.color(0,.9,.96,1,1);blf.position(0,point.x+11,point.y-4,0);blf.draw(0,label)
        finally:gpu.state.blend_set('NONE')
    def finish(self):
        self.closed=True
        if getattr(self,'handle',None):bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW');self.handle=None
        if getattr(self,'saved',None):
            try:
                self.view.view_rotation,self.view.view_location,self.view.view_distance,self.view.view_perspective=self.saved
                space=self.area.spaces.active;space.overlay.show_overlays,space.show_gizmo,space.show_region_toolbar=self.saved_display;self.area.tag_redraw()
            except ReferenceError:pass
            self.saved=None
        if self in _sessions:_sessions.remove(self)
    def cancel(self,context):self.finish()

CLASSES=(LC_OT_hand_guides,)
