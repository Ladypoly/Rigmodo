# SPDX-License-Identifier: GPL-3.0-or-later
"""Stream provider hash checks outside Blender's main thread."""
import hashlib
import json
from pathlib import Path
import sys

def native_files(directory,binaries,provider):
    directory=Path(directory).resolve()
    release=json.loads(Path(__file__).with_name('provider-release-lock.json').read_text())['files']
    prefix=provider+'/bin/'
    pinned_binaries={name[len(prefix):]:digest for name,digest in release.items() if name.startswith(prefix) and Path(name).suffix.lower() in {'.dll','.exe'}}
    if binaries!=pinned_binaries:raise ValueError('Native binary inventory differs from this extension release')
    files=[]
    for name,expected in binaries.items():
        path=directory/name
        if path.parent!=directory or path.suffix.lower() not in {'.dll','.exe'}:
            raise ValueError('Invalid native binary manifest')
        key=prefix+name
        pinned=release.get(key)
        if not pinned or pinned!=expected:
            raise ValueError('Native binary differs from the packaged release: '+name)
        files.append(dict(path=str(path),sha256=expected))
    required='skintokens-cli.exe' if provider.startswith('skin-') else 'kmd-generate.exe'
    if required not in binaries:raise ValueError('Native executable is missing from the manifest')
    return files

def accept(folder,cache):
    folder=Path(folder)
    expected=json.loads((folder/'verify.json').read_text())['files']
    result=json.loads((folder/'verified.json').read_text())
    if len(result)!=len(expected):raise ValueError('Incomplete provider verification')
    for actual,wanted in zip(result,expected):
        path=Path(wanted['path']);stamp=(str(path),path.stat().st_size,path.stat().st_mtime_ns)
        if actual['path']!=str(path) or actual['sha256']!=wanted['sha256'] or stamp[1:]!=(actual['size'],actual['modified']):
            raise ValueError('Provider changed during verification')
        cache[stamp]=actual['sha256']

def run(folder):
    folder=Path(folder).resolve()
    request=json.loads((folder/'verify.json').read_text())
    verified=[]
    for entry in request['files']:
        path=Path(entry['path']); before=path.stat()
        with path.open('rb') as stream:actual=hashlib.file_digest(stream,'sha256').hexdigest()
        after=path.stat()
        if actual!=entry['sha256'] or before.st_size!=after.st_size or before.st_mtime_ns!=after.st_mtime_ns:
            raise ValueError('Provider file failed verification: '+path.name)
        verified.append(dict(path=str(path),sha256=actual,size=after.st_size,modified=after.st_mtime_ns))
    (folder/'verified.json').write_text(json.dumps(verified))

if __name__=='__main__':run(sys.argv[1])
