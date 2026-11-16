# SPDX-License-Identifier: GPL-3.0-or-later
"""Local motion browser; previews and applications only create Actions on the target rig."""
import json,os,tempfile
from pathlib import Path
import bpy
import bpy.utils.previews
from bpy.props import StringProperty,FloatProperty,IntProperty,BoolProperty,PointerProperty,CollectionProperty
from bpy.types import Operator,PropertyGroup,Panel,OperatorFileListElement
from bpy_extras.io_utils import ImportHelper
from . import configuration,motion_store,motion_retarget,motion_jobs,motion_clips,motion_playback,image_pose,skinning,motion_assets

_icons=None
_preview=None


def root(context):return Path(bpy.path.abspath(configuration.settings(context).motion_library_directory)).resolve()


def chosen(context):
    state=context.window_manager.lc_motion_library
    key=motion_assets.selected_key(context,root(context))
    if key and (not state.entries or state.entries[state.index].key!=key):refresh(context,key)
    if not state.entries or not 0<=state.index<len(state.entries):raise ValueError('Choose a motion from the library')
    key=state.entries[state.index].key
    entry=next((c for c in motion_store.catalog(root(context))['clips'] if c['id']==key),None)
    if entry is None:raise ValueError('The library changed; refresh it')
    return state,entry


def controls_changed(self,context):
    if not self.entries or not 0<=self.index<len(self.entries):return
    item=self.entries[self.index];self.trim_start=0.;self.trim_end=item.duration;self.speed=1.;self.mirror=False;self.in_place=False;self.spacing=0.;self.loop=item.loop


def refresh(context,key=None):
    state=context.window_manager.lc_motion_library
    if key is None and state.entries and 0<=state.index<len(state.entries):key=state.entries[state.index].key
    state.entries.clear()
    for record in sorted(motion_store.catalog(root(context))['clips'],key=lambda c:(c['family'].casefold(),c['name'].casefold())):
        item=state.entries.add();item.key=record['id'];item.name=record['name'];item.family=record['family'];item.source=record['source']
        item.duration=record['duration'];item.loop=record['loop'];item.favorite=record.get('favorite',False);item.tags=record.get('tags','')
    state.index=next((i for i,item in enumerate(state.entries) if item.key==key),0);controls_changed(state,context)


def icon(context,key):
    global _icons
    if _icons is None:_icons=bpy.utils.previews.new()
    filename=motion_store.clip_dir(root(context),key)/'preview.png';cache=str(filename)
    if not filename.is_file():return 0
    if cache not in _icons:_icons.load(cache,cache,'IMAGE')
    return _icons[cache].icon_id


def restore_preview(context):
    global _preview
    if not _preview:return
    state=_preview;_preview=None
    try:
        rig=state['rig'];action=state['action']
        if rig.animation_data and rig.animation_data.action==action:
            motion_playback.stop(context)
            old=state['old'];ad=rig.animation_data
            if old:ad.action,ad.action_slot,ad.use_nla,ad.action_blend_type,ad.action_influence=old
            else:rig.animation_data_clear()
            for p,m in zip(rig.pose.bones,state['pose']):p.rotation_mode=state['modes'][p.name];p.matrix_basis=m
            scene=state['scene'];scene.use_preview_range,scene.frame_preview_start,scene.frame_preview_end=state['range']
            scene.lc_settings.loop_action=state['loop'];scene.frame_set(state['frame'],subframe=state['subframe']);context.view_layer.update()
        if action.users-int(action.use_fake_user)==0:bpy.data.actions.remove(action)
    except ReferenceError:pass


