# SPDX-License-Identifier: GPL-3.0-or-later
"""Independent motion creation, source selection and explicit character retargeting."""
import json,math,tempfile,uuid
from pathlib import Path
import bpy
import numpy as np
from bpy.types import Operator,UIList,OperatorFileListElement
from bpy.props import StringProperty,CollectionProperty,EnumProperty
from bpy_extras.io_utils import ImportHelper
from . import configuration,skinning,image_pose,motion_jobs,motionbricks,unimate,motion_store,motion_library,motion_assets,motion_clips,motion_playback,animation_transfer,rig_mapping,video_motion,video_setup

VIDEO_EXTENSIONS={'.mp4','.mov','.mkv','.webm','.avi','.m4v'}
_retarget=None
_preview=None


def busy():return bool(skinning._jobs or _retarget)


def snapshot(rig,folder,request):
    names=[b.name for b in rig.data.bones];rest=np.asarray([b.matrix_local for b in rig.data.bones],dtype=np.float32)
    data=dict(names=np.asarray(names),parents=np.asarray([names.index(b.parent.name) if b.parent else -1 for b in rig.data.bones],dtype=np.int32),rest=rest,poses=np.repeat(rest[None],2,axis=0),times=np.asarray([0,1/30],dtype=np.float32),labels=np.asarray([getattr(b,'lc_unimate_label',b.get('lc_unimate_label','')) for b in rig.data.bones]),lengths=np.asarray([b.length for b in rig.data.bones],dtype=np.float32))
    roles=rig_mapping.names(rig)
    if roles!=names:data['roles']=np.asarray(roles)
    motion_store.validate(data);path=folder/'source-rest.npz';np.savez_compressed(path,**data)
    request.update(source_rest_sha256=motion_jobs.sha(path),source_world=[list(row) for row in rig.matrix_world],source_properties={k:rig[k] for k in ('lc_twists','lc_humanoid_roles','lc_rig_type') if k in rig})


