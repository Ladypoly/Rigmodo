"""Measure owned process-tree RAM and global GPU use without claiming GPU attribution."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil

args=sys.argv[1:];destination=Path(args.pop(0));destination.parent.mkdir(parents=True,exist_ok=True)
def gpu():
    result=subprocess.run(['nvidia-smi','--query-gpu=memory.used,memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5)
    row=next(csv.reader(result.stdout.splitlines()));return [int(value.strip()) for value in row]
baseline,total=gpu();process=subprocess.Popen(args);samples=[]
while process.poll() is None:
    used,_=gpu();rss=0;names=[]
    try:
        parent=psutil.Process(process.pid)
        for child in [parent,*parent.children(recursive=True)]:
            try:rss+=child.memory_info().rss;names.append(child.name())
            except (psutil.NoSuchProcess,psutil.AccessDenied):pass
    except psutil.NoSuchProcess:pass
    samples.append(dict(time=time.time(),global_gpu_mib=used,process_tree_rss_bytes=rss,process_names=names));time.sleep(.25)
peak=max((sample['global_gpu_mib'] for sample in samples),default=baseline)
report=dict(exit_code=process.returncode,global_gpu_baseline_mib=baseline,global_gpu_peak_mib=peak,total_gpu_mib=total,
            peak_minus_baseline_mib=peak-baseline,maximum_process_tree_rss_bytes=max((s['process_tree_rss_bytes'] for s in samples),default=0),
            gpu_attribution='Global device use includes desktop and other applications; difference is an estimate, not an owned-process GPU allocation measurement',samples=samples)
destination.write_text(json.dumps(report,indent=2));print('RESOURCE_PROFILE',json.dumps({key:value for key,value in report.items() if key!='samples'}),flush=True)
sys.exit(process.returncode)
