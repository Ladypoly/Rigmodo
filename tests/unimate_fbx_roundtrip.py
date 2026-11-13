"""Check neural FK → Blender Action → exported/reimported Generic FBX."""
import bpy,json,math,sys
from pathlib import Path
from mathutils import Vector
import numpy as np
base=Path(sys.argv[sys.argv.index('--')+1])
report=json.loads((base/'model.json').read_text());job=Path(report['job']);request=json.loads((job/'request.json').read_text())
with np.load(job/'motion.npz',allow_pickle=False) as data:positions=data['positions']
bpy.ops.wm.open_mainfile(filepath=str(base/'scorpion-unimate-review.blend'))
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('lc_motion_job')==request['job_id'])
samples={};neural_error=0.
for index in (0,15,30,45,59):
    frame=request['start_frame']+index*request['scene_fps']/30
    bpy.context.scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update()
    samples[frame]={p.name:rig.matrix_world@p.head for p in rig.pose.bones}
    for j,name in enumerate(request['skeleton']['bone_names']):
        if name:neural_error=max(neural_error,(samples[frame][name]-Vector(positions[index,j])-rig.matrix_world.translation).length)
assert neural_error<1e-4,neural_error
# FBX bakes at the scene's integer frames; compare those samples rather than 30 fps subframes.
last=max(samples);samples.pop(last);frame=math.ceil(last)
bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
samples[frame]={p.name:rig.matrix_world@p.head for p in rig.pose.bones}
before=set(bpy.data.objects)
fbx=next((base/'export/ScorpionUniMate/Animations').glob('*.fbx'))
bpy.ops.import_scene.fbx(filepath=str(fbx),use_anim=True,anim_offset=0)
imported=next(o for o in set(bpy.data.objects)-before if o.type=='ARMATURE')
assert set(rig.data.bones.keys())<=set(imported.data.bones.keys())
error=0.
for frame,expected in samples.items():
    bpy.context.scene.frame_set(math.floor(frame),subframe=frame%1);bpy.context.view_layer.update()
    error=max(error,max((imported.matrix_world@imported.pose.bones[name].head-point).length for name,point in expected.items()))
assert error<1e-4,error
result=dict(passed=True,neural_fk_max_joint_error=neural_error,fbx_animation_max_joint_error=error,joints_preserved=True,
    bones=len(rig.data.bones),sampled_frames=list(samples),unity_editor_import_tested=False)
(base/'fbx-roundtrip.json').write_text(json.dumps(result,indent=2));print('UNIMATE_FBX_PASS',json.dumps(result),flush=True)
