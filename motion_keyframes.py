# SPDX-License-Identifier: GPL-3.0-or-later
"""Artist pose snapshots, inverse retargeting and native constraint transport."""
import hashlib,json,math
import bpy,numpy as np
from bpy.types import Operator
from bpy.props import FloatProperty
from mathutils import Matrix,Vector,Quaternion
from . import motion_data,motion_jobs,skeleton,skinning,twists

PROPERTY='lc_motion_keyframes'

def signature(context,rig):
    data=[context.scene.unit_settings.scale_length,[list(row) for row in rig.matrix_world],
        [(b.name,b.parent.name if b.parent else None,[list(row) for row in b.matrix_local],list(b.tail_local)) for b in rig.data.bones]]
    return hashlib.sha256(json.dumps(data,allow_nan=False).encode()).hexdigest()

def data(rig):
    raw=rig.get(PROPERTY,'{"schema_version":1,"poses":[]}')
    if not isinstance(raw,str) or len(raw)>4_000_000:raise ValueError('Invalid key pose storage')
    result=json.loads(raw)
    if not isinstance(result,dict) or not isinstance(result.get('poses'),list) or len(result['poses'])>32:raise ValueError('Invalid key pose count')
    return result

def validate_basis(rig,p):
    if not math.isfinite(p['frame']) or set(p['basis'])!=set(rig.data.bones.keys()):raise ValueError('Key pose bone scope or frame changed')
    for name,value in p['basis'].items():
        loc=np.asarray(value['location']);q=np.asarray(value['rotation']);scale=np.asarray(value['scale'])
        if loc.shape!=(3,) or q.shape!=(4,) or scale.shape!=(3,) or not all(np.isfinite(v).all() for v in (loc,q,scale)):
            raise ValueError('Invalid key pose bone transform')
        if abs(np.linalg.norm(q)-1)>1e-4 or np.max(np.abs(scale-1))>1e-4:raise ValueError('Key poses need unit rotations and unscaled bones')
        if skeleton.canonical_name(name) not in {'Root','Hips'} and np.linalg.norm(loc)>1e-5:raise ValueError('Only Root/Hips movement is supported in key poses')

def capture(context,rig):
    # Pose Mode is the author's editing context; validate the rig without
    # changing mode, selection, its Action or the current timeline position.
    from types import SimpleNamespace
    mapping=motion_jobs.validate_rig(SimpleNamespace(mode='OBJECT'),rig)
    context.view_layer.update();world=rig.matrix_world;world_rot=world.to_quaternion().to_matrix()
    for module in twists.modules(rig):
        source=rig.pose.bones[module['source']].matrix_basis;helper=rig.pose.bones[module['helper']].matrix_basis
        expected=Matrix.LocRotScale(source.translation,twists.reduced(source.to_quaternion(),module['fraction']),source.to_scale())
        if max(abs(v) for row in (expected-helper) for v in row)>1e-4:raise ValueError('Use Rig options → Update Twist Pose before capturing this pose')
    conv=Matrix(motion_data.Y_TO_Z.tolist());globals=np.zeros((30,3,3));known={}
    basis={}
    for b in rig.data.bones:
        pose=rig.pose.bones[b.name];loc,q,scale=pose.matrix_basis.decompose()
        if max(abs(v-1) for v in scale)>1e-4 or (b.name not in {mapping['Root'].name,mapping['Hips'].name} and loc.length>1e-5):
            raise ValueError('Key poses use bone rotations and Root/Hips movement; remove other bone translations or scaling')
        basis[b.name]=dict(location=list(loc),rotation=list(q),scale=list(scale))
    for canonical,bone in mapping.items():
        if canonical not in motion_data.MAPPING:continue
        source=motion_data.MAPPING[canonical];rest=world_rot@bone.matrix_local.to_3x3()
        direction=(world_rot@(bone.tail_local-bone.head_local)).normalized()
        arm=canonical in {side+part for side in ('Left','Right') for part in ('Arm','ForeArm','Hand')}
        calibration=(direction.rotation_difference(Vector(motion_data.direction(source))).to_matrix()@rest) if arm else rest
        actual=(world@rig.pose.bones[bone.name].matrix).to_quaternion().to_matrix()
        known[source]=conv.transposed()@actual@calibration.transposed()@conv
    for i,name in enumerate(motion_data.NAMES):
        parent=motion_data.PARENTS[i]
        rotation=known.get(name)
        if rotation is None:
            if name=='Neck2':rotation=known['Neck1'].to_quaternion().slerp(known['Head'].to_quaternion(),.5).to_matrix()
            else:rotation=Matrix(globals[parent].tolist()) if parent>=0 else Matrix.Identity(3)
        globals[i]=np.asarray(rotation)
    source_leg=sum(np.linalg.norm(motion_data.OFFSETS[motion_data.NAMES.index('Left'+p)]) for p in ('Shin','Foot'))
    target_leg=sum(((world@mapping['Left'+p].tail_local)-(world@mapping['Left'+p].head_local)).length for p in ('UpLeg','Leg'))
    scale=target_leg/source_leg
    delta=(world@rig.pose.bones[mapping['Hips'].name].head)-(world@mapping['Hips'].head_local)
    root=[delta.x/scale,.988+delta.z/scale,-delta.y/scale]
    row=dict(frame=context.scene.frame_current+context.scene.frame_subframe,root=root,global_rotations=globals.tolist(),basis=basis)
    result=data(rig);current=signature(context,rig)
    if result.get('poses') and result.get('rest_signature')!=current:raise ValueError('Rest joints changed; clear old key poses before capturing new ones')
    result.update(schema_version=1,rest_signature=current)
    result['poses']=[p for p in result['poses'] if abs(p['frame']-row['frame'])>1e-5]+[row]
    result['poses'].sort(key=lambda p:p['frame'])
    if len(result['poses'])>32:raise ValueError('Use at most 32 key poses per character')
    rig[PROPERTY]=json.dumps(result,allow_nan=False);return row