def build(context,preview=False):
    global _preview
    if skinning._jobs:raise ValueError('Wait for the current task to finish')
    restore_preview(context);state,entry=chosen(context)
    if not state.target:state.target=motion_jobs.selected_rig(context)
    rig=state.target
    if not rig or rig.type!='ARMATURE' or rig.name not in context.scene.objects:raise ValueError('Select the target armature before opening the library')
    motion_playback.stop(context)
    ad=rig.animation_data;old=(ad.action,ad.action_slot,ad.use_nla,ad.action_blend_type,ad.action_influence) if ad else None
    backup=dict(rig=rig,old=old,scene=context.scene,modes={p.name:p.rotation_mode for p in rig.pose.bones},pose=[p.matrix_basis.copy() for p in rig.pose.bones],frame=context.scene.frame_current,subframe=context.scene.frame_subframe,
                range=(context.scene.use_preview_range,context.scene.frame_preview_start,context.scene.frame_preview_end),loop=context.scene.lc_settings.loop_action)
    data=motion_store.read(root(context),entry['id'])
    action=motion_retarget.apply(context,rig,data,entry['name']+(' · Preview' if preview else ''),state.trim_start,state.trim_end,state.speed,state.mirror,state.in_place,state.spacing,state.loop)
    action['lc_library_source']=entry['source'];action['lc_library_license']=entry['license'];action['lc_library_id']=entry['id']
    motion_clips.select(context,rig,action,action.slots[0])
    if preview:
        backup['action']=action;_preview=backup
        from .animation import selected_action
        motion_playback.preview(context,rig,selected_action(rig,context.scene))
    return action


def start_job(context,kind,files=(),mixamo=False):
    if skinning._jobs:raise ValueError('Wait for the current task to finish')
    folder=Path(tempfile.mkdtemp(prefix='rigmodo-library-'));library=root(context);library.mkdir(parents=True,exist_ok=True)
    motion_store.atomic(folder/'request.json',dict(kind=kind,root=str(library),files=list(map(str,files)),source='Mixamo (user download)' if mixamo else 'Local import',license='Adobe Mixamo user license' if mixamo else 'User-provided'))
    context.scene.lc_settings.library_job=str(folder)
    image_pose.launch(folder,[bpy.app.binary_path,'--factory-startup','--background','--disable-autoexec','--python',str(Path(__file__).with_name('motion_library_worker.py')),'--',str(folder)],'Importing local motion library')
    if not bpy.app.background:bpy.ops.local_character.run_library_job()
    return {'FINISHED'}


class LC_LibraryItem(PropertyGroup):
    key:StringProperty();name:StringProperty();family:StringProperty();source:StringProperty();tags:StringProperty()
    duration:FloatProperty();loop:BoolProperty();favorite:BoolProperty()


class LC_LibraryState(PropertyGroup):
    entries:CollectionProperty(type=LC_LibraryItem)
    index:IntProperty(default=0,update=controls_changed)
    query:StringProperty(name='Search',options={'TEXTEDIT_UPDATE'})
    favorites:BoolProperty(name='Favorites only')
    target:PointerProperty(type=bpy.types.Object,poll=lambda self,obj:obj.type=='ARMATURE')
    speed:FloatProperty(name='Speed',default=1.,min=.1,max=4.,precision=2)
    trim_start:FloatProperty(name='Start (s)',default=0,min=0,precision=2)
    trim_end:FloatProperty(name='End (s)',default=1,min=.001,precision=2)
    mirror:BoolProperty(name='Mirror')
    in_place:BoolProperty(name='In place',description='Remove net horizontal travel while retaining body sway and vertical motion')
    loop:BoolProperty(name='Loop')
    spacing:FloatProperty(name='Arm spacing (°)',default=0,min=-10,max=45)


