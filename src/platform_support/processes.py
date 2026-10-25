"""Owned process handles and platform memory/listener inspection.

Windows children enter a kill-on-close Job Object while still suspended. No
stored PID is ever used to terminate a process, including after a crash.
"""
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import time


def peak_rss_bytes():
    if os.name != 'nt':
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024)
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    counters = Counters(); counters.cb = ctypes.sizeof(counters)
    process = ctypes.windll.kernel32.GetCurrentProcess
    process.restype = wintypes.HANDLE
    get = ctypes.windll.psapi.GetProcessMemoryInfo
    get.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    if not get(process(), ctypes.byref(counters), counters.cb):
        raise ctypes.WinError()
    return counters.PeakWorkingSetSize


def pnpm_argv(executable, node):
    """A Windows .cmd wrapper is never interpreted by cmd.exe.

    The reviewed npm global layout places pnpm.cjs next to that wrapper. Custom
    shims must instead supply the actual .cjs path; arbitrary wrapper parsing is
    deliberately unsupported.
    """
    if os.name != 'nt':
        return [str(executable)]
    path = Path(executable).absolute()
    if path.suffix.lower() == '.exe':
        return [str(path)]
    if path.suffix.lower() in {'.cjs', '.js'}:
        script = path
    elif path.suffix.lower() in {'.cmd', '.bat'}:
        script = path.parent / 'node_modules/pnpm/bin/pnpm.cjs'
    else:
        raise ValueError('On Windows supply pnpm.cmd from npm, pnpm.exe, or the explicit pnpm.cjs entry point.')
    if not script.is_file() or script.is_symlink():
        raise ValueError('pnpm JavaScript entry point was not found. Install pinned pnpm with npm or supply its pnpm.cjs file; no command wrapper was executed.')
    return [str(node), str(script)]


class OwnedWindowsProcess:
    def __init__(self, process, pid, command):
        self.handle, self.pid, self.args = process, pid, command

    def poll(self):
        from .windows import require_runtime
        _, _, con, _, _, event, process, *_ = require_runtime()
        if event.WaitForSingleObject(self.handle, 0) == con.WAIT_TIMEOUT:
            return None
        return process.GetExitCodeProcess(self.handle)

    def wait(self, timeout=None):
        from .windows import require_runtime
        _, _, con, _, _, event, process, *_ = require_runtime()
        value = event.WaitForSingleObject(self.handle, con.INFINITE if timeout is None else max(0, int(timeout * 1000)))
        if value == con.WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired(self.args, timeout)
        return process.GetExitCodeProcess(self.handle)

    def close(self):
        if self.handle is not None:
            self.handle.Close(); self.handle = None

    def request_stop(self):
        """CTRL_BREAK targets only the active group created with this handle.

        Its kernel process handle remains open throughout; the PID/group cannot
        be recycled into an unrelated process while this handle owns it. No
        stored PID, process discovery or port lookup participates in stopping.
        A missing shared console is a reported failure, never a broad signal.
        """
        from .windows import require_runtime
        if self.poll() is not None: return False
        _, api, con, *_ = require_runtime()
        try:
            api.GenerateConsoleCtrlEvent(con.CTRL_BREAK_EVENT, self.pid)
            return True
        except OSError:
            return False


class WindowsJob:
    def __init__(self):
        from .windows import require_runtime
        _, _, _, _, _, _, _, job, _ = require_runtime()
        self.handle = job.CreateJobObject(None, None)
        limits = job.QueryInformationJobObject(self.handle, job.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags'] |= job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        job.SetInformationJobObject(self.handle, job.JobObjectExtendedLimitInformation, limits)
        self.children = []

    def spawn(self, command, cwd, env):
        from .windows import require_runtime
        _, _, con, _, _, _, process, job, _ = require_runtime()
        if self.handle is None:
            raise RuntimeError('The owned Windows job is already closed.')
        flags = con.CREATE_SUSPENDED | con.CREATE_UNICODE_ENVIRONMENT | con.CREATE_NEW_PROCESS_GROUP
        handle, thread, pid, _ = process.CreateProcess(None, subprocess.list2cmdline([str(v) for v in command]),
            None, None, False, flags, dict(env), str(cwd), process.STARTUPINFO())
        try:
            # No breakaway fallback: assignment failure terminates only this
            # newly created suspended process, through its verified handle.
            job.AssignProcessToJobObject(self.handle, handle)
            child = OwnedWindowsProcess(handle, pid, command)
            process.ResumeThread(thread)
            self.children.append(child)
            return child
        except BaseException:
            process.TerminateProcess(handle, 1)
            handle.Close()
            raise
        finally:
            thread.Close()

    def close(self, shutdown_seconds=12):
        if self.handle is None:
            return {'already_closed': True}
        requested = sum(child.request_stop() for child in self.children)
        deadline = time.monotonic() + shutdown_seconds
        for child in self.children:
            try: child.wait(timeout=max(.001, deadline - time.monotonic()))
            except subprocess.TimeoutExpired: pass
        forced = sum(child.poll() is None for child in self.children)
        if self.handle is not None:
            from .windows import require_runtime
            # Kill only the processes assigned to our live kernel job handle.
            require_runtime()[7].TerminateJobObject(self.handle, 0)
            self.handle.Close(); self.handle = None
        exit_codes = []
        for child in self.children:
            try: child.wait(timeout=5)
            finally:
                exit_codes.append(child.poll()); child.close()
        self.children = []
        return {'ctrl_break_sent': requested, 'forced_primaries': forced,
            'exit_codes': exit_codes, 'owned_job_closed': True}


def windows_listener_owned(child, port):
    """The active owned process handle must own this exact IPv4 listener."""
    if not isinstance(child, OwnedWindowsProcess) or child.poll() is not None:
        return False
    import ctypes
    from ctypes import wintypes
    class Row(ctypes.Structure):
        _fields_ = [(name, wintypes.DWORD) for name in ('state', 'local', 'port', 'remote', 'remote_port', 'pid')]
    api = ctypes.windll.iphlpapi.GetExtendedTcpTable
    api.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG, ctypes.c_int, wintypes.ULONG]
    size = wintypes.DWORD()
    result = api(None, ctypes.byref(size), False, socket.AF_INET, 5, 0)  # TCP_TABLE_OWNER_PID_ALL
    if result not in {0, 122} or size.value > 16 * 1024 * 1024:
        return False
    buffer = ctypes.create_string_buffer(size.value)
    if api(buffer, ctypes.byref(size), False, socket.AF_INET, 5, 0):
        return False
    count = wintypes.DWORD.from_buffer(buffer).value
    if count * ctypes.sizeof(Row) + ctypes.sizeof(wintypes.DWORD) > size.value:
        return False
    rows = (Row * count).from_buffer(buffer, ctypes.sizeof(wintypes.DWORD))
    found = any(row.pid == child.pid and row.state == 2 and struct.pack('=I', row.local) == socket.inet_aton('127.0.0.1')
        and socket.ntohs(row.port & 0xffff) == port for row in rows)
    return found and child.poll() is None