def prepare(context,rig,frames,start_frame,in_place=False):
    result=data(rig)
    if not result.get('poses'):raise ValueError('Capture at least one pose, or turn off Use key poses')
    if result.get('schema_version')!=1 or result.get('rest_signature')!=signature(context,rig):raise ValueError('Key poses belong to edited rest joints or a changed scene scale; capture them again')
    fps=context.scene.render.fps/context.scene.render.fps_base;indices=[]
    if not math.isfinite(fps) or fps<=0 or not math.isfinite(start_frame):raise ValueError('Use a finite start frame and positive scene frame rate')
    poses=[]
    for p in result['poses']:
        p=dict(p)
        validate_basis(rig,p)
        time=(p['frame']-start_frame)*30/fps;index=round(time)
        if time<-.0001 or time>frames-1+.0001:raise ValueError('Key pose at frame '+str(p['frame'])+' lies outside the generated clip; adjust start or length')
        if index in indices:raise ValueError('Two key poses are less than one generated frame apart')
        rotations=np.asarray(p['global_rotations']);root=np.asarray(p['root'])
        if rotations.shape!=(30,3,3) or root.shape!=(3,) or not np.isfinite(rotations).all() or not np.isfinite(root).all():raise ValueError('Invalid key pose data')
        if max(np.abs(rotations@np.swapaxes(rotations,-1,-2)-np.eye(3)).max(),np.abs(np.linalg.det(rotations)-1).max())>1e-4:raise ValueError('Key pose rotations are invalid')
        if in_place and np.linalg.norm(root[[0,2]])>1e-5:raise ValueError('Moving key poses require In place to be turned off')
        p['index']=index;poses.append(p);indices.append(index)
    return dict(schema_version=1,frames=frames,start_frame=start_frame,scene_fps=fps,poses=poses,source_sha256=hashlib.sha256(rig[PROPERTY].encode()).hexdigest())

