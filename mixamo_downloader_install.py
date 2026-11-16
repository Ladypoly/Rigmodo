# SPDX-License-Identifier: GPL-3.0-or-later
"""Install a pinned MIT batch-downloader separately from Blender and the asset catalog."""
import hashlib,io,json,os,shutil,subprocess,sys,urllib.request,zipfile
from pathlib import Path

REVISION='86ecff45f9a4d78cbea8df10d22f0613ed078b57'
ARCHIVE_SHA256='17ef7e89bff7fc29025ed875ef546fa26bef9ad8784121b15d5b643b6fb86247'
ELECTRON='45.3.3'
PATCH_VERSION=2


def install(library):
    library=Path(library).resolve();root=library/'Tools'/'MixamoDownloader';root.mkdir(parents=True,exist_ok=True)
    npm=shutil.which('npm.cmd' if os.name=='nt' else 'npm')
    if not npm:raise ValueError('Install Node.js 22 or newer before setting up the optional downloader')
    ready=root/'rigmodo-source.json'
    if ready.is_file() and json.loads(ready.read_text(encoding='utf-8')).get('electron')==ELECTRON and json.loads(ready.read_text(encoding='utf-8')).get('patch')==PATCH_VERSION and (root/'node_modules/electron/dist/electron.exe').is_file():return root
    with urllib.request.urlopen('https://codeload.github.com/underfusion/mixamo-downloader/zip/'+REVISION,timeout=60) as response:data=response.read(3*1024*1024)
    if hashlib.sha256(data).hexdigest()!=ARCHIVE_SHA256:raise ValueError('Downloader source archive checksum mismatch')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            parts=Path(info.filename).parts[1:]
            if not parts:continue
            dest=root.joinpath(*parts).resolve()
            if not dest.is_relative_to(root):raise ValueError('Unsafe downloader archive path')
            if info.is_dir():dest.mkdir(parents=True,exist_ok=True)
            else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(archive.read(info))
    output=library/'Downloads'/'Mixamo';output.mkdir(parents=True,exist_ok=True)
    package=json.loads((root/'package.json').read_text(encoding='utf-8'));package['dependencies']['electron']=ELECTRON
    (root/'package.json').write_text(json.dumps(package,indent=2))
    p=root/'src/app.html';text=p.read_text(encoding='utf-8')
    text=text.replace('value="Animations"', 'value="'+str(output).replace('&','&amp;').replace('"','&quot;')+'"')
    text=text.replace('    async function checkForToken() {\n      try {','    async function checkForToken() {\n      try {\n        if (new URL(webview.getURL()).hostname !== "www.mixamo.com") return;')
    p.write_text(text,encoding='utf-8')
    p=root/'src/downloader.js';text=p.read_text(encoding='utf-8')
    text=text.replace('const DELAY_BETWEEN_MS  = 200;','const DELAY_BETWEEN_MS  = 1000;')
    text=text.replace('  migrateToRigFolders(outputDir, onProgress);','  // Rigmodo keeps existing user folders unchanged.')
    text=text.replace('  autoReorganize(outputDir, packMap, onProgress, rigDir);','  // Rigmodo does not reorganize existing downloads.')
    text=text.replace('if (fs.existsSync(flatPath)) {','if (false && fs.existsSync(flatPath)) {')
    p.write_text(text,encoding='utf-8')
    p=root/'main.js';text=p.read_text(encoding='utf-8')
    text=text.replace("title: 'Mixamo Downloader'", "title: 'Rigmodo · Mixamo Batch Downloader'")
    text=text.replace('    width: 1300,','    show: !process.env.RIGMODO_SMOKE_TEST,\n    width: 1300,')
    text=text.replace("defaultPath: path.join(__dirname, 'Animations')","defaultPath: "+json.dumps(str(output)))
    text=text.replace("  mainWindow.loadFile('src/app.html');", "  mainWindow.webContents.on('will-navigate', event => event.preventDefault());\n  mainWindow.loadFile('src/app.html');")
    text=text.replace("return { action: 'allow' };", "return { action: 'allow', overrideBrowserWindowOptions: { webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true } } };")
    # A no-login smoke check exercises the actual renderer and exits without downloading assets.
    text=text.replace("  mainWindow.loadFile('src/app.html');", "  if (process.env.RIGMODO_SMOKE_TEST) {\n    mainWindow.hide();\n    mainWindow.webContents.once('did-finish-load', async () => {\n      try {\n        const state = await mainWindow.webContents.executeJavaScript(`({output: document.getElementById('outputDir').value, disabled: document.getElementById('btnDownload').disabled})`);\n        require('fs').writeFileSync(process.env.RIGMODO_SMOKE_TEST, JSON.stringify(state));\n        app.exit(0);\n      } catch(error) { console.error(error.message); app.exit(1); }\n    });\n  }\n  mainWindow.loadFile('src/app.html');")
    p.write_text(text,encoding='utf-8')
    (root/'Start.cmd').write_text('@echo off\nset ELECTRON_RUN_AS_NODE=\ncd /d "%~dp0"\ncall "node_modules\\.bin\\electron.cmd" .\n')
    (root/'RIGMODO-README.txt').write_text('Optional unofficial Mixamo batch downloader\n\nOriginal MIT source: https://github.com/underfusion/mixamo-downloader\n'+
        'Log in directly in the downloader, select your character and a matching rig variant, then download.\n'+
        'Files go to '+str(output)+'. Use Import Folder in Rigmodo afterward.\n'+
        'Source and MIT license are retained here. No Adobe credentials are copied into Rigmodo or Git.\n'+
        'Adobe does not endorse this tool. Its current terms restrict scraping and unauthorized interfaces; account access may change.\n')
    env=os.environ.copy();env.pop('ELECTRON_RUN_AS_NODE',None)
    npm_cli=Path(npm).parent/'node_modules/npm/bin/npm-cli.js'
    command=[shutil.which('node'),str(npm_cli)] if os.name=='nt' else [npm]
    subprocess.run([*command,'install','--no-fund','--no-audit'],cwd=root,env=env,check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    executable=root/'node_modules/electron/dist/electron.exe'
    if not executable.is_file():
        subprocess.run([shutil.which('node'),str(root/'node_modules/electron/install.js')],cwd=root,env=env,check=True,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    if not executable.is_file():raise ValueError('Electron runtime did not install; inspect the setup log')
    ready.write_text(json.dumps(dict(repository='https://github.com/underfusion/mixamo-downloader',revision=REVISION,sha256=ARCHIVE_SHA256,electron=ELECTRON,patch=PATCH_VERSION),indent=2))
    print('MIXAMO_DOWNLOADER_READY',root,flush=True);return root


if __name__=='__main__':install(sys.argv[1] if len(sys.argv)>1 else 'R:/AI/MotionLibrary/Rigmodo')
