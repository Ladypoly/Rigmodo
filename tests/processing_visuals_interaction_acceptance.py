"""Real viewport draw/cleanup and real Skin Avatar in an isolated GUI, private fixture."""
import addon_utils,hashlib,importlib,json,statistics,sys,time,traceback
from pathlib import Path
import bpy,gpu
from mathutils import Vector
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
neural='--neural' in sys.argv[sys.argv.index('--')+2:]
addon_utils.enable('bl_ext.user_default.local_character',default_set=True)
addon=importlib.import_module('bl_ext.user_default.local_character');pv=addon.processing_visuals
bpy.context.preferences.view.show_splash=False
prefs=addon.configuration.preferences(bpy.context);prefs.processing_visuals=True;prefs.processing_reduced_animation=False
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
fixture=Path.home()/'AppData/Local/Temp/rigmodo-auto-skin-acceptance/skin-review.blend'
with bpy.data.libraries.load(str(fixture)) as (available,loaded):loaded.objects=available.objects
for obj in loaded.objects:
    if obj:bpy.context.scene.collection.objects.link(obj)
rig=next(o for o in loaded.objects if o and o.type=='ARMATURE')
meshes=[o for o in loaded.objects if o and o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
for obj in list(bpy.data.objects):
    if obj not in [rig,*meshes]:bpy.data.objects.remove(obj,do_unlink=True)
addon.workflow.select(bpy.context,rig,meshes);scene=bpy.context.scene;scene.frame_set(1);scene.lc_settings.ui_step='SKIN'
rig.data.display_type='STICK';rig.show_in_front=False
window=bpy.context.window;area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
region=next(r for r in area.regions if r.type=='WINDOW');space=area.spaces.active
space.show_region_ui=False;space.overlay.show_floor=False;space.overlay.show_axis_x=False;space.overlay.show_axis_y=False
space.region_3d.view_perspective='PERSP';space.region_3d.view_location=Vector((0,0,.85))
space.region_3d.view_rotation=Vector((2.8,-5.5,2.1)).to_track_quat('Z','Y');space.region_3d.view_distance=3.
bpy.context.view_layer.update()
def snapshot():
    return hashlib.sha256(json.dumps((addon.skinning._digest(rig,meshes),scene.frame_current,
        [(o.name,o.as_pointer(),o.data.as_pointer(),o.hide_get(),o.select_get(),[list(row) for row in o.matrix_world]) for o in [rig,*meshes]],
        [(p.name,p.rotation_mode,list(p.location),list(p.scale),list(p.rotation_quaternion),list(p.rotation_euler),list(p.rotation_axis_angle)) for p in rig.pose.bones])).encode()).hexdigest()
before=snapshot();identities=[(o.name,o.as_pointer()) for o in [rig,*meshes]]
counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections))
action=rig.animation_data.action if rig.animation_data else None
rest={b.name:b.matrix_local.copy() for b in rig.data.bones}
state={'phase':0,'started':time.monotonic(),'deadline':0,'token':None,'draws':0};rows=[];bench=[]
def screenshot(name):
    with bpy.context.temp_override(window=window):bpy.ops.screen.screenshot(filepath=str(out/(name+'.png')))
def finish():
    result=dict(passed=True,version=addon.exporter.VERSION,cases=rows,real_viewport_gpu_draws=pv._stats['draws'],
        maximum_vertices=pv._stats['max_vertices'],geometry_capture_count=pv._stats['geometry_builds'],
        warmed_batch_build_median_ms=statistics.median(bench),warmed_batch_build_p95_ms=sorted(bench)[int(.95*len(bench))],
        max_effect_draw_cpu_ms=pv._stats['draw_ms'],max_hud_draw_cpu_ms=pv._stats['hud_ms'],forced_redraw_hz=pv.FPS,
        actual_skin_inference=neural,private_fixture_vertex_count=sum(len(m.data.vertices) for m in meshes),
        viewport_preview_is_simulated=True,no_neural_model_used_for_preview=True,
        original_scene_preserved_during_effects=True,artists_data_preserved_by_actual_skin=neural)
    (out/'results.json').write_text(json.dumps(result,indent=2));print('PROCESSING_INTERACTION_COMPLETE',json.dumps(result),flush=True)
    pv.reset();bpy.ops.wm.quit_blender()