def write(folder,keys,frames):
    dim=9+12*30;observed=np.zeros((frames,dim),dtype='<f4');mask=np.zeros_like(observed)
    for p in keys['poses']:
        i=p['index'];root=np.asarray(p['root']);global_rot=np.asarray(p['global_rotations']);positions=np.empty((30,3))
        for j,parent in enumerate(motion_data.PARENTS):positions[j]=root if parent<0 else positions[parent]+global_rot[parent]@motion_data.OFFSETS[j]
        diff=positions[motion_data.NAMES.index('RightLeg')]-positions[motion_data.NAMES.index('LeftLeg')]
        angle=math.atan2(diff[2],-diff[0])
        observed[i,:5]=[root[0],root[1],root[2],math.cos(angle),math.sin(angle)]
        relative=positions.copy();relative[:,[0,2]]-=root[[0,2]]
        observed[i,5:95]=relative.ravel();mask[i,:95]=1
        observed[i,95:275]=global_rot[:,:,:2].transpose(0,2,1).reshape(-1)
        for name in ('LeftFoot','RightFoot','LeftHand','RightHand'):
            j=motion_data.NAMES.index(name);mask[i,95+j*6:95+(j+1)*6]=1
    observed.tofile(folder/'observed.f32');mask.tofile(folder/'observed_mask.f32')
    keys['first_heading']=math.atan2(observed[0,4],observed[0,3]) if mask[0,3] else 0.
    return {name:motion_jobs.sha(folder/name) for name in ('observed.f32','observed_mask.f32')}

def overlay(context,rig,keys):
    """Restore exact artist anchors; the intervening body motion is model output.

    Unsupported finger/helper channels interpolate their authored poses. Their
    animation is explicitly not a Kimodo prediction.
    """
    poses=keys['poses'];ordered=sorted(poses,key=lambda p:p['frame']);previous={}
    action=rig.animation_data.action;slot=rig.animation_data.action_slot
    curves={}
    for layer in action.layers:
        for strip in layer.strips:
            bag=strip.channelbag(slot,ensure=False)
            if bag:curves.update({(c.data_path,c.array_index):c for c in bag.fcurves})
    def evaluated(name,frame):
        prefix=rig.pose.bones[name].path_from_id()
        values={key:[curves[(prefix+'.'+key,i)].evaluate(frame) for i in range(count)]
            for key,count in (('location',3),('rotation_quaternion',4),('scale',3))}
        q=Quaternion(values.pop('rotation_quaternion'));q.normalize();values['rotation']=list(q);return values
    def set_basis(name,value,frame):
        pose=rig.pose.bones[name];q=Quaternion(value['rotation'])
        if name in previous and q.dot(previous[name])<0:q.negate()
        pose.rotation_mode='QUATERNION';pose.location=value['location'];pose.rotation_quaternion=q;pose.scale=value['scale'];previous[name]=q.copy()
        for key in ('location','rotation_quaternion','scale'):pose.keyframe_insert(data_path=key,frame=frame,group=name)
    start=keys['start_frame'];fps=keys['scene_fps']
    # Caller records the actual request length; never depend on UI edits.
    end=start+(keys['frames']-1)*fps/30
    sample_frames=[float(f) for f in np.arange(start,end+1e-5,fps/30)]
    # Cache the generated curves before adding keys. Blend only a short
    # correction around each anchor; preserve the model's intervening motion.
    model={(frame,b.name):evaluated(b.name,frame) for frame in sample_frames for b in rig.data.bones}
    residuals=[]
    for index,p in enumerate(ordered):
        radius=4*fps/30
        for neighbor in ordered[max(0,index-1):index]+ordered[index+1:index+2]:radius=min(radius,abs(p['frame']-neighbor['frame'])/2)
        corrections={}
        for name,target in p['basis'].items():
            base=evaluated(name,p['frame']);q=Quaternion(target['rotation'])@Quaternion(base['rotation']).conjugated()
            if q.w<0:q.negate()
            corrections[name]=(q,Vector(target['location'])-Vector(base['location']))
        residuals.append((p['frame'],radius,corrections))
    for frame in sample_frames:
        for name in rig.data.bones.keys():
            canonical=skeleton.canonical_name(name)
            if canonical!='Root' and canonical not in motion_data.MAPPING:continue
            for anchor,radius,corrections in residuals:
                weight=max(0.,1-abs(frame-anchor)/radius)
                if weight<=0:continue
                value=model[(frame,name)];q,delta=corrections[name]
                adjusted=dict(rotation=list(Quaternion().slerp(q,weight)@Quaternion(value['rotation'])),
                    location=list(Vector(value['location'])+delta*weight),scale=value['scale'])
                set_basis(name,adjusted,frame);break
    previous={}
    for frame in sample_frames:
        for module in twists.modules(rig):
            value=evaluated(module['source'],frame)
            value['rotation']=list(twists.reduced(Quaternion(value['rotation']),module['fraction']))
            set_basis(module['helper'],value,frame)
    previous={}
    for frame in sample_frames:
        before=max((p for p in ordered if p['frame']<=frame),key=lambda p:p['frame'],default=ordered[0])
        after=min((p for p in ordered if p['frame']>=frame),key=lambda p:p['frame'],default=ordered[-1])
        a=0 if before['frame']==after['frame'] else (frame-before['frame'])/(after['frame']-before['frame'])
        for name in rig.data.bones.keys():
            canonical=skeleton.canonical_name(name)
            if canonical=='Root' or canonical in motion_data.MAPPING or 'Twist' in name:continue
            lo,hi=before['basis'][name],after['basis'][name]
            value=dict(rotation=list(Quaternion(lo['rotation']).slerp(Quaternion(hi['rotation']),a)),
                location=list(Vector(lo['location']).lerp(Vector(hi['location']),a)),scale=list(Vector(lo['scale']).lerp(Vector(hi['scale']),a)))
            set_basis(name,value,float(frame))
    previous={}
    for p in ordered:
        for name,value in p['basis'].items():set_basis(name,value,p['frame'])
    # Every quaternion component shares a sample grid. Normalize signs across
    # both the generated keys and newly inserted (possibly subframe) anchors.
    for bone in rig.pose.bones:
        path=bone.path_from_id()+'.rotation_quaternion'
        rows=[curves[(path,i)].keyframe_points for i in range(4)];last=None
        for points in zip(*rows):
            q=Quaternion([p.co.y for p in points]);q.normalize()
            if last is not None and q.dot(last)<0:q.negate()
            for point,value in zip(points,q):point.co.y=value
            last=q
    for curve in curves.values():
        for point in curve.keyframe_points:point.interpolation='LINEAR'
        curve.update()
    action['lc_key_pose_frames']=json.dumps([p['frame'] for p in ordered]);action['lc_key_pose_settling_frames']=4

