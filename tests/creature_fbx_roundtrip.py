import bpy,json,sys
from pathlib import Path
base=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.wm.open_mainfile(filepath=str(base/'acceptance-final/creature-review.blend'))
rig=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('lc_rig_type')=='CREATURE')
expected={b.name:rig.matrix_world@b.head_local for b in rig.data.bones}
prior=set(bpy.data.objects)
bpy.ops.import_scene.fbx(filepath=str(base/'acceptance-final/exports/CreatureGiraffe/CreatureGiraffe.fbx'),use_anim=False)
imported=next(o for o in set(bpy.data.objects)-prior if o.type=='ARMATURE')
assert set(expected)<=set(imported.data.bones.keys())
error=max((imported.matrix_world@imported.data.bones[name].head_local-point).length for name,point in expected.items())
assert error<1e-4,error
(base/'fbx-roundtrip-results.json').write_text(json.dumps(dict(passed=True,joints_preserved=True,max_joint_world_error=error,bones=len(expected),unity_editor_import_tested=False),indent=2))
print('CREATURE_FBX_ROUNDTRIP',error,flush=True)
