# SPDX-License-Identifier: GPL-3.0-or-later
"""Capture requests and transactional application through the existing worker UI."""
import json,os,sys,tempfile,shutil,uuid
from pathlib import Path
import bpy
from bpy.types import Operator
from . import configuration,skinning,image_pose,motion_jobs,motion_store,rig_mapping,animation_transfer,character_context,video_setup


def cache():return skinning.provider_cache().parent/'video-capture'


def runtime():
    base=Path('R:/AI/Rigmodo/Runtime/VideoCapture') if Path('R:/').exists() else cache()/'runtime'
    return base/'Scripts/python.exe'


def start(context,kind=None):
    if skinning._jobs:raise ValueError('Wait for the current task to finish')
    s=context.scene.lc_settings;p=configuration.settings(context);rig=motion_jobs.selected_rig(context)
    kind=kind or ('comfy' if s.animation_source=='TEXT' else 'video')
    if context.mode!='OBJECT':raise ValueError('Return to Object Mode before creating an animation')
    if kind!='animation' and not set(rig_mapping.CORE)<=set(rig_mapping.names(rig)):raise ValueError('Video capture currently needs a mapped humanoid; review Bone mapping')
    meshes=motion_jobs.character_meshes(context,rig)
    jobs=Path(bpy.path.abspath(p.video_jobs))
    request=dict(id=uuid.uuid4().hex,kind=kind,rig=rig.name,rig_pointer=rig.as_pointer(),scene_pointer=context.scene.as_pointer(),meshes=[m.name for m in meshes],signature=skinning._digest(rig,meshes),
                 in_place=s.motion_in_place,loop=s.create_loop,contacts=s.motion_contacts,ground=s.ground_height,
                 video=bpy.path.abspath(s.video_path),cycle_method=s.video_cycle,start=s.video_start,duration=s.motion_duration,prompt=s.motion_prompt,seed=p.motion_seed,
                 models=str(Path(bpy.path.abspath(p.models_directory))/'gemx'),camera_mode=p.capture_camera,
                 ffmpeg=bpy.path.abspath(p.video_ffmpeg),ffprobe=bpy.path.abspath(p.video_ffprobe),comfy_url=p.comfy_url,
                 model=p.comfy_model,clip=p.comfy_clip,vae=p.comfy_vae,audio_vae=p.comfy_audio_vae,reference=bpy.path.abspath(s.video_reference) if s.video_reference else '',
                 output_node=p.comfy_output_node,workflow=bpy.path.abspath(p.comfy_workflow) if p.comfy_workflow else '',bindings=json.loads(p.comfy_bindings),shot_rules=p.comfy_shot_rules)
    if kind=='animation':
        source=Path(bpy.path.abspath(s.animation_file))
        if not source.is_file() or source.suffix.lower() not in {'.fbx','.glb','.gltf','.blend','.bvh'}:raise ValueError('Choose an FBX, BVH, GLB, glTF or Blender animation file')
        request['file']=str(source)
        command=[bpy.app.binary_path,'--factory-startup','--background','--disable-autoexec','--python',str(Path(__file__).with_name('animation_import_worker.py')),'--','JOB']
    else:
        python=Path(bpy.path.abspath(p.capture_python))
        if not video_setup.ready(python,request['models']):raise ValueError('Install or verify Video Capture in Extension Settings → Setup')
        for key in ('ffmpeg','ffprobe'):
            if not Path(request[key]).is_file() and not shutil.which(request[key]):raise ValueError('Set '+key+' in Extension Settings')
        if kind=='video' and not Path(request['video']).is_file():raise ValueError('Choose a video file')
        if kind=='comfy' and request['loop'] and not request['reference']:raise ValueError('Choose a reference image or use Use Character Image for a generated loop')
        if request['reference'] and not Path(request['reference']).is_file():raise ValueError('Reference image was not found')
        command=[str(python),str(Path(__file__).with_name('video_worker.py')),'--','JOB']
    jobs.mkdir(parents=True,exist_ok=True);folder=Path(tempfile.mkdtemp(prefix='motion-',dir=jobs))
    command[-1]=str(folder)
    motion_store.atomic(folder/'request.json',request);s.video_job=str(folder)
    image_pose.launch(folder,command,'Creating animation')
    if not bpy.app.background:bpy.ops.local_character.run_video_job()
    return {'FINISHED'}


_release_watchers=set()

def watch_release(path):
    from .comfy_video import Client,release_job
    import time
    deadline=time.monotonic()+7200;lookup_deadline=time.monotonic()+60
    def tick():
        again=None
        try:
            data=json.loads(Path(path).read_text());client=Client(data['url']);prompt=client.find_prompt(data)
            q=client.request('/queue',timeout=1)
            if prompt and any(entry[1]==prompt for entry in q.get('queue_running',[])+q.get('queue_pending',[])) and time.monotonic()<deadline:
                client.cancel(prompt);again=2.
            elif not prompt and time.monotonic()<lookup_deadline:again=2.
            else:release_job(Path(path).parent)
        except (OSError,ValueError,KeyError):pass
        if again is None:_release_watchers.discard(tick)
        return again
    _release_watchers.add(tick);bpy.app.timers.register(tick,first_interval=1.,persistent=True)