class LC_OT_capture_key_pose(Operator):
    bl_idname='local_character.capture_key_pose';bl_label='Capture Pose';bl_options={'REGISTER','UNDO'}
    bl_description='Capture this humanoid pose at the current timeline frame; the original Action remains unchanged'
    @classmethod
    def poll(cls,context):return context.mode in {'OBJECT','POSE'} and not skinning._jobs
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);p=capture(context,rig)
            context.scene.lc_settings.motion_use_keyframes=True;context.scene.lc_settings.ui_step='MOTION'
            self.report({'INFO'},'Pose captured at frame '+str(p['frame']))
        except (ValueError,RuntimeError,KeyError) as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

class LC_OT_key_pose(Operator):
    bl_idname='local_character.key_pose';bl_label='Key Pose';bl_options={'REGISTER','UNDO'}
    frame:FloatProperty(default=-1,options={'HIDDEN'})
    remove:bpy.props.BoolProperty(default=False,options={'HIDDEN'})
    clear:bpy.props.BoolProperty(default=False,options={'HIDDEN'})
    @classmethod
    def poll(cls,context):return context.mode in {'OBJECT','POSE'} and not skinning._jobs
    def execute(self,context):
        try:
            rig=motion_jobs.selected_rig(context);keys=data(rig)
            if self.remove or self.clear:
                keys['poses']=[] if self.clear else [p for p in keys['poses'] if abs(p['frame']-self.frame)>1e-5]
                rig[PROPERTY]=json.dumps(keys);return {'FINISHED'}
            if keys.get('rest_signature')!=signature(context,rig):raise ValueError('Rest joints changed; capture new key poses')
            p=next(p for p in keys['poses'] if abs(p['frame']-self.frame)<1e-5)
            validate_basis(rig,p)
            context.scene.frame_set(math.floor(p['frame']),subframe=p['frame']%1)
            for name,value in p['basis'].items():
                pose=rig.pose.bones[name];pose.rotation_mode='QUATERNION';pose.location=value['location'];pose.rotation_quaternion=value['rotation'];pose.scale=value['scale']
            context.view_layer.update()
            self.report({'INFO'},'Pose recalled for editing; Capture Pose saves changes. The source Action is unchanged')
        except (ValueError,RuntimeError,KeyError,StopIteration) as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

CLASSES=(LC_OT_capture_key_pose,LC_OT_key_pose)
