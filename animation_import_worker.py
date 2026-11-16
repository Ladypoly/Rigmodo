# SPDX-License-Identifier: GPL-3.0-or-later
import bpy,sys,json,importlib,shutil,traceback
from pathlib import Path
folder=Path(sys.argv[sys.argv.index('--')+1]);root=Path(__file__).parent;sys.path.insert(0,str(root.parent))
store=importlib.import_module(root.name+'.motion_store');worker=importlib.import_module(root.name+'.motion_library_worker')
try:
    request=json.loads((folder/'request.json').read_text());source=Path(request['file']);library=folder/'Source'
    if not source.is_file() or source.stat().st_size>500*1024*1024:raise ValueError('Use an animation file smaller than 500 MB')
    added,keys=worker.import_file(source,library,'User animation','User-provided','',store)
    if len(keys)!=1:raise ValueError('This file contains several animations; batch-import it into Motion Library to select a clip')
    entry=store.catalog(library)['clips'][0];shutil.copyfile(store.clip_dir(library,keys[0])/'motion.npz',folder/'output.npz')
    store.atomic(folder/'results.json',dict(name=entry['name']));store.atomic(folder/'status.json',dict(schema_version=1,status='complete'))
except Exception as exc:
    traceback.print_exc();store.atomic(folder/'status.json',dict(schema_version=1,status='failed',error=str(exc)))