def run():
    global rows
    try:
        if time.monotonic()-state['started']>200:raise AssertionError('Viewport test timed out')
        phase=state['phase'];now=time.monotonic()
        if now<state['deadline']:return .1
        if phase<4:
            if state['token']:
                assert pv._stats['draws']>state['draws'],'Viewport did not execute the draw handler'
                session=pv._sessions[state['token']]
                # Actual GPU state is restored even with nondefault overlay state.
                with bpy.context.temp_override(window=window,area=area,region=region):
                    original=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get())
                    gpu.state.blend_set('ADDITIVE');gpu.state.depth_test_set('LESS_EQUAL');gpu.state.depth_mask_set(True)
                    expected=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get())
                    pv.draw_world();pv.draw_hud()
                    assert expected==(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get())
                    gpu.state.blend_set(original[0]);gpu.state.depth_test_set(original[1]);gpu.state.depth_mask_set(original[2])
                for i in range(50):
                    start=time.perf_counter();pv.build_batches(session,session.started+i*.125,False);bench.append((time.perf_counter()-start)*1000)
                screenshot(('rig','skin','motion','image')[phase-1]);pv.finish(state['token']);state['token']=None
                assert not pv._handles and not bpy.app.timers.is_registered(pv.tick)
                assert snapshot()==before
            kind=('RIG','SKIN','MOTION','IMAGE')[phase]
            state['draws']=pv._stats['draws'];state['token']=pv.start(bpy.context,kind)
            rows.append(kind.lower()+'_overlay');state['phase']+=1;state['deadline']=now+1.2
        elif phase==4:
            assert pv._stats['draws']>state['draws'];screenshot('image');pv.finish(state['token']);state['token']=None
            assert snapshot()==before;rows.append('scene_identity_pose_weights_unchanged')
            prefs.processing_reduced_animation=True;token=pv.start(bpy.context,'SKIN');assert pv.tick()==1.
            session=pv._sessions[token]
            assert pv.geometry(session,now,True)==pv.geometry(session,now+9,True)
            pv.finish(token);prefs.processing_reduced_animation=False
            prefs.processing_visuals=False;token=pv.start(bpy.context,'SKIN');assert pv.tick()==.5 and not pv._handles
            pv.finish(token);prefs.processing_visuals=True;rows+=['reduced_static','disabled_has_no_draw_handlers']
            token=pv.start(bpy.context,'SKIN');pv.tick();space.overlay.show_overlays=False
            assert pv.tick()==.5 and not pv._handles
            with bpy.context.temp_override(window=window,area=area,region=region):assert not pv.drawable_sessions(bpy.context)
            space.overlay.show_overlays=True;pv.reset();assert not pv._handles and not bpy.app.timers.is_registered(pv.tick)
            rows+=['blender_overlay_toggle_respected','load_undo_cleanup']
            if not neural:finish();return None
            with bpy.context.temp_override(window=window,area=area,region=region):
                assert bpy.ops.local_character.build_character(auto_skin=True)=={'RUNNING_MODAL'}
            assert pv.active(scene) and addon.skinning._jobs
            state['phase']=5;state['skin_start']=now;state['captured']=False
        elif phase==5:
            session=pv.active(scene)
            if session and not state['captured'] and now-state['skin_start']>3:
                screenshot('actual-skin-running');state['captured']=True
            if addon.skinning._jobs or addon.workflow._runs:return .2
            assert identities==[(o.name,o.as_pointer()) for o in [rig,*meshes]]
            assert counts==(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections))
            assert rig.animation_data.action==action and all(rig.data.bones[n].matrix_local==m for n,m in rest.items())
            assert 'Character ready' in scene.lc_settings.workflow_status,scene.lc_settings.workflow_status
            rows+=['real_auto_skin_phases_and_stable_identity'];state['phase']=6;state['deadline']=now+1.5
        elif phase==6:
            assert not pv._sessions and not pv._handles and not bpy.app.timers.is_registered(pv.tick)
            rows.append('success_flash_self_removes')
            state['after_skin']=snapshot()
            with bpy.context.temp_override(window=window,area=area,region=region):
                assert bpy.ops.local_character.build_character(auto_skin=True)=={'RUNNING_MODAL'}
                assert bpy.ops.local_character.cancel_processing()=={'FINISHED'}
            state['phase']=7;state['deadline']=now+.8
        elif phase==7:
            if addon.skinning._jobs or addon.workflow._runs:return .2
            assert 'Cancelled' in scene.lc_settings.workflow_status
            assert snapshot()==state['after_skin']
            assert not pv._sessions and not pv._handles and not bpy.app.timers.is_registered(pv.tick)
            rows.append('actual_workflow_cancel_button_preserves_character');finish();return None
    except Exception:
        (out/'error.txt').write_text(traceback.format_exc());traceback.print_exc();screenshot('failure')
        pv.reset();addon.skinning.cancel_all();bpy.ops.wm.quit_blender();return None
    return .1
bpy.app.timers.register(run,first_interval=1.)
