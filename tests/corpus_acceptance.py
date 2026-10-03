"""Held-out geometry-only predictions, real skinning and private deformation views."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import bpy
from mathutils import Vector
import numpy as np
extension=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('local_character',extension/'__init__.py',submodule_search_locations=[str(extension)])
addon=importlib.util.module_from_spec(spec);sys.modules[spec.name]=addon;spec.loader.exec_module(addon);addon.register()
from local_character import workflow,skinning,motion_apply,motion_data,motion_jobs,exporter,regional_jobs
sys.path.insert(0,str(Path(__file__).parent));import motion_reference
output=Path(sys.argv[sys.argv.index('--')+1]);output.mkdir(parents=True,exist_ok=True);results=[]
for name,path in [('Cardboard',r'R:\BLENDER\BANTER_Avatars\CardboardBoy\CardboardBoy_02.glb'),('Mechanical',r'R:\BLENDER\BANTER_Avatars\FN T-800_5.glb')]:
    source=Path(path);file_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
    rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE'];assert len(rigs)==1
    original=rigs[0];meshes=[o for o in bpy.context.scene.objects if o.type=='MESH' and any(m.type=='ARMATURE' and m.object==original for m in o.modifiers)]
    before=skinning._digest(original,meshes);workflow.select(bpy.context,original,meshes)
    s=bpy.context.scene.lc_settings;s.workflow_motion=False;s.workflow_reuse_joints=False;s.workflow_export=False
    run=workflow.Run(bpy.context,workflow.options(s));run.launch(bpy.context);s.workflow_id=run.id;started=time.monotonic()
    while not run.finished:
        state=skinning.poll(run.folder)
        if state['status']=='running':time.sleep(.2);continue
        assert state['status']=='complete',(run.folder/'worker.log').read_text()
        assert bpy.ops.local_character.advance_workflow('EXEC_DEFAULT')=={'FINISHED'}
    assert before==skinning._digest(original,meshes)
    for a,b in zip(meshes,run.meshes):
        assert len(a.data.vertices)==len(b.data.vertices)
        assert [tuple(v.co) for v in a.data.vertices]==[tuple(v.co) for v in b.data.vertices]
        assert [uv.name for uv in a.data.uv_layers]==[uv.name for uv in b.data.uv_layers]
        if a.data.shape_keys:assert [k.name for k in a.data.shape_keys.key_blocks]==[k.name for k in b.data.shape_keys.key_blocks]
    roots,q=motion_data.load(motion_jobs.cache()/'evaluation/walk',90)
    # Motion arrays reused; this test claims fresh placement and skin inference only.
    motion_apply.bake(bpy.context,run.rig,roots,q,contacts=True,heading=True)
    bundles=[]
    for profile in ('GENERIC','HUMANOID'):
        bundle=exporter.export_bundle(bpy.context,run.rig,run.meshes,str(output),name+profile,profile=profile,include_action=True)
        bundles.append(bundle)
    for mesh in run.meshes:exporter._prune(mesh,run.rig)
    for bundle in bundles:motion_reference.write(run.rig,run.meshes,bundle)
    # Exercise conservative volume routing on the actual disconnected shells.
    geometry=regional_jobs.prepare(bpy.context,run.rig,run.meshes,parent=output,method='VOXEL',iterations=6)
    regional_jobs.start(geometry)
    while skinning.poll(geometry)['status']=='running':time.sleep(.2)
    assert skinning.poll(geometry)['status']=='complete',(geometry/'worker.log').read_text()
    _,reports=regional_jobs.apply(bpy.context,geometry)
    scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.color_type='SINGLE';scene.display.shading.show_cavity=True
    scene.render.resolution_x=700;scene.render.resolution_y=900;scene.render.resolution_percentage=100
    camera_data=bpy.data.cameras.new('Review');camera=bpy.data.objects.new('Review',camera_data);scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO'
    visible=set(run.meshes)
    for o in scene.objects:
        if o.type=='MESH':o.hide_render=o not in visible
    points=[m.matrix_world@Vector(c) for m in run.meshes for c in m.bound_box]
    lo=Vector([min(v[i] for v in points) for i in range(3)]);hi=Vector([max(v[i] for v in points) for i in range(3)]);center=(lo+hi)/2
    camera.location=center+Vector((0,-4,0));camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();camera_data.ortho_scale=max((hi-lo).z,(hi-lo).x*900/700)*1.2
    for frame in (1,25,49):
        scene.frame_set(frame);scene.render.filepath=str(output/(name+'-'+str(frame)+'.png'));bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(output/(name+'-review.blend')))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==file_hash
    result=dict(case=name,passed=True,source_preserved=True,actual_inference=['MIA','SkinTokens'],motion_arrays_reused=True,
        vertices=sum(len(m.data.vertices) for m in meshes),bones=53,elapsed_seconds=time.monotonic()-started,
        volume_reports=reports,quality='Rendered views require review; no anatomical ground truth assumed')
    results.append(result);(output/'results.json').write_text(json.dumps(results,indent=2));print('CORPUS_CASE',json.dumps(result),flush=True)
