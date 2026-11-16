# SPDX-License-Identifier: GPL-3.0-or-later
"""Optional pose-guided resynthesis; apply a new clip, then solve contacts."""
import json,tempfile
from pathlib import Path
import bpy,numpy as np
from bpy.types import Operator
from bpy.props import FloatProperty
from . import configuration,motion_jobs,motion_store,motion_sources,motionbricks,motion_playback,image_pose,skinning,animation_transfer,motion_contacts


def start(context,strength=.35,spacing=.5):
    if motion_sources.busy():raise ValueError('Finish the current local task first')
    rig=motion_jobs.selected_rig(context);motion_jobs.validate_rig(context,rig);motion_playback.stop(context)
    ad=rig.animation_data
    if not ad or not ad.action or not ad.action_slot:raise ValueError('Select an animation to refine')
    if ad.drivers or any(not t.mute and t.strips for t in ad.nla_tracks):raise ValueError('Bake drivers and mute NLA tracks before refining this Action')
    p=configuration.settings(context);provider=bpy.path.abspath(p.motionbricks_provider)
    if not motionbricks.ready(provider):raise ValueError('Install MotionBricks in Extension Settings → Setup')
    if not 0<strength<=1 or not .5<=spacing<=2:raise ValueError('Use strength 0–1 and guide spacing 0.5–2 seconds')
    data=motion_store.capture(context,rig,ad.action,ad.action_slot);frames=round(float(data['times'][-1])*30)+1
    if not 16<=frames<=900:raise ValueError('Refine clips from 0.5 to just under 30 seconds')
    # Preserve the source stance even when resynthesis introduces foot movement.
    report=json.loads(ad.action.get('lc_contact_report','{}'))
    if 'flat_intervals' not in report:_,report=motion_contacts.solve(context,rig,data,context.scene.lc_settings.ground_height,bool(ad.action.get('lc_in_place')))
    contacts=[dict(e,mode='PLANT') for e in report['flat_intervals']]+motion_contacts.contact_overrides(ad.action,float(data['times'][-1]))
    directory=Path(bpy.path.abspath(p.video_jobs));directory.mkdir(parents=True,exist_ok=True);folder=Path(tempfile.mkdtemp(prefix='refine-motion-',dir=directory))
    request=dict(rig=rig.name,rig_pointer=str(rig.as_pointer()),scene_pointer=str(context.scene.as_pointer()),action_pointer=str(ad.action.as_pointer()),name=ad.action.name,
        signature=skinning._digest(rig,motion_jobs.character_meshes(context,rig)),provider=provider,strength=strength,spacing=spacing,seed=p.motion_seed,
        contacts=contacts,unit_scale=context.scene.unit_settings.scale_length,frames=frames,loop=bool(ad.action.lc_clip_loop),in_place=bool(ad.action.get('lc_in_place')),ground=context.scene.lc_settings.ground_height,overrides=ad.action.get('lc_contact_overrides','[]'))
    motion_sources.snapshot(rig,folder,request);np.savez_compressed(folder/'original.npz',**data);request['input_sha256']=motion_jobs.sha(folder/'original.npz')
    motion_store.atomic(folder/'request.json',request);context.scene.lc_settings.refine_motion_job=str(folder)
    image_pose.launch(folder,[bpy.app.binary_path,'--factory-startup','--background','--disable-autoexec','--python',str(Path(__file__).with_name('motion_refine_worker.py')),'--',str(folder)],'MotionBricks · Refining transitions')
    if not bpy.app.background:bpy.ops.local_character.run_motion_refine_job()
    return folder


def finish(context,folder):
    folder=Path(folder)
    if json.loads((folder/'status.json').read_text()).get('status')!='complete':raise ValueError('Wait for refinement to finish')
    request=json.loads((folder/'request.json').read_text());rig=bpy.data.objects.get(request['rig']);action=rig.animation_data.action if rig and rig.animation_data else None
    if str(context.scene.as_pointer())!=request['scene_pointer'] or not rig or str(rig.as_pointer())!=request['rig_pointer'] or not action or str(action.as_pointer())!=request['action_pointer']:
        raise ValueError('Return to the original character and Action; refined data remains in the job folder')
    if motion_jobs.sha(folder/'original.npz')!=request['input_sha256'] or skinning._digest(rig,motion_jobs.character_meshes(context,rig))!=request['signature'] or action.get('lc_contact_overrides','[]')!=request['overrides']:
        raise ValueError('Source character or contact edits changed during refinement; the original is preserved')
    original=motion_store.read_file(folder/'original.npz');current=motion_store.capture(context,rig,action,rig.animation_data.action_slot)
    if current['poses'].shape!=original['poses'].shape or not np.allclose(current['poses'],original['poses'],atol=2e-5,rtol=1e-6) or not np.allclose(current['times'],original['times'],atol=1e-5):
        raise ValueError('Source animation changed during refinement; refined data remains in the job folder')
    data=motion_store.read_file(folder/'output.npz')
    provenance=json.loads(str(data.get('provenance',np.asarray(['{}']))[0]));provenance['lc_contact_overrides']=json.dumps(request['contacts']);data['provenance']=np.asarray([json.dumps(provenance)])
    s=context.scene.lc_settings;old={key:getattr(s,key) for key in ('create_loop','motion_in_place','motion_contacts','ground_height')}
    try:
        s.create_loop=request['loop'];s.motion_in_place=request['in_place'];s.motion_contacts=True;s.ground_height=request['ground']
        result=animation_transfer.finish(context,rig,data,request['name']+' · MotionBricks',dict(lc_refinement_provider='MotionBricks',lc_refinement_strength=request['strength'],lc_refinement_source=action.name))
    finally:
        for key,value in old.items():setattr(s,key,value)
    result['lc_refinement_job']=str(folder);s.motion_status='MotionBricks refinement ready · original clip retained'
    return result


class LC_OT_refine_motion(Operator):
    bl_idname='local_character.refine_motion';bl_label='Refine with MotionBricks';bl_description='Regenerate body transitions between sparse guide poses on a new clip; preserve fingers, then solve foot contacts. This is learned motion, not a physics simulation'
    strength:FloatProperty(name='Strength',default=.35,min=.05,max=1.,subtype='FACTOR')
    spacing:FloatProperty(name='Guide spacing (seconds)',default=.5,min=.5,max=2.)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self)
    def execute(self,context):
        try:start(context,self.strength,self.spacing)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class LC_OT_finish_refine_motion(Operator):
    bl_idname='local_character.finish_motion_refine';bl_label='Apply MotionBricks Refinement';bl_options={'UNDO','INTERNAL'}
    def execute(self,context):
        try:finish(context,context.scene.lc_settings.refine_motion_job)
        except (ValueError,OSError,RuntimeError,KeyError) as exc:context.scene.lc_settings.motion_status=str(exc);self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


CLASSES=(LC_OT_refine_motion,LC_OT_finish_refine_motion)
