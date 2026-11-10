"""Terminate only a job's owned worker tree when cancellation/timeout closes it."""
import os,signal,ctypes

class ComputeProcessTree:
    def __init__(self,process,memory_mb=None):
        self.process=process;self.handle=None
        if os.name=='nt':
            from ctypes import wintypes as w
            class BASIC(ctypes.Structure):
                _fields_=[('PerProcessUserTimeLimit',ctypes.c_int64),('PerJobUserTimeLimit',ctypes.c_int64),('LimitFlags',w.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',w.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',w.DWORD),('SchedulingClass',w.DWORD)]
            class IO(ctypes.Structure):_fields_=[(n,ctypes.c_uint64) for n in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
            class EXT(ctypes.Structure):_fields_=[('BasicLimitInformation',BASIC),('IoInfo',IO),('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
            k=ctypes.WinDLL('kernel32',use_last_error=True);self.kernel=k
            k.CreateJobObjectW.restype=w.HANDLE;k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR]
            k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
            k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];k.CloseHandle.argtypes=[w.HANDLE]
            self.handle=k.CreateJobObjectW(None,None);info=EXT();info.BasicLimitInformation.LimitFlags=0x2000
            if memory_mb:
                info.BasicLimitInformation.LimitFlags|=0x200
                info.JobMemoryLimit=int(memory_mb)*1024*1024
            if not self.handle or not k.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not k.AssignProcessToJobObject(self.handle,int(process._handle)):
                process.kill()
                if self.handle:k.CloseHandle(self.handle);self.handle=None
                raise OSError('Unable to isolate local compute process tree')
    def close(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle=None
        elif os.name!='nt' and self.process.poll() is None:
            # The supervisor starts this worker in its own process session.
            os.killpg(self.process.pid,signal.SIGKILL)
