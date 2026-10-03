# SPDX-License-Identifier: GPL-3.0-or-later
"""Cancellable offline native archive / online checkpoint setup outside Blender."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import bpy
from . import skinning,process_tree

def start(python,archive):
    if skinning._jobs:raise ValueError('Finish or cancel the current local job before provider setup')
    python=Path(python).resolve();archive=Path(archive).resolve()
    if not python.is_file() or not archive.is_file():raise ValueError('Choose Python 3.11 and this release’s Windows provider archive')
    directory=skinning.provider_cache().parent.parent/'jobs';directory.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='setup-',dir=directory)).resolve();log=(folder/'worker.log').open('wb')
    process=None;job=None
    try:
        process=subprocess.Popen([str(python),'-I',str(Path(__file__).with_name('provider_install.py')),'--archive',str(archive)],
            cwd=python.parent,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
        job=process_tree.WindowsJob(process)
        skinning._jobs[str(folder)]=dict(process=process,log=log,job_object=job,started=time.monotonic(),phase='Installing local providers')
        skinning._state(folder,'running',pid=process.pid)
    except Exception:
        if job:job.close()
        if process:
            process.terminate();process.wait(timeout=3)
        log.close();raise
    return folder

def inventory(settings):
    from . import motion_jobs,placement
    joint_cache=Path(bpy.path.abspath(settings.placement_python)).parent.parent.parent
    checks={
        'Joint placement':Path(bpy.path.abspath(settings.placement_python)).is_file() and all((joint_cache/'models'/name).is_file() for name in ('joints.pth','joints_coarse.pth')) and all((joint_cache/'source'/name).is_file() for name in placement.SOURCE_HASHES),
        'AI skinning':Path(settings.skin_executable).is_file() and all((Path(settings.skin_models)/name).is_file() for name in skinning.MODEL_HASHES),
        'Generated motion':(Path(settings.motion_provider)/'bin/kmd-generate.exe').is_file() and all((Path(settings.motion_provider)/'weights'/name).is_file() for name in motion_jobs.FILES)}
    return checks
