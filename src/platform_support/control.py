"""Current-SID-only, local Windows named-pipe control with bounded I/O.

This is only launcher status/stop IPC. The existing random token and instance
identity are still checked by the controller; it is not a research endpoint.
"""
import hashlib
import json
import os
from threading import Thread
import time
from .windows import native_errors


def pipe_name(state):
    from .windows import current_sid_text
    identity = current_sid_text() + '\0' + os.path.normcase(str(state))
    return '\\\\.\\pipe\\litrev-preview-' + hashlib.sha256(identity.encode()).hexdigest()


@native_errors
def _overlapped(handle, invoke, timeout):
    from .windows import require_runtime
    types, _, con, file, _, event, *_ = require_runtime()
    value = types.OVERLAPPED(); value.hEvent = event.CreateEvent(None, True, False, None)
    try:
        try: invoke(value)
        except types.error as error:
            if getattr(error, 'winerror', None) == 535:  # client already connected
                return 0
            if getattr(error, 'winerror', None) != 997:  # ERROR_IO_PENDING
                raise
        if event.WaitForSingleObject(value.hEvent, max(1, int(timeout * 1000))) != con.WAIT_OBJECT_0:
            file.CancelIoEx(handle, value)
            # Keep OVERLAPPED and its event alive until cancellation completes.
            file.GetOverlappedResult(handle, value, True)
            raise TimeoutError('Local control timed out.')
        return file.GetOverlappedResult(handle, value, False)
    finally:
        value.hEvent.Close()


class PipeConnection:
    def __init__(self, handle, timeout=2):
        self.handle, self.timeout = handle, timeout

    def recv(self, size):
        from .windows import require_runtime
        file = require_runtime()[3]
        buffer = file.AllocateReadBuffer(min(size, 4097))
        count = _overlapped(self.handle, lambda value: file.ReadFile(self.handle, buffer, value), self.timeout)
        return bytes(buffer[:count])

    def sendall(self, data):
        from .windows import require_runtime
        if len(data) > 4096: raise ValueError('Local control message exceeds its bound.')
        file = require_runtime()[3]
        count = _overlapped(self.handle, lambda value: file.WriteFile(self.handle, data, value), self.timeout)
        if count != len(data): raise OSError('Incomplete local control message.')

    def close(self):
        if self.handle is not None: self.handle.Close(); self.handle = None


@native_errors
def connect(state, expected_pid):
    from .windows import require_runtime
    _, _, con, file, _, _, _, _, pipe = require_runtime()
    name = pipe_name(state)
    pipe.WaitNamedPipe(name, 2000)
    handle = file.CreateFile(name, con.GENERIC_READ | con.GENERIC_WRITE, 0, None,
        con.OPEN_EXISTING, con.FILE_FLAG_OVERLAPPED, None)
    try:
        # PID is used only for native endpoint identity, never for signalling.
        import ctypes
        from ctypes import wintypes
        pid = wintypes.ULONG()
        call = ctypes.windll.kernel32.GetNamedPipeServerProcessId
        call.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
        if not call(int(handle), ctypes.byref(pid)) or pid.value != expected_pid:
            raise ValueError('The local control server identity did not match.')
        return PipeConnection(handle)
    except BaseException:
        handle.Close(); raise


class PipeServer:
    def __init__(self, state, stop, handler):
        self.state, self.stop, self.handler = state, stop, handler
        self.handle = self.thread = None

    @native_errors
    def start(self):
        from .windows import require_runtime, security_attributes
        _, _, con, _, _, _, _, _, pipe = require_runtime()
        # Default named-pipe ACLs permit Everyone/anonymous reads. Always use
        # our explicit protected user/SYSTEM descriptor and reject remote peers.
        self.handle = pipe.CreateNamedPipe(pipe_name(self.state),
            pipe.PIPE_ACCESS_DUPLEX | con.FILE_FLAG_OVERLAPPED | 0x00080000,
            pipe.PIPE_TYPE_BYTE | pipe.PIPE_READMODE_BYTE | pipe.PIPE_WAIT | 0x8,
            1, 4096, 4096, 2000, security_attributes())
        self.thread = Thread(target=self.serve, daemon=True); self.thread.start()

    def serve(self):
        from .windows import require_runtime
        types, *_, pipe = require_runtime()
        try:
            while not self.stop.is_set():
                try:
                    _overlapped(self.handle, lambda value: pipe.ConnectNamedPipe(self.handle, value), .2)
                except (TimeoutError, OSError):
                    continue
                try:
                    self.handler(PipeConnection(self.handle, .5))
                except (OSError, ValueError, TypeError, AttributeError):
                    pass
                finally:
                    try: pipe.DisconnectNamedPipe(self.handle)
                    except types.error: pass
        finally:
            if not self.stop.is_set(): self.stop.set()

    def close(self):
        self.stop.set()
        if self.thread: self.thread.join(timeout=3)
        if self.handle is not None:
            self.handle.Close(); self.handle = None