class LC_OT_open_motion_assets(Operator):
    bl_idname='local_character.open_motion_assets';bl_label='Motion Library'
    def execute(self,context):
        try:
            state=context.window_manager.lc_motion_library
            try:state.target=motion_jobs.selected_rig(context)
            except ValueError:pass
            refresh(context);folder=root(context)/'Assets';folder.mkdir(parents=True,exist_ok=True)
            libraries=context.preferences.filepaths.asset_libraries
            library=next((l for l in libraries if Path(bpy.path.abspath(l.path)).resolve()==folder),None)
            if library is None:library=libraries.new(name='Rigmodo Motions',directory=str(folder))
            library.import_method='APPEND'
            if context.preferences.use_preferences_save:bpy.ops.wm.save_userpref()
            area=next((a for a in context.screen.areas if a.type=='FILE_BROWSER' and a.ui_type=='ASSETS'),None)
            if area is None:
                before=set(context.screen.areas)
                bpy.ops.screen.area_split(direction='HORIZONTAL',factor=.65)
                area=next(a for a in context.screen.areas if a not in before)
            area.type='FILE_BROWSER';area.ui_type='ASSETS';area.spaces.active.show_region_tool_props=True
            def configure():
                try:
                    space=area.spaces.active
                    if space.type!='FILE_BROWSER':return None
                    if space.params is None:return .1
                    space.params.asset_library_reference=library.name
                    space.params.import_method='APPEND';area.tag_redraw()
                except ReferenceError:pass
                return None
            bpy.app.timers.register(configure,first_interval=.1)
            if any(not (folder/(e['id']+'.blend')).is_file() for e in motion_store.catalog(root(context))['clips']):
                if not skinning._jobs:start_job(context,'publish')
            return {'FINISHED'}
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_PT_motion_assets(Panel):
    bl_space_type='FILE_BROWSER';bl_region_type='TOOL_PROPS';bl_label='Rigmodo';bl_order=-100
    @classmethod
    def poll(cls,context):return context.space_data.type=='FILE_BROWSER' and context.space_data.browse_mode=='ASSETS'
    def draw(self,context):
        layout=self.layout;state=context.window_manager.lc_motion_library
        layout.prop(state,'target',text='Character')
        key=motion_assets.selected_key(context,root(context))
        if key:
            row=layout.row();row.enabled=bool(state.target) and not skinning._jobs
            row.operator('local_character.motion_library',text='Apply / Adjust',icon='ACTION')
            row=layout.row(align=True);row.enabled=bool(state.target) and not skinning._jobs
            row.operator('local_character.preview_library_motion',text='Preview',icon='PLAY')
            row.operator('local_character.stop_library_preview',text='',icon='SNAP_FACE_CENTER')
            layout.label(text='Use Apply / Adjust for the full clip.',icon='INFO')
        else:layout.label(text='Select a Rigmodo motion asset.',icon='INFO')
        column=layout.column(align=True);column.enabled=not skinning._jobs
        column.operator('local_character.import_library_motions',text='Import Files',icon='IMPORT')
        column.operator('local_character.import_motion_folder',text='Import Folder',icon='FILE_FOLDER')
        column.operator('local_character.save_library_motion',text='Save Current Animation',icon='ADD')
        column.operator('local_character.install_motion_starter',text='Get CC0 Motions',icon='URL')
        column.operator('local_character.open_mixamo_downloader',text='Mixamo Downloader',icon='URL')


class LC_OT_stop_library_preview(Operator):
    bl_idname='local_character.stop_library_preview';bl_label='Restore Previous Animation'
    def execute(self,context):restore_preview(context);return {'FINISHED'}


class LC_OT_library_refresh(Operator):
    bl_idname='local_character.refresh_motion_library';bl_label='Refresh Library'
    def execute(self,context):
        try:refresh(context)
        except (ValueError,OSError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_library(Operator):
    bl_idname='local_character.motion_library';bl_label='Motion Library';bl_options={'REGISTER','UNDO'}
    def invoke(self,context,event):
        state=context.window_manager.lc_motion_library
        try:
            if not state.target or context.area.type!='FILE_BROWSER':state.target=motion_jobs.selected_rig(context)
            chosen(context)
        except (ValueError,OSError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self,width=430,confirm_text='Apply Motion')
    def draw(self,context):
        layout=self.layout;state=context.window_manager.lc_motion_library
        try:
            _,entry=chosen(context)
            row=layout.row(align=True);row.label(text=entry['name'])
            op=row.operator('local_character.favorite_library_motion',text='',icon='SOLO_ON' if entry.get('favorite') else 'SOLO_OFF');op.key=entry['id']
            layout.template_icon(icon_value=icon(context,entry['id']),scale=8)
            layout.label(text=f"{entry['family']} · {entry['duration']:.2f} s · {entry['bones']} bones")
            layout.prop(state,'speed');row=layout.row(align=True);row.prop(state,'trim_start');row.prop(state,'trim_end')
            row=layout.row(align=True);row.prop(state,'mirror');row.prop(state,'in_place');row.prop(state,'loop')
            if entry['family'].casefold()=='human':layout.prop(state,'spacing')
            row=layout.row();row.enabled=bool(state.target) and not skinning._jobs
            row.operator('local_character.preview_library_motion',text='Preview on Character',icon='PLAY')
            layout.label(text=entry['source']);layout.label(text=entry['license'])
        except ValueError:layout.label(text='Select a Rigmodo motion in the Asset Browser.',icon='INFO')
    def execute(self,context):
        try:action=build(context)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'Applied '+action.name);return {'FINISHED'}
    def cancel(self,context):restore_preview(context)


