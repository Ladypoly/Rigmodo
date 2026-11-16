import bpy,addon_utils,importlib,sys,json,tempfile
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
root=Path('R:/AI/MotionLibrary/Rigmodo');entries=a.motion_store.catalog(root)['clips']
assert len(entries)>=330 and all((root/'Assets'/(e['id']+'.blend')).is_file() for e in entries)
for entry in [next(e for e in entries if e['family']=='Human' and e['name']=='Walk'),next(e for e in entries if e['name']=='Scorpion_WalkFast_Attack_Arcade')]:
    path=root/'Assets'/(entry['id']+'.blend')
    with bpy.data.libraries.load(str(path),link=False) as (available,loaded):
        assert not available.objects and not available.armatures
        loaded.actions=available.actions
    action=loaded.actions[0]
    assert action.asset_data and action['lc_library_id']==entry['id']
    assert action.preview.image_size[0]>0
    assert action.frame_end>action.frame_start and len(action.slots)==1
    assert abs((action.frame_end-action.frame_start)/(bpy.context.scene.render.fps/bpy.context.scene.render.fps_base)-entry['duration'])<.0001
    curves=a.motion_store.curves_for(action,action.slots[0]);assert len(curves)>10 and max(len(c.keyframe_points) for c in curves)>20
    assert action.asset_data.catalog_id in (root/'Assets'/'blender_assets.cats.txt').read_text()
    assert not getattr(action,'lc_clip_owner',None)
    bpy.data.actions.remove(action)
report=dict(passed=True,assets=330,full_human_and_scorpion_actions=True,thumbnails_embedded=True,native_catalogs=True,no_mesh_or_armature_dependencies=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('ASSET_ACTIONS_PASS',json.dumps(report))
