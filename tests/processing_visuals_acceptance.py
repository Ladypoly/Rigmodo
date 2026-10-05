"""No scene writes, bounded geometry, routing and scoped cancellation (no inference)."""
import addon_utils,hashlib,importlib,json,statistics,sys,time
from pathlib import Path
from types import SimpleNamespace
import bpy
addon_utils.enable('bl_ext.user_default.local_character',default_set=True)
addon=importlib.import_module('bl_ext.user_default.local_character');pv=addon.processing_visuals
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
fixture=Path.home()/'AppData/Local/Temp/rigmodo-auto-skin-acceptance/skin-review.blend'
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
with bpy.data.libraries.load(str(fixture)) as (available,loaded):loaded.objects=available.objects
for obj in loaded.objects:
    if obj:bpy.context.scene.collection.objects.link(obj)
rig=next(o for o in loaded.objects if o and o.type=='ARMATURE')
meshes=[o for o in loaded.objects if o and o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
addon.workflow.select(bpy.context,rig,meshes);bpy.context.view_layer.update()
def snapshot():
    rows=[]
    for o in bpy.data.objects:
        ad=o.animation_data
        rows.append((o.name,o.as_pointer(),o.data.as_pointer() if o.data else None,o.hide_get(),o.select_get(),
            o.parent.as_pointer() if o.parent else None,[list(row) for row in o.matrix_world],
            ad.action.as_pointer() if ad and ad.action else None,
            [(p.name,p.rotation_mode,list(p.location),list(p.scale),list(p.rotation_quaternion),list(p.rotation_euler),list(p.rotation_axis_angle)) for p in o.pose.bones] if o.type=='ARMATURE' else None))
    return hashlib.sha256(json.dumps((rows,addon.skinning._digest(rig,meshes),bpy.context.scene.frame_current)).encode()).hexdigest()
before=snapshot();rows=[];times=[]
for kind in ('RIG','SKIN','MOTION','IMAGE'):
    token=pv.start(bpy.context,kind,'fixture-job');session=pv._sessions[token]
    pv.capture_geometry(session);count=pv._stats['geometry_builds']
    pv.capture_geometry(session);assert count==pv._stats['geometry_builds']
    for i in range(100):
        begin=time.perf_counter();geometry=pv.geometry(session,session.started+i*.125)
        times.append((time.perf_counter()-begin)*1000)
        assert len(geometry[0])+len(geometry[2])<=4000
    assert pv.geometry(session,session.started+.2)!=pv.geometry(session,session.started+.7)
    assert pv.geometry(session,session.started+.2,True)==pv.geometry(session,session.started+.7,True)
    assert len(session.bones)<=pv.MAX_BONES
    pv.finish(token);assert not pv._sessions
    rows.append(kind)
# Workflow stages update target identity and phase without polling or reading logs.
run=SimpleNamespace(rig=rig,meshes=meshes,folder='workflow-fixture',stage='skin')
token=pv.start(bpy.context,'RIG',run=run);session=pv._sessions[token]
addon.skinning._jobs['workflow-fixture']={'phase':'Generating AI skin weights'}
pv.update_state(session);assert session.kind=='SKIN' and session.phase=='Generating AI skin weights'
run.stage='refine';addon.skinning._jobs['workflow-fixture']={'phase':'Refining skin weights'}
pv.update_state(session);assert session.phase=='Refining skin weights'
run.stage='motion';pv.update_state(session);assert session.kind=='MOTION'
addon.skinning._jobs.clear()
assert bpy.ops.local_character.cancel_processing()=={'FINISHED'} and pv.cancelled(token)
# Requesting cancellation alone must not kill a worker or alter the scene.
assert snapshot()==before
pv.finish(token)
# Worker modal consumes a request through the same owned cancellation path as Escape.
folder=out/'cancel-worker';folder.mkdir(exist_ok=True)
addon.skinning._state(folder,'running')
token=pv.start(bpy.context,'SKIN',str(folder));pv._sessions[token].cancel_requested=True
worker=addon.WorkerModal();worker._scene=bpy.context.scene;worker._folder=folder;worker._visual=token
assert worker.modal(bpy.context,SimpleNamespace(type='TIMER'))=={'CANCELLED'}
assert not pv._sessions
# No GPU timer/handler in background; shutdown removes registered lifecycle handlers.
assert not pv._handles and not bpy.app.timers.is_registered(pv.tick)
pv.reset();assert snapshot()==before
addon_utils.disable('bl_ext.user_default.local_character',default_set=True);assert not any(pv.reset in handlers for handlers in (bpy.app.handlers.load_pre,bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre))
result=dict(passed=True,version=addon.exporter.VERSION,scene_unchanged=True,geometry_cached=True,
    effects=rows,vertex_cap=4000,geometry_median_ms=statistics.median(times),geometry_p95_ms=sorted(times)[int(.95*len(times))],
    reduced_animation_static=True,workflow_phase_tracking=True,cancel_request_owned=True,idle_timer_and_handlers_removed=True,
    simulated_cancellation=True,neural_inference_tested=False)
(out/'results.json').write_text(json.dumps(result,indent=2));print('PROCESSING_VISUALS_ACCEPTANCE',json.dumps(result),flush=True)
