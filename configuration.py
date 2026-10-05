# SPDX-License-Identifier: GPL-3.0-or-later
"""Global runtime preferences with legacy scene compatibility for old files."""
KEYS=('placement_python','skin_executable','skin_models','skin_device','skin_beams','motion_provider',
      'motion_steps','motion_seed','refine_iterations','refine_seams','voxel_resolution',
      'workflow_hide_sources','keep_skin_copies','workflow_allow_strain','setup_python','setup_archive',
      'image_pose_provider','image_pose_models','image_pose_hands')

def preferences(context):
    addon=context.preferences.addons.get(__package__)
    return addon.preferences if addon else None

def settings(context):
    scene=context.scene.lc_settings;prefs=preferences(context)
    if prefs and not prefs.settings_migrated:
        for key in KEYS:
            if not prefs.is_property_set(key) and scene.is_property_set(key):setattr(prefs,key,getattr(scene,key))
        prefs.settings_migrated=True
    return Settings(scene,prefs)

class Settings:
    def __init__(self,scene,prefs):object.__setattr__(self,'scene',scene);object.__setattr__(self,'prefs',prefs)
    def __getattr__(self,key):return getattr(self.prefs if self.prefs and key in KEYS else self.scene,key)
    def __setattr__(self,key,value):setattr(self.prefs if self.prefs and key in KEYS else self.scene,key,value)

def hide_sources(context,objects):
    if settings(context).workflow_hide_sources:
        for obj in objects:
            if obj and obj.name in context.view_layer.objects:obj.hide_set(True)
