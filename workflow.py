# SPDX-License-Identifier: GPL-3.0-or-later
"""Sequential local character workflow; each finished phase owns review copies."""
import json
from pathlib import Path
import tempfile
import uuid
import bpy
from . import placement, skinning, regional_jobs, motion_jobs, motion_apply, motion_finish, exporter, skeleton, regions,twists,deformation_qa,weight_copy,character_result

_runs={}


def select(context,rig,meshes):
    for obj in context.selected_objects:obj.select_set(False)
    for obj in [rig,*meshes]:
        obj.hide_set(False);obj.select_set(True)
    context.view_layer.objects.active=rig


class Run:
    def __init__(self,context,options):
        if skinning._jobs or _runs:raise ValueError('Finish or cancel the current local workflow first')
        self.scene=context.scene;self.options=dict(options);self.original_rig,self.original_meshes=placement.selected(context)
        self.rig,self.meshes=self.original_rig,list(self.original_meshes)
        self.stages=[];self.generated=[];self.stage=None;self.folder=None;self.finished=False
        self.halted=None
        self.id=uuid.uuid4().hex
        directory=skinning.provider_cache().parent.parent/'jobs';directory.mkdir(parents=True,exist_ok=True)
        self.record=Path(tempfile.mkdtemp(prefix='character-',dir=directory))
        if self.options.get('export'):
            destination=self.options['export_directory']
            if destination.startswith('//') and not bpy.data.filepath:raise ValueError('Choose an absolute export folder or save the blend file before automatic export')
            name=exporter.safe_name(self.options['character_name'])
            if (Path(bpy.path.abspath(destination)).resolve()/name).exists():raise ValueError('This export bundle already exists. Choose a new character name before starting')
        accepted=False;add_root=False
        if self.rig and self.options.get('reuse_joints',True):
            try:motion_jobs.validate_rig(context,self.rig);accepted=True
            except ValueError as validation_error:
                mapping={skeleton.canonical_name(b.name):b for b in self.rig.data.bones}
                # Root is structural. Its absence does not invalidate accepted
                # imported anatomical joints or authorize replacing them.
                if 'Root' not in mapping and mapping.get('Hips') and mapping['Hips'].parent is None and skeleton.REQUIRED<=mapping.keys():
                    skeleton.resolve_mapping(self.rig.data.bones)
                    scales=self.rig.matrix_world.to_scale()
                    accepted=not self.rig.parent and self.rig.matrix_world.determinant()>0 and max(scales)-min(scales)<1e-5 and not self.rig.constraints and not any(b.constraints for b in self.rig.pose.bones)
                    accepted=accepted and all(b.inherit_scale=='FULL' and b.use_inherit_rotation for b in self.rig.data.bones)
                    add_root=accepted
                if not accepted and skeleton.REQUIRED<=mapping.keys():
                    raise ValueError('Imported humanoid cannot be reused: '+str(validation_error)+'. Prepare an unconstrained working copy, or explicitly disable Reuse accepted joints for a fresh proposal') from validation_error
        if self.options.get('skin_only') and not accepted:raise ValueError('Generate or select an accepted humanoid rig first; geometric binding is available under Advanced skinning')
        if self.options.get('motion') and self.options.get('motion_use_keyframes'):
            from . import motion_keyframes
            if self.options.get('loop'):raise ValueError('Disable automatic loop finishing when using key poses; finish loops on a separate Action copy')
            if not accepted or add_root or self.options.get('twists'):raise ValueError('Generate/skin the final rig first, then add pose keyframes in Motion')
            motion_keyframes.prepare(context,self.rig,self.options['motion_frames'],self.options['motion_start_frame'],self.options['motion_in_place'])
        self.pending=(['root'] if add_root else []) if accepted else ['placement']
        self.pending+=['skin'] if self.options.get('rebind',True) or not accepted else []
        self.pending+=['refine']
        if self.options.get('twists'):
            if self.rig and self.rig.get('lc_twists'):raise ValueError('Build or refine the core before adding twists; use the motion operation directly on an existing twist rig')
            self.pending+=['twists']
        if self.options.get('motion',True):self.pending+=['motion']
        self._write('prepared')

    def _write(self,status,error=None):
        try:rig_name=self.rig.name if self.rig else None
        except ReferenceError:rig_name=None
        data=dict(schema_version=1,workflow_id=self.id,status=status,stage=self.stage,stages=self.stages,options=self.options,
                  final_rig=rig_name,error=error)
        (self.record/'workflow.json').write_text(json.dumps(data,indent=2,allow_nan=False))

    def launch(self,context):
        self._context(context)
        if not self.pending:return self.finish(context)
        self.stage=self.pending.pop(0);options=self.options
        if self.stage=='placement':
            self.folder=placement.prepare(context,self.meshes,self.rig,parent=self.record,provider=Path(options['placement_python']).parent.parent.parent)
            placement.start(self.folder,options['placement_python'])
        elif self.stage=='skin':
            self.folder=skinning.prepare(context,self.rig,self.meshes,parent=self.record,device=options['skin_device'],beams=options['skin_beams'])
            skinning.start(self.folder,options['skin_executable'],options['skin_models'])
        elif self.stage=='refine':
            self.folder=regional_jobs.prepare(context,self.rig,self.meshes,parent=self.record,method='RIGID_PARTS' if options.get('rigid_parts') else 'AUTO',
                iterations=options['refine_iterations'],strength=options['refine_strength'],join_seams=options['refine_seams'])
            regional_jobs.start(self.folder)
        elif self.stage=='motion':
            select(context,self.rig,self.meshes)
            self.folder=motion_jobs.prepare(context,self.rig,options['motion_prompt'],options['motion_frames'],
                options['motion_steps'],options['motion_seed'],options['motion_in_place'],parent=self.record,
                keyframes=options.get('motion_use_keyframes',False),start_frame=options.get('motion_start_frame',1))
            motion_jobs.start(self.folder,options['motion_provider'])
        elif self.stage=='twists':
            collection,self.rig,self.meshes=twists.add(context,self.rig,self.meshes)
            self.generated.append([self.rig,*self.meshes]);select(context,self.rig,self.meshes)
            self.stages.append(dict(stage='twists',collection=collection.name))
            return self.launch(context)
        elif self.stage=='root':
            self.folder=self.record/'root';self.folder.mkdir()
            (self.folder/'request.json').write_text(json.dumps(dict(source_digest=skinning._digest(self.rig,self.meshes))))
            skinning._state(self.folder,'complete')
        _runs[self.id]=self;self._write('running')
        return self.folder

    def _context(self,context):
        if context.scene!=self.scene or context.mode!='OBJECT':raise ValueError('Return to the original scene in Object Mode to continue this workflow')

    def apply_step(self,context):
        self._context(context)
        if skinning.poll(self.folder)['status']!='complete':raise ValueError('Current workflow phase is not complete')
        previous=[self.rig,*self.meshes] if self.rig else self.meshes[:]
        if self.stage=='root':
            if skinning._digest(self.rig,self.meshes)!=json.loads((self.folder/'request.json').read_text())['source_digest']:
                raise ValueError('Source changed before Root adaptation')
            collection,self.rig,self.meshes=weight_copy.clone(context,self.rig,self.meshes,label='Root')
            select(context,self.rig,self.meshes);exporter._add_root(context,self.rig);motion_jobs.validate_rig(context,self.rig)
        elif self.stage=='placement':collection,self.rig,self.meshes,_=placement.apply(context,self.folder)
        elif self.stage=='skin':collection,self.rig,self.meshes=skinning.apply(context,self.folder)
        elif self.stage=='refine':(collection,self.rig,self.meshes),_=regional_jobs.apply(context,self.folder)
        elif self.stage=='motion':collection,self.rig,self.meshes,_,_=motion_apply.apply(context,self.folder,
            self.options['motion_hand_curl'],self.options['motion_contacts'],self.options.get('motion_heading',False),self.options.get('hands'))
        else:raise ValueError('Unknown workflow phase')
        self.generated.append([self.rig,*self.meshes])
        select(context,self.rig,self.meshes)
        settings=context.scene.lc_settings
        job_property={'placement':'placement_job','skin':'skin_job','refine':'region_job','motion':'motion_job'}.get(self.stage)
        if job_property:setattr(settings,job_property,str(self.folder))
        self.stages.append(dict(stage=self.stage,job=str(self.folder),collection=collection.name))
        self._write('phase_applied')
        if self.stage=='refine':
            report=deformation_qa.inspect(self.rig,self.meshes);severe,warnings=deformation_qa.findings(report)
            self.rig['lc_deformation_report']=json.dumps(report);settings.deformation_report=json.dumps(report)
            (self.record/'deformation-report.json').write_text(json.dumps(report,indent=2))
            if severe and not self.options.get('allow_strain',False):
                self.halted='Deformation needs correction before motion/export. '+severe[0]+'. Review joints/weights or explicit rigid regions; selected copies are retained'
                settings.workflow_status=self.halted;self._write('needs_review',self.halted);_runs.pop(self.id,None)
                return None
        return self.launch(context)

    def finish(self,context):
        self._context(context)
        settings=context.scene.lc_settings
        if self.options.get('loop') and self.options.get('motion'):
            motion_finish.loop(context,self.rig,self.options['motion_loop_blend']);settings.loop_action=True
        if self.options.get('export'):
            destination=exporter.export_bundle(context,self.rig,self.meshes,self.options['export_directory'],
                self.options['character_name'],self.options['profile'],self.options.get('motion',False),self.options.get('loop',False))
            settings.last_export=str(destination)
        if self.options.get('skin_only') and not self.options.get('keep_skin_copies',False):
            self.rig,self.meshes=character_result.skin(context,self.original_rig,self.original_meshes,self.rig,self.meshes,
                owned=[obj for stage in self.generated for obj in stage])
            self.generated=[]
        elif self.options.get('hide_sources',True):
            source=[self.original_rig,*self.original_meshes] if self.original_rig else self.original_meshes[:]
            for obj in source+[o for stage in self.generated[:-1] for o in stage]:
                if obj.name in context.view_layer.objects:obj.hide_set(True)
        select(context,self.rig,self.meshes)
        settings.include_action=bool(self.options.get('motion'));self.rig['lc_workflow']=str(self.record)
        self.finished=True;self.stage=None;self._write('complete');_runs.pop(self.id,None)
        return None

    def cancel(self,error=None):
        if self.folder and str(self.folder) in skinning._jobs:skinning.cancel(self.folder)
        try:self._write('failed' if error else 'cancelled',error)
        finally:_runs.pop(self.id,None)
        # Completed phases remain available for correction or resumption.


