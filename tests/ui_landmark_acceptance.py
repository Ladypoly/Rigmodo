"""Real RNA preferences, uncluttered draws, captured guides and stale rejection."""
import addon_utils,copy,importlib,json,os,shutil,sys
from pathlib import Path
from types import SimpleNamespace
import bpy
from mathutils import Vector
root=Path(__file__).resolve().parents[1];name='bl_ext.user_default.local_character'
addon_utils.enable(name,default_set=True);addon=importlib.import_module(name)
configuration,ui,placement,skinning,landmarks,workflow=(getattr(addon,n) for n in ('configuration','ui','placement','skinning','landmarks','workflow'))
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True)
s=bpy.context.scene.lc_settings;prefs=configuration.preferences(bpy.context);assert prefs
s.skin_beams=7;assert configuration.settings(bpy.context).skin_beams==7
prefs.skin_beams=8;s.skin_beams=3
assert configuration.settings(bpy.context).skin_beams==8 and workflow.options(configuration.settings(bpy.context))['skin_beams']==8
class Layout:
    def __init__(self,records,expanded=False):self.records=records;self.expanded=expanded
    def row(self,**kwargs):return self
    def column(self,**kwargs):return self
    def box(self):return self
    def separator(self):pass
    def label(self,**kwargs):self.records.append(('label',kwargs.get('text','')))
    def prop(self,data,key,**kwargs):assert hasattr(data,key),key;self.records.append(('prop',key))
    def prop_search(self,data,key,search,key_search,**kwargs):assert hasattr(data,key) and hasattr(search,key_search);self.records.append(('prop',key))
    def operator(self,key,**kwargs):
        category,name=key.split('.');assert hasattr(getattr(bpy.ops,category),name)
        self.records.append(('operator',key));return SimpleNamespace()
    def panel(self,key,**kwargs):return self,self if self.expanded else None
for expanded in (False,True):
    for step in ('RIG','SKIN','MOTION','EXPORT'):
        s.ui_step=step;s.ui_skin_advanced=expanded;records=[];ui.draw(Layout(records,expanded),bpy.context)
        assert not set(configuration.KEYS)&{key for kind,key in records if kind=='prop'},records
for page in ('SETUP','DEFAULTS','RECOVERY'):prefs.page=page;ui.draw_preferences(Layout([],True),bpy.context,prefs)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
bpy.ops.import_scene.gltf(filepath=r'R:\BLENDER\BANTER_Avatars\Shane.glb')
rig=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==rig for m in o.modifiers)]
workflow.select(bpy.context,rig,meshes);before=skinning._digest(rig,meshes)
# Exercise actual mode switches and the focused paint panel on private geometry.
assert bpy.ops.local_character.weight_editor()=={'FINISHED'} and bpy.context.mode=='PAINT_WEIGHT'
assert bpy.ops.brush.asset_activate(asset_library_type='ESSENTIALS',relative_asset_identifier='brushes/essentials_brushes-mesh_weight.blend/Brush/Paint')=={'FINISHED'}
records=[];ui.draw(Layout(records,True),bpy.context)
assert ('prop','ui_weight_bone') in records
assert all(('prop',key) in records for key in ('weight','strength','size'))
s.ui_weight_bone=meshes[0].vertex_groups[0].name
assert bpy.context.active_object.vertex_groups.active.name==s.ui_weight_bone
assert bpy.ops.local_character.test_pose()=={'FINISHED'} and bpy.context.mode=='POSE'
assert bpy.ops.local_character.object_mode()=={'FINISHED'}
assert bpy.ops.local_character.select_character()=={'FINISHED'}
assert set(o for o in bpy.context.selected_objects if o.type=='MESH')==set(meshes)
assert bpy.ops.local_character.edit_joints()=={'FINISHED'} and bpy.context.mode=='EDIT_ARMATURE'
assert bpy.ops.local_character.object_mode()=={'FINISHED'}
workflow.select(bpy.context,rig,meshes)
assert before==skinning._digest(rig,meshes)
private=Path(os.environ['LOCALAPPDATA'])/'Temp';old=json.loads((private/'local-character-one-click/results.json').read_text())
record=json.loads((Path(old['workflow_record'])/'workflow.json').read_text())
cached=Path(next(stage['job'] for stage in record['stages'] if stage['stage']=='placement'))
model=json.loads((cached/'output.json').read_text());predicted={n:Vector((p[0],-p[2],p[1])) for n,p in zip(model['names'],model['heads'])}
data=dict(schema_version=1,mesh_digest=skinning._digest(None,meshes),points={})
for bone in {n for n,_ in landmarks.STEPS}|{n for n,_ in landmarks.RIGHT}:
    p=predicted[bone].copy();p.x+=.002;p.z+=.003;data['points'][bone]=list(p)
s=bpy.context.scene.lc_settings;s.landmark_data=json.dumps(data);prefs.workflow_hide_sources=True
folder=placement.prepare(bpy.context,meshes,rig,parent=output,landmarks=data)
shutil.copy2(cached/'output.json',folder/'output.json');placement.finish(folder);skinning._state(folder,'complete');s.placement_job=str(folder)
assert bpy.ops.local_character.apply_placement_job()=={'FINISHED'}
target=bpy.context.active_object;copies=[o for o in bpy.context.selected_objects if o.type=='MESH']
assert s.ui_step=='SKIN' and all(o.hide_get() for o in [rig,*meshes])
assert before==skinning._digest(rig,meshes)
for bone,p in data['points'].items():
    actual=target.matrix_world@target.data.bones[bone].head_local
    assert max(abs(actual[i]-p[i]) for i in (0,2))<1e-6 and abs(actual.y-predicted[bone].y)<1e-6
    assert target.data.bones[bone]['lc_joint_locked']
try:skinning.prepare(bpy.context,target,[meshes[0],copies[0]],parent=output);raise AssertionError('Original + derived accepted')
except ValueError as error:assert 'copies of the same avatar' in str(error)
# Changed guides fail before allocating any review objects.
second=placement.prepare(bpy.context,meshes,rig,parent=output,landmarks=data)
shutil.copy2(cached/'output.json',second/'output.json');placement.finish(second);skinning._state(second,'complete')
changed=copy.deepcopy(data);changed['points']['Head'][2]+=.01;s.landmark_data=json.dumps(changed);count=len(bpy.data.objects)
try:placement.apply(bpy.context,second);raise AssertionError('Edited guides accepted')
except ValueError as error:assert 'Landmarks changed' in str(error)
assert len(bpy.data.objects)==count
result=dict(passed=True,global_preferences_used=True,legacy_settings_migrated=True,workflow_panel_has_no_runtime_fields=True,
    eight_front_anchors_exact=True,model_depth_preserved=True,landmarks_locked=True,source_preserved=True,
    sources_hidden_after_individual_step=True,original_plus_copy_rejected=True,stale_landmarks_rejected=True,cached_actual_mia_used=True,
    native_weight_editor_draws=True,bone_choice_updates_group=True,pose_and_joint_editors_work=True,character_selection_helper_works=True)
(output/'results.json').write_text(json.dumps(result,indent=2));print('UI_LANDMARK_ACCEPTANCE',json.dumps(result),flush=True)
