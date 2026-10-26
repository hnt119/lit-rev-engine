"""Bounded parent-pipe supervision for the unchanged optional capsule installer.

The executable/arguments are fixed by this packaged module. Parent loss closes
an anonymous pipe: request helper cleanup, then kill only its still-live owned
process group. No stored PID, network control, provider key or system fallback.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event,Thread
import time

MAX_OUTPUT=65536


def supervise(command,owner_pipe,*,timeout=280,grace=3,cancel=None):
    """Return bounded child output or a safe reason; command injection is test-only."""
    if os.name=='nt':return 1,b'','Windows optional runtime supervision is not qualified.'
    cancelled=cancel or Event();output=bytearray();reason=[]
    def owner():
        try:os.read(owner_pipe.fileno(),1)
        except (OSError,ValueError):pass
        reason.append('parent_pipe_closed');cancelled.set()
    Thread(target=owner,daemon=True,name='runtime-installer-owner').start()
    if cancelled.wait(.01):return 1,b'','Installer owner is unavailable.'
    child=None
    def stop_owned():
        if child is None or child.poll() is not None:return
        try:os.killpg(child.pid,signal.SIGTERM)
        except ProcessLookupError:return
        try:child.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            # PID/group authority is the still-live child created above.
            if child.poll() is None:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            child.wait(timeout=grace)
    try:
        child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
        def read_output():
            while True:
                chunk=child.stdout.read(4096)
                if not chunk:return
                if len(output)+len(chunk)>MAX_OUTPUT:reason.append('output_limit');cancelled.set();return
                output.extend(chunk)
        reader=Thread(target=read_output,daemon=True,name='runtime-installer-output');reader.start()
        deadline=time.monotonic()+timeout
        while child.poll() is None:
            if cancelled.wait(.02):stop_owned();return 1,b'','Optional runtime installation cancelled after owner loss or interruption.'
            if time.monotonic()>=deadline:stop_owned();return 1,b'','Optional runtime installation exceeded its runtime limit.'
        reader.join(timeout=grace)
        if cancelled.is_set() or reader.is_alive():return 1,b'','Optional runtime installation was interrupted or exceeded its output bound.'
        return child.returncode,bytes(output),''
    finally:
        stop_owned()
        if child and child.stdout:child.stdout.close()


def main():
    cancelled=Event()
    signal.signal(signal.SIGTERM,lambda *_:cancelled.set())
    signal.signal(signal.SIGINT,lambda *_:cancelled.set())
    helper=Path(__file__).resolve().with_name('install_desktop_optional_runtime.py')
    # The existing helper validates its operation, target, pinned catalog and files.
    if not sys.argv[1:] or sys.argv[1]!='install':raise SystemExit('Use the packaged optional-runtime install operation.')
    command=[sys.executable,'-I','-B',str(helper),*sys.argv[1:]]
    try:code,raw,message=supervise(command,sys.stdin.buffer,cancel=cancelled)
    except (OSError,ValueError,subprocess.SubprocessError):code,raw,message=1,b'','Optional runtime supervision failed. Core remains available.'
    if not code:
        try:
            value=json.loads(raw)
            if not isinstance(value,dict) or value.get('state')!='installed_verified':raise ValueError()
        except (ValueError,UnicodeError):code=1;message='Optional installer returned an invalid result.'
    if code:print(json.dumps({'state':'invalid','message':message or 'Optional runtime installation failed. Core remains available.'}))
    else:print(json.dumps(value,separators=(',',':')))
    raise SystemExit(0 if not code else 1)
if __name__=='__main__':main()