class LC_OT_library_preview(Operator):
    bl_idname='local_character.preview_library_motion';bl_label='Preview Library Motion'
    def execute(self,context):
        try:build(context,True)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_library_favorite(Operator):
    bl_idname='local_character.favorite_library_motion';bl_label='Toggle Favorite'
    key:StringProperty()
    def execute(self,context):
        try:
            with motion_store.locked(root(context)):
                catalog=motion_store.catalog(root(context));entry=next(c for c in catalog['clips'] if c['id']==self.key);entry['favorite']=not entry.get('favorite',False)
                motion_store.atomic(root(context)/'catalog.json',catalog)
            for item in context.window_manager.lc_motion_library.entries:
                if item.key==self.key:item.favorite=entry['favorite']
        except (ValueError,OSError,StopIteration) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_library_save(Operator):
    bl_idname='local_character.save_library_motion';bl_label='Save Animation to Library'
    name:StringProperty(name='Name');tags:StringProperty(name='Tags',description='Search keywords separated by spaces or commas')
    @classmethod
    def poll(cls,context):return motion_clips.editable(context) and bool(motion_jobs.selected_rig(context).animation_data and motion_jobs.selected_rig(context).animation_data.action)
    def invoke(self,context,event):
        self.name=motion_jobs.selected_rig(context).animation_data.action.name
        return context.window_manager.invoke_props_dialog(self,width=380)
    def draw(self,context):self.layout.prop(self,'name');self.layout.prop(self,'tags')
    def execute(self,context):
        try:
            if skinning._jobs:raise ValueError('Wait for the current task to finish')
            if not self.name.strip():raise ValueError('Enter a motion name')
            rig=motion_jobs.selected_rig(context);ad=rig.animation_data
            motion_playback.stop(context);data=motion_store.capture(context,rig,ad.action,ad.action_slot)
            meta=ad.action.asset_data
            source=ad.action.get('lc_library_source',meta.author if meta else 'Own animation');license=ad.action.get('lc_library_license',meta.license if meta else 'User-provided')
            key,created=motion_store.write(root(context),data,self.name,source,license,loop=motion_playback.looping(ad.action),tags=self.tags)
            refresh(context,key)
            start_job(context,'publish')
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},'Saved motion to library' if created else 'This motion is already in the library');return {'FINISHED'}