def options(settings,skin_only=False,context=None):
    keys=('keep_skin_copies','placement_python','skin_executable','skin_models','skin_device','skin_beams','refine_iterations','refine_strength',
          'refine_seams','motion_prompt','motion_frames','motion_steps','motion_seed','motion_in_place','motion_provider',
          'motion_hand_curl','motion_contacts','motion_heading','motion_loop_blend','motion_use_keyframes','export_directory','character_name','profile')
    values={key:getattr(settings,key) for key in keys}
    values['motion_start_frame']=(context or bpy.context).scene.frame_start
    from . import hand_pose
    values['hands']=hand_pose.settings(settings) if settings.hand_controls else None
    for key in ('placement_python','skin_executable','skin_models','motion_provider'):values[key]=bpy.path.abspath(values[key])
    values.update(reuse_joints=settings.workflow_reuse_joints,rebind=settings.workflow_rebind,motion=settings.workflow_motion,
                  export=settings.workflow_export,loop=settings.workflow_loop,hide_sources=settings.workflow_hide_sources,twists=settings.workflow_twists,rigid_parts=settings.workflow_rigid,allow_strain=settings.workflow_allow_strain)
    if skin_only:values.update(skin_only=True,reuse_joints=True,rebind=True,motion=False,export=False,loop=False,twists=False)
    return values
