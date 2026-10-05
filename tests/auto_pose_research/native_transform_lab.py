# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated GUI experiment, never imported by the extension.

blender --factory-startup --enable-event-simulate --python THIS -- OUTPUT
Uses actual Blender keymap/modal transforms, driven by documented event_simulate.
Results are observations, not a production Auto Pose implementation.
"""
import bpy,importlib.util,json,sys,time,traceback
from pathlib import Path
from mathutils import Matrix,Quaternion

ROOT=Path(__file__).resolve().parents[2]
assert '--factory-startup' in sys.argv, 'Run this destructive setup only in its own factory-startup Blender process'
OUT=Path(sys.argv[sys.argv.index('--')+1]);OUT.mkdir(parents=True,exist_ok=True)
CUSTOM='custom' in sys.argv[sys.argv.index('--')+2:]
spec=importlib.util.spec_from_file_location('lab_skeleton',ROOT/'skeleton.py')
skeleton=importlib.util.module_from_spec(spec);sys.modules[spec.name]=skeleton;spec.loader.exec_module(skeleton)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
rig=skeleton.create_armature(bpy.context,1.75,20);rig.name='AutoPose_Lab'
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Rigmodo_AutoPose_Lab.blend'))
bpy.ops.object.mode_set(mode='POSE')
bpy.context.scene.tool_settings.use_keyframe_insert_auto=False
bpy.context.object.pose.use_auto_ik=False
window=bpy.context.window;area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW')
area.spaces.active.region_3d.view_rotation=Quaternion((1,0,0),1.5707963267948966)
area.spaces.active.region_3d.view_location=(0,0,.9)
area.spaces.active.region_3d.view_distance=3.7
area.spaces.active.region_3d.view_perspective='ORTHO'
x=int(region.x+region.width*.6);y=int(region.y+region.height*.6)
log=(OUT/'native-events.jsonl').open('w',buffering=1)
state=dict(case='',write=False,neighbor='RightArm',calls=0,writes=0,depth=0,max_depth=0,msgbus=0,stage=0,last=None,errors=[])
results=[];actions=[];deadline=time.monotonic()+2

def rig_now():return bpy.data.objects['AutoPose_Lab']
def flat(m):return [round(float(v),7) for row in m for v in row]
def ops():return [o.bl_idname for o in window.modal_operators]
def transforming():return any(s.startswith(('TRANSFORM_OT_','POSE_OT_autopose_lab_drag')) for s in ops())
def snapshot():
    r=rig_now();p=r.pose.bones['LeftHand'];n=r.pose.bones[state['neighbor']]
    return dict(active=r.data.bones.active.name if r.data.bones.active else None,selected=[b.name for b in r.pose.bones if b.select],
        active_basis=flat(p.matrix_basis),active_matrix=flat(p.matrix),neighbor_basis=flat(n.matrix_basis),neighbor_matrix=flat(n.matrix),
        all_basis={b.name:flat(b.matrix_basis) for b in r.pose.bones},ops=ops())
def emit(kind,**extra):
    log.write(json.dumps(dict(t=time.monotonic(),case=state['case'],kind=kind,**extra))+'\n')
def notify():state['msgbus']+=1
owner=object()
bpy.msgbus.subscribe_rna(key=(bpy.types.PoseBone,'location'),owner=owner,args=(),notify=notify)
bpy.msgbus.subscribe_rna(key=(bpy.types.PoseBone,'rotation_euler'),owner=owner,args=(),notify=notify)

def handler(scene,dg):
    state['depth']+=1;state['max_depth']=max(state['max_depth'],state['depth'])
    try:
        state['calls']+=1
        if state['depth']>1 or not state['write'] or not transforming():return
        r=rig_now();p=r.pose.bones[state['neighbor']]
        before=flat(p.matrix_basis)
        # Fixed proposal tests native overwriting separately from solver drift.
        if abs(p.rotation_euler.x-.4)>1e-6:
            p.rotation_euler.x=.4;state['writes']+=1
            emit('handler_write',before=before,after=flat(p.matrix_basis),ops=ops())
    finally:state['depth']-=1
bpy.app.handlers.depsgraph_update_post.append(handler)

class LAB_OT_observer(bpy.types.Operator):
    bl_idname='wm.autopose_lab_observer';bl_label='Auto Pose Lab Observer'
    def invoke(self,context,event):context.window_manager.modal_handler_add(self);return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if event.type in {'G','R','ESC','RET','LEFTMOUSE','RIGHTMOUSE','Z'}:emit('observer_event',event=event.type,value=event.value,ops=ops())
        return {'PASS_THROUGH'}
bpy.utils.register_class(LAB_OT_observer)
with bpy.context.temp_override(window=window,area=area,region=region):bpy.ops.wm.autopose_lab_observer('INVOKE_DEFAULT')

class LAB_OT_drag(bpy.types.Operator):
    """Only a cancel/undo ownership probe, NOT a pose solver/finished G/R clone."""
    bl_idname='pose.autopose_lab_drag';bl_label='Auto Pose Transaction Probe'
    bl_options={'REGISTER','UNDO','BLOCKING'}
    kind:bpy.props.EnumProperty(items=[('G','Move',''),('R','Rotate','')])
    def invoke(self,context,event):
        self.initial={p.name:p.matrix_basis.copy() for p in rig_now().pose.bones}
        self.start=(event.mouse_x,event.mouse_y);context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if event.type in {'ESC','RIGHTMOUSE'} and event.value=='PRESS':
            for p in rig_now().pose.bones:p.matrix_basis=self.initial[p.name]
            return {'CANCELLED'}
        if event.type in {'RET','LEFTMOUSE'} and event.value=='PRESS':return {'FINISHED'}
        if event.type=='MOUSEMOVE':
            r=rig_now();delta=(event.mouse_x-self.start[0])*.002
            p=r.pose.bones['LeftHand']
            if self.kind=='G':p.location.x=self.initial[p.name].translation.x+delta
            else:p.rotation_euler.z=delta
            r.pose.bones[state['neighbor']].rotation_euler.x=delta*.7
            context.area.tag_redraw()
        return {'RUNNING_MODAL'}
if CUSTOM:
    bpy.utils.register_class(LAB_OT_drag)
    km=bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='Pose',space_type='EMPTY')
    for k in ('G','R'):km.keymap_items.new(LAB_OT_drag.bl_idname,k,'PRESS').properties.kind=k

def event(key,value='PRESS',dx=0,dy=0,ctrl=False,shift=False):window.event_simulate(type=key,value='NOTHING' if key=='MOUSEMOVE' else value,x=x+dx,y=y+dy,ctrl=ctrl,shift=shift)
def key(key,ctrl=False,shift=False):event(key,ctrl=ctrl,shift=shift);event(key,'RELEASE',ctrl=ctrl,shift=shift)
def begin(label,write=False,neighbor='RightArm',constraint=False,multi=False):
    state.update(case=label,write=False,neighbor=neighbor,calls=0,writes=0,msgbus=0,max_depth=0,last=None)
    r=rig_now()
    for p in r.pose.bones:
        for c in list(p.constraints):p.constraints.remove(c)
        p.rotation_mode='XYZ';p.matrix_basis=Matrix.Identity(4);p.select=False
    r.pose.bones['LeftHand'].select=True;r.data.bones.active=r.data.bones['LeftHand']
    if multi:r.pose.bones[neighbor].select=True
    if constraint:
        c=r.pose.bones[neighbor].constraints.new('LIMIT_ROTATION');c.owner_space='LOCAL';c.use_limit_x=True;c.min_x=c.max_x=0
    bpy.context.view_layer.update()
    with bpy.context.temp_override(window=window,area=area,region=region):bpy.ops.ed.undo_push(message='AutoPose Lab '+label)
    row=dict(name=label,before=snapshot(),samples=[],handler=write,constraint=constraint,multi=multi)
    results.append(row);state['write']=write
    event('MOUSEMOVE');emit('begin',snapshot=row['before'])
def capture(label):
    results[-1][label]=snapshot();results[-1]['handler_calls']=state['calls'];results[-1]['writes']=state['writes']
    results[-1]['max_handler_depth']=state['max_depth'];results[-1]['msgbus_notifications']=state['msgbus']
    emit(label,snapshot=results[-1][label])
def disable():state['write']=False

for label,mode,write,neighbor,constraint,multi,cancel in (
    ('G_read_only','G',False,'RightArm',False,False,False),
    ('G_other_bone_confirm','G',True,'RightArm',False,False,False),
    ('G_other_bone_cancel','G',True,'RightArm',False,False,True),
    ('R_other_bone_confirm','R',True,'RightArm',False,False,False),
    ('R_other_bone_cancel','R',True,'RightArm',False,False,True),
    ('G_parent_write','G',True,'LeftForeArm',False,False,False),
    ('R_selected_overlap','R',True,'RightArm',False,True,False),
    ('G_constrained_other','G',True,'RightArm',True,False,False),
):
    if CUSTOM and (multi or constraint or neighbor!='RightArm'):continue
    actions.extend([(lambda l=label,w=write,n=neighbor,c=constraint,m=multi:begin(l,False if CUSTOM else w,n,c,m)),
        (lambda k=mode:key(k)),(lambda k=('X' if mode=='G' else 'Z'):key(k))])
    for dx,dy in ((30,20),(60,40),(90,60),(120,80),(150,100)):
        actions.append(lambda dx=dx,dy=dy:event('MOUSEMOVE',dx=dx,dy=dy))
    actions.extend([(lambda:capture('during')),disable,(lambda c=cancel:key('ESC' if c else 'RET')),
        (lambda:capture('after')), (lambda:key('Z',ctrl=True)),(lambda:capture('undo'))])
    if not cancel:actions.extend([(lambda:key('Z',ctrl=True,shift=True)),(lambda:capture('redo'))])

def finish():
    state['write']=False;bpy.app.handlers.depsgraph_update_post.remove(handler);bpy.msgbus.clear_by_owner(owner)
    report=dict(blender=bpy.app.version_string,input_method='documented Window.event_simulate through real native keymap',
        production_addon_loaded=False,custom_transaction_probe=CUSTOM,auto_key=False,auto_ik=False,cases=results,errors=state['errors'])
    (OUT/'native-results.json').write_text(json.dumps(report,indent=2)+'\n');log.close()
    print('NATIVE_TRANSFORM_LAB_COMPLETE',str(OUT),flush=True)
    bpy.ops.wm.quit_blender()
def tick():
    global deadline
    try:
        if results:
            sample=snapshot();signature=json.dumps(sample)
            if signature!=state['last']:
                state['last']=signature;results[-1]['samples'].append(sample);emit('sample',snapshot=sample)
        if time.monotonic()<deadline:return .01
        if not actions:finish();return None
        action=actions.pop(0);action();deadline=time.monotonic()+.22
        return .01
    except Exception:
        state['errors'].append(traceback.format_exc());finish();return None
bpy.app.timers.register(tick,first_interval=2)
