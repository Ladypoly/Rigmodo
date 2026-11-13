"""Real UniRig giraffe inference, transactional import, optional native AI skin/export."""
import copy,importlib.util,json,shutil,sys,time
from pathlib import Path
from types import SimpleNamespace
import bpy
import numpy as np
root=Path(__file__).resolve().parents[1];name='rigmodo_creature_acceptance'
spec=importlib.util.spec_from_file_location(name,root/'__init__.py',submodule_search_locations=[str(root)])
addon=importlib.util.module_from_spec(spec);sys.modules[name]=addon;spec.loader.exec_module(addon);addon.register()
args=sys.argv[sys.argv.index('--')+1:];out=Path(args[0]);out.mkdir(parents=True,exist_ok=True)
fixture,provider=Path(args[1]),Path(args[2]);full='--skin' in args
scene=bpy.context.scene;s=scene.lc_settings;s.rig_type='CREATURE';s.creature_provider=str(provider)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete()
bpy.ops.import_scene.gltf(filepath=str(fixture));source_rig,source_meshes=addon.placement.selected(bpy.context)
before=addon.skinning._digest(source_rig,source_meshes)
source_ids=[(o.name,o.as_pointer(),o.data.as_pointer()) for o in ([source_rig] if source_rig else [])+source_meshes]
# Original geometry, material assignments and shape keys stay on untouched source objects.
folder=addon.creatures.prepare(bpy.context,source_meshes,source_rig,parent=out,provider=provider)
s.creature_job=str(folder);addon.creatures.start(folder,s.placement_python)
started=time.monotonic()
def await_job(job):
    while True:
        state=addon.skinning.poll(job)
        if state['status']!='running':assert state['status']=='complete',state;return state
        if time.monotonic()-started>240:raise AssertionError('Creature test exceeded time limit')
        time.sleep(.1)
await_job(folder);result=addon.creatures.output(folder);counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes))
assert 2<=len(result['parents'])<=256
assert result['model_coordinate_space']=='blender_z_up' and result['samples']==65536 and result['beams']==15
assert addon.skinning._digest(source_rig,source_meshes)==before
# Malformed model topology and stale artist geometry are rejected before allocation.
saved=(folder/'output.json').read_text();bad=copy.deepcopy(result);bad['parents'][0]=0
(folder/'output.json').write_text(json.dumps(bad))
try:addon.creatures.output(folder);raise AssertionError('Cyclic result accepted')
except ValueError:pass
(folder/'output.json').write_text(saved)
v=source_meshes[0].data.vertices[0];original=v.co.copy();v.co.x+=.01
try:addon.creatures.apply(bpy.context,folder);raise AssertionError('Stale source accepted')
except ValueError as error:assert 'changed' in str(error)
v.co=original
assert counts==(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes))
assert bpy.ops.local_character.apply_creature_rig()=={'FINISHED'}
rig=bpy.context.active_object;meshes=[o for o in bpy.context.selected_objects if o.type=='MESH']
assert addon.creatures.is_creature(rig) and len(rig.data.bones)==len(result['parents'])+1
assert s.profile=='GENERIC' and s.ui_step=='SKIN'
assert all(b.length>1e-6 for b in rig.data.bones)
assert source_ids==[(o.name,o.as_pointer(),o.data.as_pointer()) for o in ([source_rig] if source_rig else [])+source_meshes]
assert addon.skinning._digest(source_rig,source_meshes)==before
assert all(len(mesh.data.vertices)==len(original.data.vertices) for mesh,original in zip(meshes,source_meshes))
class Layout:
    def __init__(self):self.rows=[]
    def row(self,**kw):return self
    def column(self,**kw):return self
    def box(self):return self
    def separator(self):pass
    def prop(self,data,key,**kw):assert hasattr(data,key);self.rows.append(('prop',key))
    def prop_search(self,*args,**kw):pass
    def label(self,**kw):pass
    def panel(self,*args,**kw):return self,self
    def operator(self,key,**kw):self.rows.append(('operator',key));return SimpleNamespace()
for step in ('RIG','SKIN','MOTION'):
    s.ui_step=step;layout=Layout();addon.ui.draw(layout,bpy.context)
    if step=='RIG':
        assert ('operator','local_character.generate_creature_rig') in layout.rows
        assert ('prop','ui_rig_mode') not in layout.rows
    if step=='SKIN':assert ('operator','local_character.ai_skin') in layout.rows
    if step=='MOTION':
        assert ('operator','local_character.generate_motion') not in layout.rows
        assert ('operator','local_character.image_pose') not in layout.rows
s.ui_step='SKIN';addon.workflow.select(bpy.context,rig,meshes)
before_skin=[(o.name,o.as_pointer()) for o in [rig,*meshes]];skin_counts=(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections))
export=None
if full:
    skin=addon.skinning.prepare(bpy.context,rig,meshes,parent=out,device=s.skin_device,beams=s.skin_beams)
    addon.skinning.start(skin,s.skin_executable,s.skin_models);await_job(skin);s.skin_job=str(skin)
    assert bpy.ops.local_character.apply_skin_job()=={'FINISHED'}
    assert before_skin==[(o.name,o.as_pointer()) for o in [rig,*meshes]]
    assert skin_counts==(len(bpy.data.objects),len(bpy.data.armatures),len(bpy.data.meshes),len(bpy.data.collections))
    report=addon.preflight.inspect(rig,meshes,'GENERIC');assert not report['errors'],report
    export=addon.exporter.export_bundle(bpy.context,rig,meshes,str(out/'exports'),'CreatureGiraffe','GENERIC')
bpy.ops.wm.save_as_mainfile(filepath=str(out/'creature-review.blend'))
record=dict(passed=True,version=addon.exporter.VERSION,actual_unirig_inference=True,joints=len(result['parents']),
    model_elapsed_seconds=result['elapsed_seconds'],peak_gpu_bytes=result['peak_gpu_bytes'],
    stale_and_cyclic_results_rejected=True,source_objects_geometry_materials_preserved=True,
    variable_hierarchy=True,creature_ui_routes_correctly=True,actual_skin_inference=full,
    skin_keeps_identity=full,unity_generic_bundle=str(export) if export else None,
    unity_editor_import_tested=False,model_coordinate_space=result['model_coordinate_space'],samples=result['samples'],beams=result['beams'])
(out/'results.json').write_text(json.dumps(record,indent=2));print('CREATURE_ACCEPTANCE',json.dumps(record),flush=True)
