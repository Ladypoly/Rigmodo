import bpy,addon_utils,importlib,json,sys,numpy as np
from pathlib import Path
folder=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.wm.open_mainfile(filepath=str(folder/'before.blend'),load_ui=False,use_scripts=False);addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character');ctx=bpy.context;rig=ctx.scene.objects['Mummy_Rig'];body=ctx.scene.objects['Mummy_Body'];meshes=[body,ctx.scene.objects['Mummy_staff']]
a.character_context.pin(ctx,rig,meshes);ctx.view_layer.update();before=a.skinning._digest(rig,meshes);old=rig.animation_data.action
new=a.motion_contacts.correct(ctx,rig,old,0);new.name='Mummy Staff · Feet fixed';roles={r:b.name for r,b in zip(a.rig_mapping.names(rig),rig.data.bones)};markers=a.motion_contacts.soles(ctx,rig,roles);ids={}
for side in ('Left','Right'):
 names={roles[side+'Foot'],*[b.name for b in rig.data.bones[roles[side+'Foot']].children_recursive]};groups={g.index for g in body.vertex_groups if g.name in names};vs=[v for v in body.data.vertices if sum(g.weight for g in v.groups if g.group in groups)>.5];height=min((body.matrix_world@v.co).z for v in vs);ids[side]=[v.index for v in vs if (body.matrix_world@v.co).z<height+.012]
records={s:[] for s in ids};max_length=0.
for f in range(1,194):
 ctx.scene.frame_set(f);ctx.view_layer.update();ev=body.evaluated_get(ctx.evaluated_depsgraph_get())
 for side,indices in ids.items():
  points=np.asarray([ev.matrix_world@ev.data.vertices[i].co for i in indices]);m=rig.matrix_world@rig.pose.bones[roles[side+'Foot']].matrix;pm=np.asarray([m@p for p in markers[side]])
  records[side].append(dict(frame=f,min_sole=float(points[:,2].min()),mean_sole=float(points[:,2].mean()),max_sole=float(points[:,2].max()),markers_z=pm[:,2].tolist()))
 max_length=max(max_length,max(abs((b.tail-b.head).length-b.bone.length) for b in rig.pose.bones))
assert before==a.skinning._digest(rig,meshes) and max_length<1e-5
flat=json.loads(new['lc_contact_report'])['flat_intervals'];stationary=[]
for e in flat:
 for row in records[e['side']]:
  t=(row['frame']-1)/24
  if (e['start']==0 or t>=e['start']+.1) and (e['end']>7.96 or t<=e['end']-.1) and e['start']<=t<=e['end']+.001:stationary.append(abs(row['min_sole']))
assert max(stationary)<.002,max(stationary)
report=dict(passed=True,maximum_stationary_sole_error_m=max(stationary),frames=records,contacts=json.loads(new['lc_contact_report']),maximum_length_error=max_length,summary={s:dict(min_m=min(x['min_sole'] for x in rs),max_min_sole_m=max(x['min_sole'] for x in rs),max_sole_m=max(x['max_sole'] for x in rs)) for s,rs in records.items()})
(folder/'fixed-metrics.json').write_text(json.dumps(report,indent=2),encoding='utf-8');ctx.scene.frame_set(193);bpy.ops.wm.save_as_mainfile(filepath=str(folder/'fixed-review.blend'),copy=True);print('FEET_TEST',json.dumps(dict(summary=report['summary'],contacts=report['contacts'],maximum_length_error=max_length)),flush=True)