class LC_OT_library_import(Operator,ImportHelper):
    bl_idname='local_character.import_library_motions';bl_label='Batch Import Motions'
    filename_ext='';filter_glob:StringProperty(default='*.fbx;*.glb;*.gltf;*.blend',options={'HIDDEN'})
    files:CollectionProperty(type=OperatorFileListElement);directory:StringProperty(subtype='DIR_PATH')
    mixamo:BoolProperty(name='Mixamo downloads',default=False,description='Record Adobe Mixamo provenance for these files')
    def draw(self,context):self.layout.prop(self,'mixamo')
    def execute(self,context):
        try:
            files=[Path(self.directory)/f.name for f in self.files] if self.files else [Path(self.filepath)]
            restore_preview(context);return start_job(context,'import',files,self.mixamo)
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_OT_library_folder(Operator):
    bl_idname='local_character.import_motion_folder';bl_label='Import Motion Folder'
    directory:StringProperty(subtype='DIR_PATH');recursive:BoolProperty(name='Include subfolders',default=True)
    mixamo:BoolProperty(name='Mixamo downloads',default=False)
    def invoke(self,context,event):context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}
    def execute(self,context):
        try:
            directory=Path(self.directory);paths=directory.rglob('*') if self.recursive else directory.glob('*')
            files=[p for p in sorted(paths) if p.is_file() and p.suffix.lower() in {'.fbx','.glb','.gltf','.blend'}]
            if not files:raise ValueError('No motion files found in that folder')
            if len(files)>5000:raise ValueError('Choose a smaller folder (at most 5000 files per import)')
            restore_preview(context);return start_job(context,'import',files,self.mixamo)
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_OT_library_starter(Operator):
    bl_idname='local_character.install_motion_starter';bl_label='Download CC0 Starter Motions'
    def execute(self,context):
        try:restore_preview(context);return start_job(context,'starter')
        except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class LC_OT_library_finish(Operator):
    bl_idname='local_character.finish_library_job';bl_label='Refresh Imported Motions'
    def execute(self,context):
        try:
            folder=Path(context.scene.lc_settings.library_job);result=json.loads((folder/'results.json').read_text());refresh(context)
            for area in context.screen.areas if context.screen else []:
                if area.type=='FILE_BROWSER' and area.ui_type=='ASSETS':
                    with context.temp_override(area=area):bpy.ops.asset.library_refresh()
            context.scene.lc_settings.motion_status='Mixamo downloader installed. Click Mixamo Downloader to sign in.' if result.get('downloader_ready') else f"Library: {len(result['added'])} motions added, {len(result['errors'])} files failed."
        except (ValueError,OSError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_mixamo_downloader(Operator):
    bl_idname='local_character.open_mixamo_downloader';bl_label='Open Mixamo Batch Downloader'
    def execute(self,context):
        launcher=root(context)/'Tools'/'MixamoDownloader'/'Start.cmd'
        if not launcher.is_file():
            try:return start_job(context,'downloader')
            except (ValueError,OSError,RuntimeError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        import subprocess
        env=os.environ.copy();env.pop('ELECTRON_RUN_AS_NODE',None)
        subprocess.Popen(['cmd','/c',str(launcher)],cwd=launcher.parent,env=env,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        return {'FINISHED'}


CLASSES=(LC_LibraryItem,LC_LibraryState,LC_OT_open_motion_assets,LC_PT_motion_assets,LC_OT_stop_library_preview,LC_OT_library_refresh,LC_OT_library,LC_OT_library_preview,
         LC_OT_library_favorite,LC_OT_library_save,LC_OT_library_import,LC_OT_library_folder,LC_OT_library_starter,LC_OT_library_finish,LC_OT_mixamo_downloader)

def draw_asset_header(self,context):
    if context.space_data.browse_mode!='ASSETS' or not motion_assets.selected_key(context,root(context)):return
    row=self.layout.row(align=True);row.enabled=not skinning._jobs
    row.operator('local_character.motion_library',text='Apply Motion',icon='ACTION')
    row.operator('local_character.preview_library_motion',text='',icon='PLAY')
    row.operator('local_character.stop_library_preview',text='',icon='SNAP_FACE_CENTER')


def register():
    bpy.types.WindowManager.lc_motion_library=PointerProperty(type=LC_LibraryState,options={'SKIP_SAVE'})
    bpy.types.FILEBROWSER_HT_header.append(draw_asset_header)
def unregister():
    global _icons
    bpy.types.FILEBROWSER_HT_header.remove(draw_asset_header)
    restore_preview(bpy.context)
    if _icons is not None:bpy.utils.previews.remove(_icons);_icons=None
    del bpy.types.WindowManager.lc_motion_library