def start(context,files=()):
    if busy():raise ValueError('Wait for the current motion task to finish')
    stop_preview(context);s=context.scene.lc_settings;p=configuration.settings(context);system=s.motion_system
    jobs=Path(bpy.path.abspath(p.video_jobs));jobs.mkdir(parents=True,exist_ok=True);folder=Path(tempfile.mkdtemp(prefix='source-',dir=jobs))
    name=s.source_name.strip() or (s.motion_prompt.strip()[:90] if system in {'KIMODO','UNIMATE'} else 'Pose transition' if system=='MOTIONBRICKS' else '')
    request=dict(id=uuid.uuid4().hex,system=system,name=name,prompt=s.motion_prompt,library=str(motion_library.root(context)),model_root=bpy.path.abspath(p.models_directory),loop=s.source_loop,in_place=s.source_in_place,unit_scale=context.scene.unit_settings.scale_length)
    rig=None
    if system in {'KIMODO','MOTIONBRICKS','UNIMATE'}:
        if system=='KIMODO':
            rig=s.pose_source_rig if s.motion_use_keyframes else None
            if s.motion_use_keyframes and rig is None:raise ValueError('Choose a pose rig, or disable Use pose keys')
            model=motion_jobs.prepare(context,rig,s.motion_prompt,min(900,round(s.motion_duration*30)+1),p.motion_steps,p.motion_seed,False,parent=folder,keyframes=s.motion_use_keyframes,start_frame=context.scene.frame_start)
            request['provider']=bpy.path.abspath(p.motion_provider)
        elif system=='MOTIONBRICKS':
            rig=s.pose_source_rig
            if not rig:raise ValueError('Choose or create a pose rig and insert at least two pose keys')
            model=motionbricks.prepare(context,rig,p.motion_seed,False,bpy.path.abspath(p.motionbricks_provider),parent=folder)
        else:
            rig=s.pose_source_rig
            if not rig:raise ValueError('Choose the creature skeleton that defines this motion')
            model=unimate.prepare(context,rig,s.motion_prompt,min(60,max(15,round(s.motion_duration*30)+1)),p.motion_seed,False,rig.lc_unimate_forward,s.unimate_guidance,bpy.path.abspath(p.unimate_provider),parent=folder)
        if not model.resolve().is_relative_to(folder.resolve()) or (folder/'model').exists():raise ValueError('Invalid source job directory')
        model=model.rename(folder/'model')
        if system!='UNIMATE' and s.source_loop:
            native=json.loads((model/'request.json').read_text())
            animation_transfer.validate_key_loop(model,native,s.source_in_place)
        if rig:snapshot(rig,folder,request)
    else:
        system='VIDEO' if s.video_input=='FILES' else 'COMFY';request['system']=system
        if not video_setup.ready(bpy.path.abspath(p.capture_python),Path(bpy.path.abspath(p.models_directory))/'gemx'):raise ValueError('Install or verify Video Capture in Extension Settings')
        paths=list(map(Path,files)) or ([Path(bpy.path.abspath(s.video_path))] if system=='VIDEO' else [])
        if system=='VIDEO' and (not paths or any(not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS for path in paths)):raise ValueError('Choose video files to capture')
        if len(paths)>200:raise ValueError('Capture at most 200 videos in one batch')
        request.update(files=list(map(str,paths)),whole_video=s.capture_whole_video,start=s.video_start,duration=s.motion_duration,capture_python=bpy.path.abspath(p.capture_python))
        request['capture']=dict(models=str(Path(bpy.path.abspath(p.models_directory))/'gemx'),camera_mode=p.capture_camera,ffmpeg=bpy.path.abspath(p.video_ffmpeg),ffprobe=bpy.path.abspath(p.video_ffprobe),prompt=s.motion_prompt,seed=p.motion_seed,comfy_url=p.comfy_url,model=p.comfy_model,clip=p.comfy_clip,vae=p.comfy_vae,audio_vae=p.comfy_audio_vae,reference=bpy.path.abspath(s.video_reference) if s.video_reference else '',workflow=bpy.path.abspath(p.comfy_workflow) if p.comfy_workflow else '',bindings=json.loads(p.comfy_bindings),output_node=p.comfy_output_node,shot_rules=p.comfy_shot_rules,cycle_method=s.video_cycle if system=='VIDEO' else 'FULL')
        if system=='COMFY' and s.source_loop and not s.video_reference:raise ValueError('A generated video loop needs a reference image')
    motion_store.atomic(folder/'request.json',request);s.source_job=str(folder)
    image_pose.launch(folder,[bpy.app.binary_path,'--factory-startup','--background','--disable-autoexec','--python',str(Path(__file__).with_name('motion_source_worker.py')),'--',str(folder)],'Creating reusable motion')
    if not bpy.app.background:bpy.ops.local_character.run_source_motion_job()
    return {'FINISHED'}


def cancel_external(folder):
    path=Path(folder)/'active.json'
    if path.is_file():
        active=Path(json.loads(path.read_text())['folder']).resolve()
        if active.is_relative_to(Path(folder).resolve()):video_motion.cancel_external(active)


def refresh(context,selected=()):
    motion_library.refresh(context)
    if selected:
        chosen=set(selected)
        for item in context.window_manager.lc_motion_library.entries:item.source_selected=item.key in chosen


def chosen(context):
    state=context.window_manager.lc_motion_library
    if not state.entries:refresh(context)
    selected=motion_assets.selected_keys(context,motion_library.root(context)) or [item.key for item in state.entries if item.source_selected]
    if not selected and state.entries and 0<=state.index<len(state.entries):
        item=state.entries[state.index]
        if state.query.casefold() in (item.name+' '+item.family+' '+item.source).casefold():selected=[item.key]
    return [entry for entry in motion_store.catalog(motion_library.root(context))['clips'] if entry['id'] in selected]


class LC_UL_source_motions(UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_property,index):
        row=layout.row(align=True);row.prop(item,'source_selected',text='');row.label(text=item.family+' · '+item.name,icon='ACTION');row.label(text=f'{item.duration:.1f}s')
    def filter_items(self,context,data,propname):
        items=getattr(data,propname);query=context.window_manager.lc_motion_library.query.casefold()
        return [self.bitflag_filter_item if query in (item.name+' '+item.family+' '+item.source).casefold() else 0 for item in items],[]


