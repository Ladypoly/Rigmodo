# SPDX-License-Identifier: GPL-3.0-or-later
import bpy,addon_utils,importlib,json,sys,tempfile
from pathlib import Path
addon_utils.enable('bl_ext.user_default.local_character');a=importlib.import_module('bl_ext.user_default.local_character')
folder=Path(tempfile.mkdtemp(prefix='rigmodo-bvh-'));path=folder/'synthetic.bvh'
path.write_text('''HIERARCHY
ROOT Hips
{
 OFFSET 0 1 0
 CHANNELS 6 Xposition Yposition Zposition Zrotation Xrotation Yrotation
 JOINT Head
 {
  OFFSET 0 1 0
  CHANNELS 3 Zrotation Xrotation Yrotation
  End Site
  {
   OFFSET 0 .2 0
  }
 }
}
MOTION
Frames: 4
Frame Time: 0.0333333333333333
0 0 0 0 0 0 0 0 0
.1 0 0 0 0 0 0 0 0
.2 0 0 0 0 0 0 0 0
.3 0 0 0 0 0 0 0 0
''')
from importlib import import_module
worker=import_module(a.__name__+'.motion_library_worker');added,keys=worker.import_file(path,folder/'Library','Synthetic fixture','CC0','',a.motion_store)
assert len(keys)==1
data=a.motion_store.read(folder/'Library',keys[0]);assert len(data['times'])>=4 and abs(float(data['times'][-1])-.1)<.0001
assert len(data['names'])==2 and data['poses'][-1,0,0,3]>data['poses'][0,0,0,3]
report=dict(passed=True,bvh_ingestion=True,physical_timestamps=True,source_motion_preserved=True)
Path(sys.argv[sys.argv.index('--')+1]).write_text(json.dumps(report,indent=2));print('BVH_ACCEPTANCE_PASS',report)
