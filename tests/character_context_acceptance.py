import bpy,addon_utils,importlib,json,sys,tempfile
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
rig=a.skeleton.create_armature(bpy.context);bpy.ops.mesh.primitive_cube_add();mesh=bpy.context.object
m=mesh.modifiers.new('Character','ARMATURE');m.object=rig
a.character_context.pin(bpy.context,rig,[mesh]);name=rig.name;meshname=mesh.name
bpy.ops.mesh.primitive_cube_add();other=bpy.context.object
assert a.motion_jobs.selected_rig(bpy.context)==rig
assert a.skinning.selection(bpy.context)==(rig,[mesh])
assert a.placement.selected(bpy.context)==(rig,[mesh])
assert a.motion_jobs.character_meshes(bpy.context,rig)==[mesh]
s=bpy.context.scene.lc_settings;s.motion_duration=1.5;assert s.motion_frames==46 and s.unimate_frames==46
path=Path(tempfile.mkdtemp(prefix='rigmodo-context-'))/'pinned.blend'
bpy.ops.wm.save_as_mainfile(filepath=str(path),copy=True);bpy.ops.wm.open_mainfile(filepath=str(path))
assert a.motion_jobs.selected_rig(bpy.context).name==name
assert a.skinning.selection(bpy.context)[1][0].name==meshname
rig=bpy.data.objects[name];bpy.data.objects.remove(rig,do_unlink=True)
try:a.motion_jobs.selected_rig(bpy.context);raise AssertionError('Removed character silently changed')
except ValueError:pass
bpy.context.scene.lc_settings.character_pinned=False
a.unregister();a.register();assert hasattr(bpy.context.scene.lc_settings,'character')
report=dict(passed=True,pinned_rig_and_mesh_scope=True,selection_changes_safe=True,removed_character_rejected=True,survives_save_reload=True,registration_cycle=True,duration_in_seconds=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('UI_CONTEXT_PASS',report)
