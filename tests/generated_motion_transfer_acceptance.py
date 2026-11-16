# SPDX-License-Identifier: GPL-3.0-or-later
import bpy,addon_utils,importlib,sys,json,tempfile
from pathlib import Path
import numpy as np
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
ctx=bpy.context;rig=a.skeleton.create_armature(ctx);s=ctx.scene.lc_settings;s.create_loop=False;s.motion_contacts=True
a.character_context.pin(ctx,rig,[]);s.rig_type='CREATURE';assert not a.animation_ui.creature_character(ctx,rig);s.rig_type='HUMANOID';lib=Path('R:/AI/MotionLibrary/Rigmodo');entry=next(c for c in a.motion_store.catalog(lib)['clips'] if c['family']=='Human' and c['name'].casefold()=='walk');data=a.motion_store.read(lib,entry['id'])
original=a.motion_retarget.apply(ctx,rig,data,'Original');oldcurves=[(c.data_path,c.array_index,[(tuple(p.co),p.interpolation) for p in c.keyframe_points]) for c in a.motion_clips.slot_curves(original,rig.animation_data.action_slot)]
collection=bpy.data.collections.new('Owned generated review');ctx.scene.collection.children.link(collection)
review=rig.copy();review.data=rig.data.copy();collection.objects.link(review);review.animation_data_clear()
generated=a.motion_retarget.apply(ctx,review,data,'Generated review');objects=set(bpy.data.objects)-{review};rest={b.name:b.matrix_local.copy() for b in rig.data.bones}
request=dict(rig=rig.name,meshes=[],prompt='Acceptance',ui_pipeline=dict(motion_in_place=True,create_loop=True,motion_contacts=True,ground_height=0.,keep_copies=False))
assert a.animation_transfer.adopt_generated(ctx,Path(tempfile.mkdtemp()),request,collection,review,[],generated)
assert set(bpy.data.objects)==objects and rig.animation_data.action!=original
assert all(b.matrix_local==rest[b.name] for b in rig.data.bones)
assert oldcurves==[(c.data_path,c.array_index,[(tuple(p.co),p.interpolation) for p in c.keyframe_points]) for c in a.motion_clips.slot_curves(original,original.slots[0])]
assert all(not action.get('lc_internal_variant') for action,slot in a.motion_clips.available(rig))
# Different central chain counts must retain all target bones and fixed lengths.
ctx.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT');bones=rig.data.edit_bones;upper=bones['Spine1'];parent=upper.parent
extra=bones.new('ExtraSpine');extra.head=parent.head.lerp(upper.head,.5);extra.tail=upper.head;extra.parent=parent;parent.tail=extra.head;upper.parent=extra
bpy.ops.object.mode_set(mode='OBJECT');rest={b.name:b.matrix_local.copy() for b in rig.data.bones}
action=a.animation_transfer.finish(ctx,rig,data,'Different spine')
assert all(b.matrix_local==rest[b.name] for b in rig.data.bones)
for f in (1,12,24):
    ctx.scene.frame_set(f);ctx.view_layer.update();assert all(abs(p.bone.length-(p.tail-p.head).length)<1e-5 for p in rig.pose.bones)
# Manual contact overrides retain explicit flight and reject out-of-range intervals.
action['lc_contact_overrides']=json.dumps([dict(side='Left',start=0,end=.2,mode='AIR')]);assert a.motion_contacts.contact_overrides(action,float(data['times'][-1]))
action['lc_contact_overrides']=json.dumps([dict(side='Left',start=0,end=999,mode='PLANT')])
try:a.motion_contacts.contact_overrides(action,float(data['times'][-1]));raise AssertionError('Invalid interval accepted')
except ValueError:pass
report=dict(passed=True,generated_motion_same_character=True,owned_review_removed=True,original_action_unchanged=True,internal_variants_hidden=True,different_spine_counts=True,bone_lengths_preserved=True,contact_overrides_validated=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('TRANSFER_EDITOR_ACCEPTANCE_PASS',report)
