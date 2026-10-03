# SPDX-License-Identifier: GPL-3.0-or-later
"""Own installer subprocess descendants through a Windows Job Object."""
import ctypes
from ctypes import wintypes
import os

class WindowsJob:
    def __init__(self,process):
        if os.name!='nt':raise ValueError('Provider installation currently targets Windows')
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);self.kernel=kernel
        kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,wintypes.LPCWSTR];kernel.CreateJobObjectW.restype=wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD];kernel.SetInformationJobObject.restype=wintypes.BOOL
        kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE];kernel.AssignProcessToJobObject.restype=wintypes.BOOL
        kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
        class Basic(ctypes.Structure):
            _fields_=[('per_process_time',ctypes.c_int64),('per_job_time',ctypes.c_int64),('flags',wintypes.DWORD),('minimum_working_set',ctypes.c_size_t),('maximum_working_set',ctypes.c_size_t),('active_processes',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):_fields_=[(name,ctypes.c_uint64) for name in ('read_operations','write_operations','other_operations','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):_fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process_memory',ctypes.c_size_t),('peak_job_memory',ctypes.c_size_t)]
        self.handle=kernel.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limit=Extended();limit.basic.flags=0x2000 # KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle,9,ctypes.byref(limit),ctypes.sizeof(limit)) or not kernel.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle))):
            error=ctypes.get_last_error();self.close();raise ctypes.WinError(error)
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None
