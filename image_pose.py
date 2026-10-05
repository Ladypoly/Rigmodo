# SPDX-License-Identifier: GPL-3.0-or-later
"""Scoped image drops, owned local inference and undoable in-place pose retargeting."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from types import SimpleNamespace
import bpy
import numpy as np
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator, FileHandler
from bpy.app.handlers import persistent
from bpy_extras.io_utils import ImportHelper
from mathutils import Matrix, Vector
from . import auto_pose, configuration, motion_keyframes, motion_jobs, skeleton, skinning, twists, process_tree
from .sam_pose_protocol import SAM_REV, MAPPING, MODELS, sha

EXTENSIONS={'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}
_pending=None
_native_drop_patch=None

def drop_surface(context):
    return bool(context.area and context.area.type=='VIEW_3D' and context.region and context.region.type=='UI'
                and context.region.active_panel_category=='Rigmodo'
                and context.scene.lc_settings.ui_step=='MOTION' and context.mode in {'OBJECT','POSE'}
                and context.active_object and context.active_object.type=='ARMATURE')

def cache():return skinning.provider_cache().parent/'sam-3d-body-b5c765a'

def selected(context):
    rig=context.active_object
    if context.mode not in {'OBJECT','POSE'} or not rig or rig.type!='ARMATURE' or not rig.select_get():
        raise ValueError('Select the humanoid armature in Object or Pose Mode')
    return rig

def validate(context,rig):
    if auto_pose._sessions:raise ValueError('Confirm or cancel the current Auto Pose gesture first')
    # Direct RNA channel assignment never invokes Blender's transform Auto Key.
    # Reuse rig validation while allowing Auto Key to stay enabled for other tools.
    validation_context=SimpleNamespace(screen=context.screen,
        scene=SimpleNamespace(tool_settings=SimpleNamespace(use_keyframe_insert_auto=False)))
    mapping=auto_pose.validate(validation_context,rig)
    if rig.animation_data and any(not track.mute for track in rig.animation_data.nla_tracks):
        raise ValueError('Mute NLA tracks before applying an image pose')
    for name in MAPPING:
        p=mapping.get(name)
        if p and (any(p.lock_rotation) or p.lock_rotation_w):raise ValueError('Unlock pose rotation channels before applying an image pose')
    return mapping

def fingerprint(context,rig):
    # Protect the artist's frame, Action assignment, exact channels, rest data and world placement.
    ad=rig.animation_data
    values=[str(context.scene.as_pointer()),str(rig.as_pointer()),str(rig.data.as_pointer()),
            motion_keyframes.signature(context,rig),context.scene.frame_current,context.scene.frame_subframe,
            str(ad.action.as_pointer()) if ad and ad.action else None,
            [(p.name,p.rotation_mode,list(p.location),list(p.scale),list(p.rotation_quaternion),
              list(p.rotation_euler),list(p.rotation_axis_angle)) for p in rig.pose.bones]]
    return hashlib.sha256(json.dumps(values,allow_nan=False).encode()).hexdigest()

def read_result(folder):
    folder=Path(folder)
    if (folder/'pose.json').stat().st_size>250_000:raise ValueError('Image pose result is too large')
    request=json.loads((folder/'request.json').read_text())
    if sha(folder/'request.json')!=(folder/'request.sha256').read_text():raise ValueError('Image pose request changed')
    if sha(folder/request['input_file'])!=request['input_sha256']:raise ValueError('Image input changed')
    if sha(folder/'pose.json')!=(folder/'pose.sha256').read_text():raise ValueError('Image pose result changed')
    result=json.loads((folder/'pose.json').read_text())
    if result.get('request_sha256')!=sha(folder/'request.json') or result.get('input_sha256')!=request['input_sha256']:
        raise ValueError('Image pose belongs to a different request')
    check_pose(result)
    return request,result

def check_pose(result):
    if (result.get('schema_version'),result.get('provider'),result.get('source_revision'),result.get('coordinates'))!=(1,'sam-3d-body',SAM_REV,'MHR_Y_UP'):
        raise ValueError('Unsupported image pose format or provider revision')
    if set(result['joints'])!=set(MAPPING):raise ValueError('Image pose humanoid joints are incomplete')
    for row in result['joints'].values():
        for key in ('rotation','neutral_rotation'):
            r=np.asarray(row[key],dtype=float)
            if r.shape!=(3,3) or not np.isfinite(r).all() or np.max(np.abs(r.T@r-np.eye(3)))>3e-4 or abs(np.linalg.det(r)-1)>3e-4:
                raise ValueError('Image pose contains an invalid rotation')
        d=row['neutral_direction']
        if d is not None:
            a=np.asarray(d,dtype=float)
            if a.shape!=(3,) or not np.isfinite(a).all() or np.linalg.norm(a)<1e-6:raise ValueError('Invalid source bone calibration')

def bases_for(rig,result,hands=True):
    """Global anatomical rotation deltas with MHR A-pose calibration for arms/digits.

    MHR has four spine joints and additional wrist/ankle rotations. Accumulated
    globals collapse them without dropping articulation. Target FK alone determines
    every joint position: source translations, scale and mesh are never applied.
    """
    check_pose(result)
    conversion=Matrix(((1,0,0),(0,0,-1),(0,1,0)))
    mapping={skeleton.canonical_name(b.name):b for b in rig.data.bones}
    root=mapping['Root'];root_pose=rig.pose.bones[root.name].matrix.copy()
    anchor=root_pose.to_quaternion().to_matrix()@root.matrix_local.to_quaternion().to_matrix().transposed()
    poses={};bases={}
    for bone in sorted(rig.data.bones,key=lambda b:len(b.parent_recursive)):
        p=rig.pose.bones[bone.name];name=skeleton.canonical_name(bone.name)
        parent=poses.get(bone.parent.name,Matrix.Identity(4)) if bone.parent else Matrix.Identity(4)
        inherited=bone.convert_local_to_pose(p.matrix_basis,bone.matrix_local,parent_matrix=parent,
                    parent_matrix_local=bone.parent.matrix_local if bone.parent else Matrix.Identity(4))
        row=result['joints'].get(name)
        if row and (hands or not ('Hand' in name and name[-1:] in {'1','2','3'})):
            rest=bone.matrix_local.to_quaternion().to_matrix()
            neutral=Matrix(row['neutral_rotation']);posed=Matrix(row['rotation'])
            alignment=Matrix.Identity(3)
            if row['neutral_direction'] is not None:
                source=conversion@Vector(row['neutral_direction'])
                alignment=(bone.tail_local-bone.head_local).rotation_difference(source).to_matrix()
            orientation=anchor@conversion@posed@neutral.transposed()@conversion.transposed()@alignment@rest
            target=orientation.to_4x4();target.translation=inherited.translation
        else:target=inherited
        poses[bone.name]=target
    twists.update_matrices(rig,poses)
    for bone in rig.data.bones:
        basis=bone.convert_local_to_pose(poses[bone.name],bone.matrix_local,
            parent_matrix=poses[bone.parent.name] if bone.parent else Matrix.Identity(4),
            parent_matrix_local=bone.parent.matrix_local if bone.parent else Matrix.Identity(4),invert=True)
        if any(not np.isfinite(v) for row in basis for v in row):raise ValueError('Retargeted pose is not finite')
        bases[bone.name]=basis
    return bases

def apply(context,rig,result,hands=True):
    validate(context,rig)
    context.view_layer.update()
    snapshot=auto_pose.channel_snapshot(rig)
    bases=bases_for(rig,result,hands)
    changed=set(result['joints'])
    if not hands:changed={n for n in changed if not ('Hand' in n and n[-1:] in {'1','2','3'})}
    changed.update(skeleton.canonical_name(m['helper']) for m in twists.modules(rig))
    try:
        for p in rig.pose.bones:
            if skeleton.canonical_name(p.name) not in changed:continue
            q=bases[p.name].to_quaternion()
            if p.rotation_mode=='QUATERNION':
                if q.dot(snapshot[p.name]['quaternion'])<0:q.negate()
                p.rotation_quaternion=q
            elif p.rotation_mode=='AXIS_ANGLE':p.rotation_axis_angle=(q.angle,*q.axis)
            else:p.rotation_euler=q.to_euler(p.rotation_mode,snapshot[p.name]['euler'])
        context.view_layer.update()
    except Exception:
        auto_pose.restore_channels(rig,snapshot);context.view_layer.update();raise
    return len(changed & {skeleton.canonical_name(p.name) for p in rig.pose.bones})

def launch(folder,command,phase):
    log=(folder/'worker.log').open('wb');process=None;job=None
    try:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        if os.name=='nt':job=process_tree.WindowsJob(process)
        skinning._jobs[str(folder)]=dict(process=process,log=log,job_object=job,started=time.monotonic(),phase=phase)
        skinning._state(folder,'running',pid=process.pid)
    except Exception:
        if job:job.close()
        if process:process.terminate();process.wait(timeout=3)
        log.close();raise

def prepare(context,rig,path,provider,hands=True,parent=None):
    validate(context,rig)
    context.view_layer.update()
    path=Path(path).resolve();provider=Path(provider).resolve()
    if path.suffix.lower() not in EXTENSIONS or not path.is_file():raise ValueError('Choose a PNG, JPEG, WebP, BMP or TIFF image')
    if not 0<path.stat().st_size<=50_000_000:raise ValueError('Use an image smaller than 50 MB')
    directory=Path(parent) if parent else cache().parent.parent/'jobs';directory.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='image-pose-',dir=directory)).resolve()
    image='input'+path.suffix.lower();shutil.copyfile(path,folder/image)
    request=dict(schema_version=1,provider=str(provider),source_revision=SAM_REV,input_file=image,input_sha256=sha(folder/image),
                 rig=rig.name,rig_pointer=str(rig.as_pointer()),fingerprint=fingerprint(context,rig),hands=bool(hands))
    (folder/'request.json').write_text(json.dumps(request,indent=2,allow_nan=False));(folder/'request.sha256').write_text(sha(folder/'request.json'))
    skinning._state(folder,'prepared');return folder

def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':area.tag_redraw()

def tick():
    global _pending
    if not _pending:return None
    folder,scene,kind=_pending
    try:
        if scene not in list(bpy.data.scenes):raise ValueError('Original scene closed')
        state=skinning.poll(folder)
        if state['status']=='running':
            scene.lc_settings.image_pose_status=f"{state.get('phase','Estimating pose')} · {state['elapsed_seconds']:.0f}s";redraw();return .5
        _pending=None
        if state['status']!='complete':raise ValueError(state.get('error') or 'Image pose job cancelled')
        if kind=='setup':scene.lc_settings.image_pose_status='SAM 3D Body is ready'
        else:
            if bpy.context.scene!=scene:raise ValueError('Scene changed; original pose was left intact')
            status=bpy.ops.local_character.apply_image_pose(folder=str(folder),async_undo=True)
            if status!={'FINISHED'}:raise ValueError('Pose could not be applied; original pose was left intact')
    except (ValueError,OSError,KeyError,RuntimeError,ReferenceError) as error:
        skinning.cancel(folder);_pending=None
        if scene in list(bpy.data.scenes):scene.lc_settings.image_pose_status=str(error)
    redraw();return None

def begin(context,folder,kind):
    global _pending
    _pending=(folder,context.scene,kind)
    context.scene.lc_settings.image_pose_job=str(folder)
    if not bpy.app.timers.is_registered(tick):bpy.app.timers.register(tick,first_interval=.5)
    redraw()

def cleanup():
    global _pending
    if _pending:
        skinning.cancel(_pending[0]);_pending=None
    if bpy.app.timers.is_registered(tick):bpy.app.timers.unregister(tick)

@persistent
def reset_jobs(_):cleanup()

def register():
    global _native_drop_patch
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if reset_jobs not in handlers:handlers.append(reset_jobs)
    # Blender's stock reference-image handler polls every View3D region, including
    # sidebars. Yield only the active Rigmodo image-pose surface so a native file
    # drop invokes our operator directly rather than opening an import-choice menu.
    if _native_drop_patch is None:
        for cls in FileHandler.__subclasses__():
            if cls.__name__=='VIEW3D_FH_empty_image':
                original=cls.__dict__['poll_drop']
                def scoped(owner,context):
                    if _native_drop_patch is not None and drop_surface(context):return False
                    return original.__func__(owner,context)
                replacement=classmethod(scoped);cls.poll_drop=replacement
                _native_drop_patch=(cls,original,replacement);break

def unregister():
    global _native_drop_patch
    cleanup()
    if _native_drop_patch:
        cls,original,replacement=_native_drop_patch
        if cls.__dict__.get('poll_drop') is replacement:cls.poll_drop=original
        _native_drop_patch=None
    for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if reset_jobs in handlers:handlers.remove(reset_jobs)

class LC_OT_image_pose(Operator,ImportHelper):
    bl_idname='local_character.image_pose'
    bl_label='Pose from Image'
    bl_description='Apply one person’s image pose to the selected humanoid; preserve mesh, skeleton and Action'
    filename_ext='.png'
    filter_glob:StringProperty(default='*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff',options={'HIDDEN'})
    filepath:StringProperty(subtype='FILE_PATH',options={'SKIP_SAVE'})
    @classmethod
    def poll(cls,context):
        return context.mode in {'OBJECT','POSE'} and context.active_object is not None and context.active_object.type=='ARMATURE' and not skinning._jobs and not _pending and not auto_pose._sessions
    def invoke(self,context,event):
        if self.filepath:return self.execute(context)
        return ImportHelper.invoke(self,context,event)
    def execute(self,context):
        try:
            settings=configuration.settings(context);provider=Path(bpy.path.abspath(settings.image_pose_provider))
            if not (provider/'installation.json').is_file() or not (provider/'runtime/Scripts/python.exe').is_file():
                raise ValueError('Set up SAM 3D Body in Rigmodo Extension Settings first')
            rig=selected(context);folder=prepare(context,rig,bpy.path.abspath(self.filepath),provider,settings.image_pose_hands)
            launch(folder,[str(provider/'runtime/Scripts/python.exe'),'-I',str(Path(__file__).with_name('sam_pose_worker.py')),str(folder)],'Estimating image pose')
            begin(context,folder,'pose')
        except (ValueError,OSError,RuntimeError) as error:
            context.scene.lc_settings.image_pose_status=str(error);self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

class LC_OT_apply_image_pose(Operator):
    bl_idname='local_character.apply_image_pose';bl_label='Apply Image Pose';bl_options={'UNDO'}
    folder:StringProperty(subtype='DIR_PATH',options={'SKIP_SAVE'})
    async_undo:BoolProperty(default=False,options={'HIDDEN','SKIP_SAVE'})
    def execute(self,context):
        snapshot=None;rig=None
        try:
            folder=Path(self.folder)
            if skinning.poll(folder)['status']!='complete':raise ValueError('Image inference has not completed')
            request,result=read_result(folder);rig=selected(context);context.view_layer.update()
            if str(rig.as_pointer())!=request['rig_pointer'] or fingerprint(context,rig)!=request['fingerprint']:
                raise ValueError('Selection, frame, rig or pose changed during inference; choose the image again')
            snapshot=auto_pose.channel_snapshot(rig)
            # Timer-invoked Python operators do not get the window event loop's
            # automatic Undo push. Capture both boundaries explicitly for that path.
            if self.async_undo and not bpy.app.background:bpy.ops.ed.undo_push(message='Before Image Pose')
            count=apply(context,rig,result,request['hands']);skinning._state(folder,'applied')
            context.scene.lc_settings.image_pose_status=f'Image pose applied · {count} joints. Review, then Capture Pose or Insert Pose Key.'
            if self.async_undo and not bpy.app.background:bpy.ops.ed.undo_push(message='Apply Image Pose')
        except (ValueError,OSError,KeyError,RuntimeError) as error:
            if snapshot is not None and rig:
                auto_pose.restore_channels(rig,snapshot);context.view_layer.update()
            context.scene.lc_settings.image_pose_status=str(error);self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

class LC_OT_cancel_image_pose(Operator):
    bl_idname='local_character.cancel_image_pose';bl_label='Cancel'
    @classmethod
    def poll(cls,context):return _pending is not None
    def execute(self,context):
        cleanup();context.scene.lc_settings.image_pose_status='Cancelled; original pose kept';redraw();return {'FINISHED'}

class LC_OT_setup_image_pose(Operator):
    bl_idname='local_character.setup_image_pose';bl_label='Install Image Pose Provider'
    @classmethod
    def poll(cls,context):return not skinning._jobs and not _pending and not auto_pose._sessions
    def execute(self,context):
        try:
            s=configuration.settings(context);provider=Path(bpy.path.abspath(s.image_pose_provider)).resolve()
            python=Path(bpy.path.abspath(s.setup_python))
            if not python.is_file():raise ValueError('Choose Python 3.11 in Extension Settings')
            jobs=cache().parent.parent/'jobs';jobs.mkdir(parents=True,exist_ok=True)
            folder=Path(tempfile.mkdtemp(prefix='sam-setup-',dir=jobs)).resolve()
            launch(folder,[str(python),'-I',str(Path(__file__).with_name('sam_pose_install.py')),'--provider',str(provider),
                           '--models',bpy.path.abspath(s.image_pose_models)],'Installing image-pose runtime and approved checkpoints')
            begin(context,folder,'setup')
        except (ValueError,OSError,RuntimeError) as error:self.report({'ERROR'},str(error));return {'CANCELLED'}
        return {'FINISHED'}

class LC_FH_image_pose(FileHandler):
    bl_idname='LC_FH_image_pose';bl_label='Rigmodo Pose from Image'
    bl_import_operator='local_character.image_pose'
    bl_file_extensions=';'.join(sorted(EXTENSIONS))
    @classmethod
    def poll_drop(cls,context):
        return drop_surface(context) and LC_OT_image_pose.poll(context)

def draw(layout,context):
    box=layout.box();box.label(text='Pose from Image',icon='IMAGE_DATA')
    if _pending:
        box.operator('local_character.cancel_image_pose',icon='X')
    else:
        box.operator('local_character.image_pose',text='Choose Image…',icon='FILE_IMAGE')
        box.label(text='Or drop an image into this sidebar.')
    if context.scene.lc_settings.image_pose_status:
        from .ui import message
        message(box,context.scene.lc_settings.image_pose_status)

CLASSES=(LC_OT_image_pose,LC_OT_apply_image_pose,LC_OT_cancel_image_pose,LC_OT_setup_image_pose,LC_FH_image_pose)
