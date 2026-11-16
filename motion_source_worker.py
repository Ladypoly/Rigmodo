# SPDX-License-Identifier: GPL-3.0-or-later
"""Create reusable motion assets in isolation; one GPU child at a time."""
import importlib,json,os,subprocess,sys,time,traceback
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix


def main(folder):
    request=json.loads((folder/'request.json').read_text(encoding='utf-8'));root=Path(__file__).parent
    os.environ['RIGMODO_MODEL_DIRECTORY']=request['model_root'];sys.path.insert(0,str(root.parent))
    bpy.ops.wm.read_factory_settings(use_empty=True);addon=importlib.import_module(root.name);addon.register();bpy.context.scene.render.fps=30
    store=addon.motion_store;library=Path(request['library']);added=[];errors=[];completed=[]
    last_phase=None
    def progress(phase):
        nonlocal last_phase
        if phase!=last_phase:store.atomic(folder/'progress.json',dict(phase=phase));print('SOURCE_STAGE',phase,flush=True);last_phase=phase
    def dispose():
        if bpy.context.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
        for obj in list(bpy.context.scene.objects):
            data=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if data and data.users==0:
                (bpy.data.armatures if isinstance(data,bpy.types.Armature) else bpy.data.meshes).remove(data)
        for action in list(bpy.data.actions):bpy.data.actions.remove(action)
    def checkpoint():store.atomic(folder/'results.json',dict(added=added,completed=completed,errors=errors,system=request['system']))
    def save(data,name,metadata,keys=None):
        # Source cleanup happens on a disposable skeleton, independently of avatars.
        if request['loop'] or request['in_place']:
            rig=addon.motion_assets.source_rig(bpy.context,data)
            data=dict(data,rest=np.array([rig.data.bones[str(n)].matrix_local for n in data['names']],dtype=np.float32))
            s=bpy.context.scene.lc_settings;s.create_loop=request['loop'];s.motion_in_place=request['in_place'];s.motion_contacts=False
            action=addon.animation_transfer.finish(bpy.context,rig,data,name,metadata)
            if keys:
                adjusted=json.loads(json.dumps(keys));offset=adjusted['start_frame']-action.frame_start;adjusted['start_frame']-=offset
                for pose in adjusted['poses']:pose['frame']-=offset
                addon.motion_keyframes.overlay(bpy.context,rig,adjusted)
            data=store.capture(bpy.context,rig,action,rig.animation_data.action_slot)
        else:
            data=dict(data,provenance=np.asarray([json.dumps(metadata)]))
        key,created=store.write(library,data,name,metadata['lc_library_source'],metadata['lc_library_license'],loop=request['loop'])
        if key not in added:added.append(key)
        dispose();return key,created
    system=request['system']
    if system in {'KIMODO','MOTIONBRICKS','UNIMATE'}:
        model=folder/'model';store.atomic(folder/'active.json',dict(folder=str(model)))
        native=json.loads((model/'request.json').read_text())
        if system=='KIMODO':addon.motion_jobs.start(model,request['provider'])
        elif system=='MOTIONBRICKS':addon.motionbricks.start(model)
        else:addon.unimate.start(model)
        while True:
            state=addon.skinning.poll(model)
            if state['status']!='running':break
            progress(state.get('phase','Generating source motion'));time.sleep(.5)
        if state['status']!='complete':raise ValueError(state.get('error') or 'Source motion generation failed')
        progress('Saving reusable source motion')
        settings=bpy.context.scene.lc_settings
        if (folder/'source-rest.npz').is_file():
            if addon.motion_jobs.sha(folder/'source-rest.npz')!=request['source_rest_sha256']:raise ValueError('Source skeleton snapshot changed')
            rig=addon.motion_assets.source_rig(bpy.context,store.read_file(folder/'source-rest.npz'))
            rig.matrix_world=Matrix(request['source_world']);bpy.context.scene.unit_settings.scale_length=request['unit_scale']
            for key,value in request.get('source_properties',{}).items():rig[key]=value
        else:rig=addon.skeleton.create_armature(bpy.context)
        keys=None
        if system=='UNIMATE':
            native,report,positions,rotations=addon.unimate.output(model)
            bpy.context.scene.render.fps=round(native['scene_fps']);bpy.context.scene.render.fps_base=round(native['scene_fps'])/native['scene_fps']
            action=addon.unimate.bake(bpy.context,rig,native,positions,rotations)
        else:
            keys=addon.motion_jobs.check_inputs(model,native);positions,rotations=addon.motion_data.load(model,native['frames'])
            if keys:
                bpy.context.scene.render.fps=round(keys['scene_fps']);bpy.context.scene.render.fps_base=round(keys['scene_fps'])/keys['scene_fps']
            action=addon.motion_apply.bake(bpy.context,rig,positions,rotations,False,label=request['name'],contacts=False,heading=True,start_frame=keys['start_frame'] if keys else 1,root_origin=(0,0,0) if keys else None)
            if keys:addon.motion_keyframes.overlay(bpy.context,rig,keys)
        data=store.capture(bpy.context,rig,action,rig.animation_data.action_slot)
        key,created=save(data,request['name'],dict(lc_library_source=system+' generated',lc_library_license='User-generated; upstream model terms apply',lc_motion_prompt=request['prompt']),keys)
        completed.append(dict(name=request['name'],id=key,created=created));checkpoint()
    else:
        inputs=request['files'] if system=='VIDEO' else ['ComfyUI']
        for index,filename in enumerate(inputs):
            label=Path(filename).stem if system=='VIDEO' else request['name'];job=folder/'captures'/f'{index:04d}';job.mkdir(parents=True,exist_ok=True)
            try:
                options=dict(request['capture'],id=request['id']+f'-{index}',kind='video' if system=='VIDEO' else 'comfy',video=str(filename),start=request['start'],duration=request['duration'],loop=request['loop'])
                if system=='VIDEO' and request['whole_video']:
                    # Probe without importing the Torch capture runtime into Blender.
                    command=[options['ffprobe'],'-v','error','-show_entries','format=duration','-of','json',str(filename)]
                    probe=subprocess.run(command,capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    duration=float(json.loads(probe.stdout)['format']['duration'])
                    if duration>60.001:raise ValueError('Capture supports up to 60 seconds per clip; trim or split this video')
                    options['start']=0;options['duration']=duration
                store.atomic(job/'request.json',options);store.atomic(folder/'active.json',dict(folder=str(job)))
                with (job/'worker.log').open('wb') as log:
                    child=subprocess.Popen([request['capture_python'],str(root/'video_worker.py'),'--',str(job)],stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    try:
                        while child.poll() is None:
                            phase='Capturing video'
                            try:phase=json.loads((job/'progress.json').read_text()).get('phase',phase)
                            except (OSError,ValueError):pass
                            progress(f'{index+1}/{len(inputs)} · {label} · {phase}');time.sleep(.5)
                    finally:
                        if child.poll() is None:child.terminate();child.wait(timeout=5)
                state=json.loads((job/'status.json').read_text())
                if child.returncode or state.get('status')!='complete':raise ValueError(state.get('error') or 'Video capture failed; inspect its worker log')
                result=json.loads((job/'results.json').read_text());data=store.read_file(job/'output.npz')
                name=request['name'] if len(inputs)==1 and request['name'] else label
                metadata=dict(lc_library_source='Video capture' if system=='VIDEO' else 'ComfyUI video capture',lc_library_license='User-provided',lc_capture_video=result['video'],lc_capture_offset_seconds=result['source'].get('capture_start',0)+result.get('metrics',{}).get('selected_cycle',{}).get('start_seconds',0),lc_capture_provenance=json.dumps(result),lc_motion_prompt=request['prompt'])
                key,created=save(data,name,metadata);completed.append(dict(file=str(filename),name=name,id=key,created=created));checkpoint()
            except Exception as exc:
                errors.append(dict(file=str(filename),error=str(exc)));checkpoint();traceback.print_exc();dispose()
    if not added:raise ValueError(errors[0]['error'] if errors else 'No source motions were created')
    progress('Publishing motion assets')
    addon.motion_assets.publish_all(library,lambda i,n,name:progress(f'Publishing {i+1}/{n} · {name}') if i%25==0 else None)
    store.atomic(folder/'results.json',dict(added=added,completed=completed,errors=errors,system=system))
    store.atomic(folder/'status.json',dict(schema_version=1,status='complete'))
    print('MOTION_SOURCE_COMPLETE',json.dumps(dict(motions=len(added),errors=len(errors))),flush=True)


if __name__=='__main__':
    folder=Path(sys.argv[sys.argv.index('--')+1])
    try:main(folder)
    except Exception as exc:
        traceback.print_exc();from tempfile import NamedTemporaryFile
        (folder/'status.json').write_text(json.dumps(dict(schema_version=1,status='failed',error=str(exc))))
        sys.exit(1)