def cleanup():
    for callback in _release_watchers:
        if bpy.app.timers.is_registered(callback):bpy.app.timers.unregister(callback)
    _release_watchers.clear()


def cancel_external(folder):
    from .comfy_video import Client
    for path in (Path(folder)/'comfy.json',Path(folder)/'bridge/comfy.json'):
        if path.is_file():
            data=json.loads(path.read_text());client=Client(data['url']);prompt=client.find_prompt(data)
            if prompt:client.cancel(prompt)
            watch_release(path)
    return 'Cancelled'


class LC_OT_video_motion(Operator):
    bl_idname='local_character.video_motion';bl_label='Create Animation from Video'
    def execute(self,context):
        try:return start(context)
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_OT_finish_video(Operator):
    bl_idname='local_character.finish_video_motion';bl_label='Apply Captured Animation';bl_options={'UNDO'}
    def execute(self,context):
        try:
            s=context.scene.lc_settings;folder=Path(s.video_job);request=json.loads((folder/'request.json').read_text());result=json.loads((folder/'results.json').read_text())
            rig=bpy.data.objects.get(request['rig']);meshes=[bpy.data.objects.get(n) for n in request['meshes']]
            if not rig or rig.as_pointer()!=request['rig_pointer'] or context.scene.as_pointer()!=request['scene_pointer'] or any(m is None for m in meshes) or skinning._digest(rig,meshes)!=request['signature']:raise ValueError('Source character changed during processing; its captured result remains in the job folder')
            data=motion_store.read_file(folder/'output.npz')
            old={key:getattr(s,key) for key in ('motion_in_place','create_loop','motion_contacts','ground_height')}
            try:
                s.motion_in_place=request['in_place'];s.create_loop=request['loop'];s.motion_contacts=request['contacts'];s.ground_height=request['ground']
                metadata=dict(lc_library_source='ComfyUI video capture' if request['kind']=='comfy' else 'User animation' if request['kind']=='animation' else 'User video capture',lc_library_license='User-provided',lc_capture_job=str(folder),lc_capture_video=result.get('video',''),lc_capture_offset_seconds=result.get('source',{}).get('capture_start',0)+result.get('metrics',{}).get('selected_cycle',{}).get('start_seconds',0),lc_motion_prompt=request['prompt'],lc_capture_provenance=json.dumps(dict(source=result.get('source',{}),metrics=result.get('metrics',{}),workflow=request.get('workflow') or 'builtin-h3-v1',loop=request['loop'],in_place=request['in_place'])))
                action=animation_transfer.finish(context,rig,data,result.get('name') or ('Captured Motion' if request['kind']!='animation' else 'Retargeted Motion'),metadata)
            finally:
                for key,value in old.items():setattr(s,key,value)
            quality=result.get('metrics',{}).get('quality',{})
            uncertain=len(quality.get('missing_track_frames',[]))+len(quality.get('low_confidence_frames',[]))
            if uncertain:s.motion_status=f'Animation ready · review {uncertain} low-confidence capture samples'
            if result.get('video'):s.video_path=result['video']
            character_context.pin(context,rig,meshes)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'Created '+action.name);return {'FINISHED'}


class LC_OT_comfy_check(Operator):
    bl_idname='local_character.check_comfy';bl_label='Check ComfyUI Connection'
    def execute(self,context):
        try:
            from .comfy_video import Client
            p=configuration.settings(context);client=Client(p.comfy_url);nodes=client.request('/object_info');q,_=client.queued_ids()
            self.report({'INFO'},f"Connected · {len(nodes)} node types · {len(q.get('queue_running',[]))} running jobs")
        except (ValueError,OSError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_retry_video(Operator):
    bl_idname='local_character.retry_video_motion';bl_label='Retry Last Video Job'
    def execute(self,context):
        try:
            if skinning._jobs:raise ValueError('Wait for the current task to finish')
            settings=context.scene.lc_settings;p=configuration.settings(context);folder=Path(settings.video_job)
            request=json.loads((folder/'request.json').read_text());rig=bpy.data.objects.get(request['rig']);meshes=[bpy.data.objects.get(n) for n in request['meshes']]
            if request['kind'] not in {'video','comfy'}:raise ValueError('Create a new animation import instead')
            if not rig or rig.as_pointer()!=request['rig_pointer'] or context.scene.as_pointer()!=request['scene_pointer'] or any(m is None for m in meshes) or skinning._digest(rig,meshes)!=request['signature']:raise ValueError('The source character changed; create a new job')
            image_pose.launch(folder,[bpy.path.abspath(p.capture_python),str(Path(__file__).with_name('video_worker.py')),'--',str(folder)],'Resuming animation')
            if not bpy.app.background:bpy.ops.local_character.run_video_job()
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_release_comfy_memory(Operator):
    bl_idname='local_character.release_comfy_memory';bl_label='Release ComfyUI GPU Memory'
    bl_description='Unload idle ComfyUI models; skip while its queue is busy. Models reload on the next generation'
    def execute(self,context):
        try:
            from .comfy_video import Client
            result=Client(configuration.settings(context).comfy_url).release_models()
            self.report({'INFO'} if result['released'] else {'WARNING'},result['reason'])
        except (OSError,ValueError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


CLASSES=(LC_OT_release_comfy_memory,LC_OT_video_motion,LC_OT_finish_video,LC_OT_comfy_check,LC_OT_retry_video)