class LC_OT_create_source(Operator):
    bl_idname='local_character.create_motion_source';bl_label='Create Reusable Motion'
    def execute(self,context):
        try:return start(context)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_OT_batch_videos(Operator,ImportHelper):
    bl_idname='local_character.capture_video_batch';bl_label='Capture Videos to Motion Library'
    bl_description='Choose multiple videos and capture them using the current loop and capture settings'
    filename_ext='';filter_glob:StringProperty(default='*.mp4;*.mov;*.mkv;*.webm;*.avi;*.m4v',options={'HIDDEN'})
    files:CollectionProperty(type=OperatorFileListElement);directory:StringProperty(subtype='DIR_PATH')
    def execute(self,context):
        try:
            context.scene.lc_settings.motion_system='VIDEO';context.scene.lc_settings.video_input='FILES'
            files=[Path(self.directory)/entry.name for entry in self.files] if self.files else [Path(self.filepath)]
            return start(context,files)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_OT_finish_source(Operator):
    bl_idname='local_character.finish_motion_source';bl_label='Finish Source Motions'
    def execute(self,context):
        try:
            s=context.scene.lc_settings;result=json.loads((Path(s.source_job)/'results.json').read_text());refresh(context,result['added'])
            s.motion_status=f"Saved {len(result['added'])} reusable motion(s)"+(f" · {len(result['errors'])} failed; inspect the job log" if result['errors'] else '')
            self.report({'INFO'},s.motion_status)
        except (ValueError,OSError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_assets_to_sources(Operator):
    bl_idname='local_character.use_motion_assets';bl_label='Use for Retargeting'
    def execute(self,context):
        keys=motion_assets.selected_keys(context,motion_library.root(context))
        if not keys:return {'CANCELLED'}
        refresh(context,keys);s=context.scene.lc_settings;s.ui_step='MOTION';s.animation_view='EDIT'
        s.motion_status=f'{len(keys)} source motion(s) selected · choose targets in the Rigmodo sidebar'
        return {'FINISHED'}


class LC_OT_source_tab(Operator):
    bl_idname='local_character.motion_system_tab';bl_label='Choose Motion System';bl_options={'INTERNAL'}
    system:StringProperty()
    def execute(self,context):context.scene.lc_settings.motion_system=self.system;return {'FINISHED'}


class LC_OT_pose_rig(Operator):
    bl_idname='local_character.create_pose_source';bl_label='Create Pose Rig';bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        if context.mode!='OBJECT' or busy():return {'CANCELLED'}
        from . import skeleton
        rig=skeleton.create_armature(context);rig.name='Rigmodo Pose Rig';rig['lc_pose_source']=True;context.scene.lc_settings.pose_source_rig=rig
        return {'FINISHED'}


class LC_OT_use_pose_rig(Operator):
    bl_idname='local_character.use_pose_source';bl_label='Use Selected Rig'
    def execute(self,context):
        rig=context.active_object
        if not rig or rig.type!='ARMATURE':self.report({'ERROR'},'Select the source pose rig');return {'CANCELLED'}
        context.scene.lc_settings.pose_source_rig=rig;return {'FINISHED'}


class LC_OT_edit_source(Operator):
    bl_idname='local_character.edit_source_poses';bl_label='Edit Source Poses';bl_options={'UNDO'}
    def execute(self,context):
        rig=context.scene.lc_settings.pose_source_rig
        if not rig or busy():return {'CANCELLED'}
        if context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in context.selected_objects:obj.select_set(False)
        rig.select_set(True);context.view_layer.objects.active=rig;bpy.ops.object.mode_set(mode='POSE');return {'FINISHED'}


class LC_OT_source_selection(Operator):
    bl_idname='local_character.select_source_motions';bl_label='Select Source Motions'
    mode:EnumProperty(items=[('ALL','All',''),('NONE','None','')])
    def execute(self,context):
        state=context.window_manager.lc_motion_library;query=state.query.casefold()
        for item in state.entries:
            item.source_selected=self.mode=='ALL' and query in (item.name+' '+item.family+' '+item.source).casefold()
        return {'FINISHED'}


def targets(context):
    s=context.scene.lc_settings
    if s.retarget_selected_characters:
        rigs={o for o in context.selected_objects if o.type=='ARMATURE'}
        rigs.update(o.find_armature() for o in context.selected_objects if o.type=='MESH' and o.find_armature())
    else:
        obj=s.character;rigs={obj if obj and obj.type=='ARMATURE' else obj.find_armature() if obj else None};rigs.discard(None)
    rigs={rig for rig in rigs if not rig.get('lc_source_preview') and rig.name in context.view_layer.objects and rig.library is None}
    if not rigs:raise ValueError('Choose a target character, or select character armatures')
    return sorted(rigs,key=lambda rig:rig.name)


class LC_OT_retarget_sources(Operator):
    bl_idname='local_character.retarget_sources';bl_label='Retarget Selected Motions';bl_options={'REGISTER','UNDO'}
    def invoke(self,context,event):
        result=self.prepare(context)
        if result!={'FINISHED'}:return result
        self._timer=context.window_manager.event_timer_add(.1,window=context.window);context.window_manager.modal_handler_add(self);return {'RUNNING_MODAL'}
    def prepare(self,context):
        global _retarget
        try:
            if busy():raise ValueError('Wait for the current motion task to finish')
            if context.mode!='OBJECT':raise ValueError('Finish pose editing before retargeting')
            stop_preview(context);entries=chosen(context);rigs=targets(context)
            if not entries:raise ValueError('Choose source motions from the library')
            options=context.scene.lc_settings;controls=context.window_manager.lc_motion_library
            adjustments=dict(speed=controls.speed,mirror=controls.mirror,spacing=controls.spacing)
            if len(entries)==1:adjustments.update(start=controls.trim_start,end=min(controls.trim_end,entries[0]['duration']))
            _retarget=dict(scene=context.scene,tasks=[(rig,entry) for rig in rigs for entry in entries],index=0,errors=[],made=[],options=dict(in_place=options.retarget_in_place,contacts=options.motion_contacts,ground=options.ground_height,loop=options.retarget_loop),root=motion_library.root(context),controls=adjustments)
            self._token=None
            if not bpy.app.background:
                from . import processing_visuals
                self._token=processing_visuals.start(context,'SETUP')
            return {'FINISHED'}
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
    def step(self,context):
        state=_retarget;rig,entry=state['tasks'][state['index']];s=state['scene'].lc_settings
        try:label=rig.name
        except ReferenceError:label='Removed character'
        try:
            if context.scene!=state['scene']:raise ValueError('Return to the retargeting scene')
            data=motion_store.read(state['root'],entry['id']);previous={key:getattr(s,key) for key in ('motion_in_place','motion_contacts','ground_height','create_loop')}
            try:
                s.motion_in_place=state['options']['in_place'];s.motion_contacts=state['options']['contacts'];s.ground_height=state['options']['ground'];s.create_loop=entry['loop'] if state['options']['loop']=='SOURCE' else state['options']['loop']=='LOOP'
                action=animation_transfer.finish(context,rig,data,entry['name'],dict(lc_library_source=entry['source'],lc_library_license=entry['license'],lc_library_id=entry['id']),state['controls'])
                state['made'].append(action.name)
            finally:
                for key,value in previous.items():setattr(s,key,value)
        except (ValueError,OSError,RuntimeError,KeyError,ReferenceError) as exc:state['errors'].append(dict(character=label,motion=entry['name'],error=str(exc)))
        state['index']+=1;s.motion_status=f"Retargeted {state['index']}/{len(state['tasks'])}"
        return state['index']>=len(state['tasks'])
    def finish(self,context,cancelled=False):
        global _retarget
        state=_retarget;_retarget=None
        if getattr(self,'_timer',None):context.window_manager.event_timer_remove(self._timer)
        from . import processing_visuals
        if self._token:processing_visuals.finish(self._token,'CANCELLED' if cancelled else 'FINISHED')
        state['scene'].lc_settings.motion_status=f"{'Stopped · ' if cancelled else ''}{len(state['made'])} animation(s) retargeted"+(f" · {len(state['errors'])} failed" if state['errors'] else '')
        state['scene'].lc_settings.retarget_report=json.dumps(state['errors'])
    def modal(self,context,event):
        from . import processing_visuals
        if event.type=='ESC' or context.scene!=_retarget['scene'] or processing_visuals.cancelled(self._token):
            made=bool(_retarget['made']);self.finish(context,True);return {'FINISHED'} if made else {'CANCELLED'}
        if event.type=='TIMER' and self.step(context):self.finish(context);return {'FINISHED'}
        return {'PASS_THROUGH'}
    def execute(self,context):
        result=self.prepare(context)
        if result!={'FINISHED'}:return result
        while not self.step(context):pass
        self.finish(context);return {'FINISHED'}
    def cancel(self,context):
        if _retarget:self.finish(context,True)


def stop_preview(context):
    global _preview
    if not _preview:return
    state=_preview;_preview=None
    motion_playback.stop(context)
    try:
        rig=state.get('rig');action=state.get('action')
        if rig:
            if context.active_object==rig and context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
            armature=rig.data;bpy.data.objects.remove(rig,do_unlink=True)
            if armature.users==0:bpy.data.armatures.remove(armature)
        if action and action.users-int(action.use_fake_user)==0:bpy.data.actions.remove(action)
        scene=state['scene'];scene.lc_settings.loop_action=state['loop']
        scene.use_preview_range,scene.frame_preview_start,scene.frame_preview_end=state['range'];scene.frame_set(state['frame'])
        if context.scene==scene and context.mode=='OBJECT':
            for obj in context.selected_objects:obj.select_set(False)
            for obj in state['selected']:
                if obj.name in context.view_layer.objects:obj.select_set(True)
            if state['active'] and state['active'].name in context.view_layer.objects:context.view_layer.objects.active=state['active']
    except ReferenceError:pass


class LC_OT_preview_source(Operator):
    bl_idname='local_character.preview_source_motion';bl_label='Preview Source Motion'
    def execute(self,context):
        global _preview
        try:
            if context.mode!='OBJECT' or busy():raise ValueError('Finish the current edit or task first')
            stop_preview(context);entries=chosen(context)
            if not entries:raise ValueError('Choose a source motion')
            data=motion_store.read(motion_library.root(context),entries[0]['id']);state=dict(scene=context.scene,loop=context.scene.lc_settings.loop_action,selected=list(context.selected_objects),active=context.view_layer.objects.active,frame=context.scene.frame_current,range=(context.scene.use_preview_range,context.scene.frame_preview_start,context.scene.frame_preview_end))
            _preview=state
            rig=motion_assets.source_rig(context,data,'Motion Preview');state['rig']=rig;rig['lc_source_preview']=True;rig.show_in_front=True;rig.data.display_type='STICK'
            action=motion_retarget(context,rig,data,entries[0]);state['action']=action
            if not bpy.app.background:
                from . import animation
                motion_playback.preview(context,rig,animation.selected_action(rig,context.scene))
        except (ValueError,OSError,RuntimeError,KeyError) as exc:stop_preview(context);self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


def motion_retarget(context,rig,data,entry):
    from .motion_retarget import apply
    normalized=dict(data,rest=np.asarray([rig.data.bones[str(n)].matrix_local for n in data['names']],dtype=np.float32))
    return apply(context,rig,normalized,entry['name']+' · Source Preview',loop=entry['loop'])


class LC_OT_stop_source(Operator):
    bl_idname='local_character.stop_source_preview';bl_label='Stop Source Preview'
    def execute(self,context):stop_preview(context);return {'FINISHED'}


def initial_refresh():
    try:refresh(bpy.context)
    except (OSError,ValueError):pass


def cleanup():
    if bpy.app.timers.is_registered(initial_refresh):bpy.app.timers.unregister(initial_refresh)
    stop_preview(bpy.context)


CLASSES=(LC_UL_source_motions,LC_OT_create_source,LC_OT_batch_videos,LC_OT_finish_source,LC_OT_assets_to_sources,LC_OT_source_tab,LC_OT_pose_rig,LC_OT_use_pose_rig,LC_OT_edit_source,LC_OT_source_selection,LC_OT_retarget_sources,LC_OT_preview_source,LC_OT_stop_source)
