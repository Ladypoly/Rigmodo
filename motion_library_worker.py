# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated Blender import worker: never loads downloaded assets into the user's scene."""
import bpy,sys,json,hashlib,urllib.request,urllib.parse,os,traceback,re
from pathlib import Path
import importlib


def download(url,path,blob,size):
    if path.exists():
        data=path.read_bytes()
        if len(data)==size and hashlib.sha1(b'blob '+str(size).encode()+b'\0'+data).hexdigest()==blob:return
    request=urllib.request.Request(url,headers={'User-Agent':'Rigmodo-motion-library'})
    with urllib.request.urlopen(request,timeout=60) as response:
        data=response.read(size+1)
    if len(data)!=size or hashlib.sha1(b'blob '+str(size).encode()+b'\0'+data).hexdigest()!=blob:raise ValueError('Source asset checksum mismatch: '+path.name)
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.pending');temporary.write_bytes(data);os.replace(temporary,path)


def import_file(path,root,source,license,family,store):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    suffix=path.suffix.lower()
    if suffix=='.bvh':
        import addon_utils
        addon_utils.enable('io_anim_bvh')
        bpy.ops.import_anim.bvh(filepath=str(path),update_scene_fps=True)
    elif suffix=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path))
    elif suffix in {'.glb','.gltf'}:bpy.ops.import_scene.gltf(filepath=str(path))
    elif suffix=='.blend':
        with bpy.data.libraries.load(str(path),link=False) as (available,loaded):loaded.objects=available.objects;loaded.actions=available.actions
        for obj in loaded.objects:
            if obj and not obj.users_collection:bpy.context.scene.collection.objects.link(obj)
    else:raise ValueError('Use FBX, GLB, glTF or Blender files')
    bpy.context.view_layer.update();added=[];all_keys=[]
    rigs=[o for o in bpy.context.scene.objects if o.type=='ARMATURE'];seen=set()
    for rig in rigs:
        for action in list(bpy.data.actions):
            for slot in action.slots:
                paths=[]
                for layer in action.layers:
                    for strip in layer.strips:
                        bag=strip.channelbag(slot,ensure=False)
                        if bag:paths.extend(c.data_path for c in bag.fcurves if c.keyframe_points or c.sampled_points)
                if not any(p.startswith('pose.bones[') for p in paths):continue
                import ast
                names=[]
                for p in paths:
                    match=re.match(r'^pose\.bones\[("(?:\\.|[^"\\])*")\]',p)
                    if match:names.append(json.loads(match[1]))
                if not names or any(n not in rig.data.bones for n in names):continue
                signature=(action.session_uid,tuple((b.name,tuple(v for row in b.matrix_local for v in row)) for b in rig.data.bones))
                if signature in seen:continue
                seen.add(signature)
                ad=rig.animation_data_create();ad.action=action;ad.action_slot=slot
                data=store.capture(bpy.context,rig,action,slot)
                words=set(re.findall('[a-z]+',action.name.lower()))
                looping=bool(words&{'walk','walking','run','running','idle','crawl','flying','swim','swimming','glide','flap'}) and not bool(words&{'attack','death','die','hit','hurt'})
                loop=action.get('lc_clip_loop',looping)
                name=action.name
                if name.lower() in {'animation','take 001','take 001.001'}:name=path.stem
                key,created=store.write(root,data,name,source,license,family,bool(loop))
                all_keys.append(key)
                if created:added.append(key)
    if not rigs:raise ValueError('No armature was found in '+path.name)
    return added,all_keys


def main(folder):
    root_module=Path(__file__).resolve().parent
    sys.path.insert(0,str(root_module.parent));package=root_module.name
    store=importlib.import_module(package+'.motion_store')
    request=json.loads((folder/'request.json').read_text());root=Path(request['root']);files=[]
    if request['kind']=='downloader':
        installer=importlib.import_module(package+'.mixamo_downloader_install');installer.install(root)
        store.atomic(folder/'results.json',dict(added=[],errors=[],files=0,downloader_ready=True))
        store.atomic(folder/'status.json',dict(schema_version=1,status='complete'));return
    if request['kind']=='publish':pass
    elif request['kind']=='starter':
        manifest=json.loads((root_module/'motion-library-sources.json').read_text())
        revision=manifest['revision'];license=manifest['license']
        for item in manifest['files']:
            relative=item['path']
            if not re.fullmatch(r'static/assets/[a-z0-9-]+/animations/[a-z0-9._-]+\.glb',relative):raise ValueError('Invalid starter manifest path')
            family=relative.split('/')[2].title();path=root/'Sources'/'Mesh2Motion'/revision/family/Path(relative).name
            url='https://raw.githubusercontent.com/Mesh2Motion/mesh2motion-app/'+revision+'/'+relative
            download(url,path,item['sha'],item['size']);files.append((path,'Mesh2Motion · CC0',license,family))
        store.atomic(root/'Sources'/'Mesh2Motion'/'provenance.json',manifest)
        (root/'Sources'/'Mesh2Motion'/'LICENSE-CC0.txt').write_text(manifest['license_text'])
    elif request['kind']=='import':
        for name in request['files']:
            path=Path(name).resolve()
            if not path.is_file() or path.suffix.lower() not in {'.fbx','.glb','.gltf','.blend','.bvh'}:raise ValueError('Unsupported motion file: '+str(path))
            files.append((path,request.get('source','Local import'),request.get('license','User-provided'),''))
    else:raise ValueError('Unknown motion-library job')
    added=[];errors=[];skipped=[]
    cache_path=root/'import-cache.json';cache=json.loads(cache_path.read_text()) if cache_path.is_file() else {}
    present={c['id'] for c in store.catalog(root)['clips']}
    for i,(path,source,license,family) in enumerate(files):
        store.atomic(folder/'progress.json',dict(done=i,total=len(files),file=path.name))
        try:
            if path.stat().st_size>500*1024*1024:raise ValueError('Source file exceeds 500 MB')
            with path.open('rb') as stream:fingerprint=hashlib.file_digest(stream,'sha256').hexdigest()
            if fingerprint in cache and set(cache[fingerprint])<=present:
                skipped.append(dict(file=str(path),reason='Already imported'));continue
            created,keys=import_file(path,root,source,license,family,store);added.extend(created);present.update(keys)
            with store.locked(root):
                cache=json.loads(cache_path.read_text()) if cache_path.is_file() else {}
                cache[fingerprint]=keys;store.atomic(cache_path,cache)
        except Exception as exc:
            if 'span at least two distinct frames' in str(exc):skipped.append(dict(file=str(path),reason='Static pose without an animation range'))
            else:errors.append(dict(file=str(path),error=str(exc)));traceback.print_exc()
        print('LIBRARY_FILE',i+1,len(files),path.name,flush=True)
    assets=importlib.import_module(package+'.motion_assets')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    assets.publish_all(root,lambda i,n,name:store.atomic(folder/'progress.json',dict(done=i,total=n,file='Publishing '+name)))
    store.atomic(folder/'results.json',dict(added=added,errors=errors,skipped=skipped,files=len(files)))
    if errors and not added:raise ValueError('No motions imported; '+errors[0]['error'])
    store.atomic(folder/'status.json',dict(schema_version=1,status='complete'))
    print('LIBRARY_IMPORT_COMPLETE',len(added),'motions;',len(errors),'errors',flush=True)


if __name__=='__main__':
    folder=Path(sys.argv[sys.argv.index('--')+1])
    try:main(folder)
    except Exception as exc:
        traceback.print_exc();(folder/'status.json').write_text(json.dumps(dict(schema_version=1,status='failed',error=str(exc))))
        raise
