# SPDX-License-Identifier: GPL-3.0-or-later
"""Native FileHandler routing, async completion, Undo/Redo and cancellation in isolated GUI.

Defaults to a simulated worker returning the real MHR fixture. Pass --neural
after the output folder to test native drop, production inference and Undo/Redo
with the separately installed, approved SAM provider.
"""
import addon_utils,importlib,json,shutil,sys,time,traceback
from pathlib import Path
import bpy
assert '--factory-startup' in sys.argv and '--enable-event-simulate' in sys.argv
out=Path(sys.argv[sys.argv.index('--')+1]);out.mkdir(parents=True,exist_ok=True)
neural='--neural' in sys.argv[sys.argv.index('--')+2:]
addon_utils.enable('bl_ext.user_default.local_character',default_set=True)
addon=importlib.import_module('bl_ext.user_default.local_character');ip=addon.image_pose
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
rig=addon.skeleton.create_armature(bpy.context,1.75,25);rig.name='ImagePose_Interaction_Test'
rig.animation_data_create();action=bpy.data.actions.new('Existing Animation');rig.animation_data.action=action
rig.pose.bones['Spine'].keyframe_insert(data_path='rotation_quaternion',frame=1)
bpy.context.view_layer.update()
scene=bpy.context.scene;scene.lc_settings.ui_step='MOTION'
window=bpy.context.window;area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
area.spaces.active.show_region_ui=True
region=next(r for r in area.regions if r.type=='UI')
provider=ip.cache() if neural else out/'provider';provider.mkdir(exist_ok=True)
assert (provider/'runtime/Scripts/python.exe').is_file(), 'Test launcher must link the isolated SAM runtime'
if not neural:(provider/'installation.json').write_text('{}')
else:assert (provider/'installation.json').is_file()
prefs=addon.configuration.preferences(bpy.context);prefs.image_pose_provider=str(provider)
if neural:
    image=out/'reference.jpg';shutil.copyfile(provider/'source/notebook/images/dancing.jpg',image)
else:
    image=out/'reference.png';im=bpy.data.images.new('Reference',width=8,height=8);im.filepath_raw=str(image);im.file_format='PNG';im.save();bpy.data.images.remove(im)
fixture=Path.home()/'AppData/Local/Temp/rigmodo-sam-research/pose-fixture.json'
worker=out/'simulated_worker.py'
worker.write_text('''import hashlib,json,sys,time
from pathlib import Path
folder=Path(sys.argv[1]);time.sleep(.8)
req=json.loads((folder/'request.json').read_text());pose=json.loads(Path(sys.argv[2]).read_text())
pose.update(request_sha256=hashlib.sha256((folder/'request.json').read_bytes()).hexdigest(),input_sha256=req['input_sha256'])
(folder/'pose.json').write_text(json.dumps(pose));(folder/'pose.sha256').write_text(hashlib.sha256((folder/'pose.json').read_bytes()).hexdigest())
''')
original_launch=ip.launch
def simulated_launch(folder,command,phase):
    return original_launch(folder,[str(provider/'runtime/Scripts/python.exe'),'-I',str(worker),str(folder),str(fixture)],'Simulated test worker')
if not neural:ip.launch=simulated_launch
def current():return bpy.data.objects['ImagePose_Interaction_Test']
def snapshot():return {p.name:[v for row in p.matrix_basis for v in row] for p in current().pose.bones}
def diff(a,b):return max(abs(x-y) for n in a for x,y in zip(a[n],b[n]))
baseline=snapshot();counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.actions))
bpy.ops.wm.save_as_mainfile(filepath=str(out/'interaction.blend'))
state={'phase':-1,'start':time.monotonic(),'tab_click':0};rows=[]
def native_drop():
    with bpy.context.temp_override(window=window,area=area,region=region):
        assert ip.LC_FH_image_pose.poll_drop(bpy.context)
        default_handler=next(c for c in bpy.types.FileHandler.__subclasses__() if c.__name__=='VIEW3D_FH_empty_image')
        assert not default_handler.poll_drop(bpy.context)
        assert bpy.ops.wm.drop_import_file('EXEC_DEFAULT',directory=str(out)+'/',files=[{'name':image.name}])=={'FINISHED'}
    assert ip._pending and addon.skinning._jobs
def finish():
    ip.launch=original_launch
    (out/'error.txt').unlink(missing_ok=True)
    (out/'results.json').write_text(json.dumps(dict(passed=True,version=addon.exporter.VERSION,cases=rows,
        actual_file_handler_dispatch=True,simulated_worker=not neural,sam_neural_inference_tested=neural),indent=2))
    bpy.ops.wm.quit_blender()
def run():
    try:
        if time.monotonic()-state['start']>(90 if neural else 35):raise AssertionError('GUI test timed out')
        phase=state['phase']
        if phase==-1:
            if region.active_panel_category=='Rigmodo':state['phase']=0
            else:
                y=region.y+region.height-15-state['tab_click']*12
                if state['tab_click']>60:raise AssertionError('Rigmodo sidebar tab could not be selected')
                state['tab_click']+=1
                window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=region.x+region.width-12,y=y)
                for value in ('PRESS','RELEASE'):window.event_simulate(type='LEFTMOUSE',value=value,x=region.x+region.width-12,y=y)
        elif phase==0:
            bpy.ops.ed.undo_push(message='Image pose baseline');native_drop();state['phase']=1
        elif phase==1 and ip._pending is None:
            assert 'Image pose applied' in scene.lc_settings.image_pose_status,scene.lc_settings.image_pose_status
            assert diff(snapshot(),baseline)>.1
            assert current().animation_data.action.name=='Existing Animation'
            assert counts==(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.actions))
            state['applied']=snapshot();rows.append('native_drop_and_async_apply')
            with bpy.context.temp_override(window=window,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):bpy.ops.ed.undo()
            state['phase']=2
        elif phase==2:
            assert diff(snapshot(),baseline)<1e-6
            rows.append('whole_pose_undo')
            with bpy.context.temp_override(window=window,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):bpy.ops.ed.redo()
            state['phase']=3
        elif phase==3:
            assert diff(snapshot(),state['applied'])<1e-6
            rows.append('whole_pose_redo')
            addon.motion_keyframes.capture(bpy.context,current());rows.append('kimodo_capture')
            if neural:finish();return None
            bpy.context.scene.lc_settings.ui_step='MOTION'
            native_drop();bpy.context.scene.frame_set(2);state['stale']=snapshot();state['phase']=4
        elif phase==4 and ip._pending is None:
            assert 'changed during inference' in bpy.context.scene.lc_settings.image_pose_status
            assert diff(snapshot(),state['stale'])<1e-6
            rows.append('stale_frame_completion_rejected')
            native_drop()
            state['cancel']=snapshot();assert bpy.ops.local_character.cancel_image_pose()=={'FINISHED'}
            assert not ip._pending and not addon.skinning._jobs and diff(snapshot(),state['cancel'])<1e-6
            rows.append('cancel_preserves_pose');finish();return None
    except Exception:
        with bpy.context.temp_override(window=window):bpy.ops.screen.screenshot(filepath=str(out/'failure.png'))
        (out/'error.txt').write_text(traceback.format_exc());ip.cleanup();bpy.ops.wm.quit_blender();return None
    return .2
bpy.app.timers.register(run,first_interval=1)
