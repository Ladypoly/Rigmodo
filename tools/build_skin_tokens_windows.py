"""Build the pinned local provider without editing Blender or a user checkout.

Run with --prepare to download the pinned source/dependencies and F16 weights.
Requires Git, CMake, Conda and VS 2022 Build Tools with ClangCL already installed.
The build directory must be short because nested Visual Studio projects hit MAX_PATH.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request

root = Path(__file__).resolve().parents[1]
constants = {}
for node in ast.parse((root / 'skinning.py').read_text()).body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
        if node.targets[0].id in {'PROVIDER_REVISION', 'MODEL_REVISION', 'MODEL_HASHES'}:
            constants[node.targets[0].id] = ast.literal_eval(node.value)
pins = {
    'source': ('https://github.com/localai-org/skin-tokens.cpp.git', constants['PROVIDER_REVISION']),
    'json': ('https://github.com/nlohmann/json.git', '9cca280a4d0ccf0c08f47a99aa71d1b0e52f8d03'),
    'vulkan-headers': ('https://github.com/KhronosGroup/Vulkan-Headers.git', 'd1cd37e925510a167d4abef39340dbdea47d8989'),
    'spirv-headers': ('https://github.com/KhronosGroup/SPIRV-Headers.git', '01e0577914a75a2569c846778c2f93aa8e6feddd'),
}
parser = argparse.ArgumentParser()
parser.add_argument('--cache', type=Path, default=Path(os.environ['LOCALAPPDATA']) / 'LocalCharacter/providers/skin-tokens-46dbfec')
parser.add_argument('--build-dir', type=Path, default=Path(r'C:\LCBuild\st46vk'))
parser.add_argument('--vs', type=Path, default=Path(r'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools'))
parser.add_argument('--prepare', action='store_true')
args = parser.parse_args()
cache, build = args.cache.resolve(), args.build_dir.resolve()
if os.name != 'nt': raise SystemExit('This helper targets Windows only')
if len(str(build)) > 45: raise SystemExit('Choose a build directory shorter than 45 characters')
cache.mkdir(parents=True, exist_ok=True)

def run(command, **kwargs):
    print('Running:', command[0], command[1], flush=True)
    return subprocess.run([str(v) for v in command], check=True, **kwargs)

def revision(folder):
    return subprocess.check_output(['git', '-C', str(folder), 'rev-parse', 'HEAD'], text=True).strip()

for name, (url, pin) in pins.items():
    folder = cache / name
    if not folder.exists() and args.prepare:
        run(['git', 'clone', '--no-checkout', url, folder])
        run(['git', '-C', folder, 'checkout', '--detach', pin])
    if not folder.is_dir() or revision(folder) != pin:
        raise SystemExit(f'{name}: missing or mismatched pinned source; use --prepare for a fresh cache')
    if subprocess.check_output(['git', '-C', str(folder), 'status', '--porcelain'], text=True).strip():
        raise SystemExit(f'{name}: source has local modifications; choose a separate clean cache')
if args.prepare: run(['git', '-C', cache / 'source', 'submodule', 'update', '--init'])
ggml_pin = '8c63e70982c95ceb862e3a1073a2c1beef75d60a'
if revision(cache / 'source/ggml') != ggml_pin: raise SystemExit('GGML revision differs from the source lock')

toolset = sorted((args.vs / 'VC/Tools/MSVC').glob('*'), key=lambda p: tuple(map(int, p.name.split('.'))))[-1]
host_tools = toolset / 'bin/Hostx64/x64'
if not (args.vs / 'VC/Tools/Llvm/x64/bin/clang-cl.exe').is_file():
    raise SystemExit('VS ClangCL is required for the NumPy PCG64 uint128 sampler')
if args.prepare:
    for name, options in [('json', ['-DJSON_BuildTests=OFF']), ('spirv-headers', [])]:
        run(['cmake', '-S', cache / name, '-B', cache / (name + '-build'), '-G', 'Visual Studio 17 2022', '-A', 'x64', *options,
             '-DCMAKE_INSTALL_PREFIX=' + str(cache / (('json' if name == 'json' else 'spirv') + '-install'))])
        run(['cmake', '--install', cache / (name + '-build'), '--config', 'Release'])
    if not (cache / 'shader-tools/Library/bin/glslc.exe').is_file():
        conda = shutil.which('conda.exe') or str(Path(os.environ['USERPROFILE']) / 'miniconda3/Scripts/conda.exe')
        run([conda, 'create', '-y', '--prefix', cache / 'shader-tools', '--override-channels', '-c', 'conda-forge',
             'shaderc=2026.4=hef10606_0', 'glslang=16.6.0', 'spirv-tools=2026.3'])
    # Use the system Vulkan loader; create its MSVC import library locally.
    loader = Path(os.environ['WINDIR']) / 'System32/vulkan-1.dll'
    exports = subprocess.check_output([str(host_tools / 'dumpbin.exe'), '/exports', str(loader)], text=True)
    names = re.findall(r'^\s+\d+\s+[0-9A-F]+\s+[0-9A-F]+\s+(vk\w+)', exports, re.M)
    if len(names) < 100: raise SystemExit('Could not inspect the installed Vulkan loader')
    imports = cache / 'vulkan-import'; imports.mkdir(exist_ok=True)
    (imports / 'vulkan.def').write_text('LIBRARY vulkan-1.dll\nEXPORTS\n' + '\n'.join(names) + '\n')
    run([host_tools / 'lib.exe', '/def:' + str(imports / 'vulkan.def'), '/machine:x64', '/out:' + str(imports / 'vulkan-1.lib')])
    models = cache / 'models'; (models / 'F16').mkdir(parents=True, exist_ok=True)
    for name, expected in constants['MODEL_HASHES'].items():
        destination = models / 'F16' / name
        if not destination.exists():
            url = f"https://huggingface.co/LocalAI-io/SkinTokens-GGUF/resolve/{constants['MODEL_REVISION']}/F16/{name}"
            temporary = destination.with_suffix('.download')
            urllib.request.urlretrieve(url, temporary)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != expected: raise SystemExit('Model download hash mismatch')
            os.replace(temporary, destination)
    for name in ('LICENSE', 'README.md', 'MANIFEST.json', 'SHA256SUMS'):
        if not (models / name).exists():
            urllib.request.urlretrieve(f"https://huggingface.co/LocalAI-io/SkinTokens-GGUF/resolve/{constants['MODEL_REVISION']}/{name}", models / name)

for name, expected in constants['MODEL_HASHES'].items():
    with (cache / 'models/F16' / name).open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected: raise SystemExit(f'{name}: F16 hash mismatch')
configuration = ['cmake', '-S', cache / 'source', '-B', build, '-G', 'Visual Studio 17 2022', '-A', 'x64', '-T', 'ClangCL',
    '-DSKINTOKENS_ENABLE_VULKAN=ON', '-DSKINTOKENS_BUILD_TESTS=ON', '-DSKINTOKENS_CPU_ALL_VARIANTS=OFF',
    '-DCMAKE_C_FLAGS=-D_CRT_SECURE_NO_WARNINGS',
    '-DCMAKE_CXX_FLAGS=-D_CRT_SECURE_NO_WARNINGS /EHsc -I' + str(cache / 'spirv-install/include'),
    '-Dnlohmann_json_DIR=' + str(cache / 'json-install/share/cmake/nlohmann_json'),
    '-DSPIRV-Headers_DIR=' + str(cache / 'spirv-install/share/cmake/SPIRV-Headers'),
    '-DVulkan_INCLUDE_DIR=' + str(cache / 'vulkan-headers/include'),
    '-DVulkan_LIBRARY=' + str(cache / 'vulkan-import/vulkan-1.lib'),
    '-DVulkan_GLSLC_EXECUTABLE=' + str(cache / 'shader-tools/Library/bin/glslc.exe')]
with (cache / 'reproducible-build.log').open('w') as log:
    run(configuration, stdout=log, stderr=subprocess.STDOUT)
    run(['cmake', '--build', build, '--config', 'Release', '--target', 'skintokens-cli', 'ggml-vulkan',
         'skintokens-api-test', 'skintokens-c-api-test', 'skintokens-binding-test', 'skintokens-tokenizer-test', '--parallel', '8'],
        stdout=log, stderr=subprocess.STDOUT)
binary = cache / 'bin'; binary.mkdir(exist_ok=True)
for file in (build / 'bin/Release').glob('*.dll'): shutil.copy2(file, binary / file.name)
shutil.copy2(build / 'Release/skintokens.dll', binary / 'skintokens.dll')
shutil.copy2(build / 'bin/Release/skintokens-cli.exe', binary / 'skintokens-cli.exe')
environment = os.environ.copy(); environment['PATH'] = str(binary) + os.pathsep + environment['PATH']
run(['ctest', '--test-dir', build, '-C', 'Release', '--output-on-failure'], env=environment)
run([binary / 'skintokens-cli.exe', 'inspect', cache / 'models/F16', '--device', 'vulkan'])
for name in ('LICENSE', 'NOTICE'): shutil.copy2(cache / 'source' / name, binary / name)
manifest = {'provider_revision': constants['PROVIDER_REVISION'], 'ggml_revision': ggml_pin,
            'model_revision': constants['MODEL_REVISION'], 'model_hashes': constants['MODEL_HASHES'],
            'source_pins': pins, 'configuration': list(map(str, configuration)),
            'binaries': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in binary.iterdir() if p.suffix in {'.dll', '.exe'}}}
(cache / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print('LOCAL_CHARACTER_PROVIDER_BUILT', binary)
