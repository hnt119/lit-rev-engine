"""Real owned subprocess/pipe checks; no runtimes, models, research or network."""
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Thread
import time
import pytest
from scripts.desktop_runtime_supervisor import supervise

pytestmark=pytest.mark.skipif(os.name=='nt',reason='Windows optional runtime is explicitly unavailable; no unqualified job supervision claim.')


def pipes():
    read,write=os.pipe();return os.fdopen(read,'rb',buffering=0),write


def test_completed_child_returns_bounded_status_without_waiting_for_parent_exit():
    owner,write=pipes()
    try:
        code,raw,reason=supervise([sys.executable,'-c','print("completed")'],owner,timeout=2,grace=.2)
        assert code==0 and raw==b'completed\n' and not reason
    finally:os.close(write);owner.close()


def test_parent_pipe_loss_requests_graceful_cleanup_and_does_not_kill_unrelated_child(tmp_path):
    owner,write=pipes();marker=tmp_path/'owned-cleanup'
    child_code='import signal,time,sys;from pathlib import Path;p=Path(sys.argv[1]);p.write_text("running");signal.signal(signal.SIGTERM,lambda *_:(p.unlink(),sys.exit(0)));time.sleep(60)'
    unrelated=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
    def close_owner():
        deadline=time.monotonic()+3
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.01)
        os.close(write)
    thread=Thread(target=close_owner);thread.start();started=time.monotonic()
    try:
        code,_,reason=supervise([sys.executable,'-c',child_code,str(marker)],owner,timeout=5,grace=.3)
        assert code==1 and 'owner loss' in reason and time.monotonic()-started<4
        assert not marker.exists() and unrelated.poll() is None
    finally:thread.join();owner.close();unrelated.terminate();unrelated.wait(timeout=3)


def test_runtime_expiry_hard_stops_only_the_still_live_owned_process(tmp_path):
    owner,write=pipes();pid_file=tmp_path/'pid'
    code='import signal,time,os,sys;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(60)'
    started=time.monotonic()
    try:
        result=supervise([sys.executable,'-c',code,str(pid_file)],owner,timeout=.3,grace=.15)
        assert result[0]==1 and 'runtime limit' in result[2] and time.monotonic()-started<2
        pid=int(pid_file.read_text())
        with pytest.raises(ProcessLookupError):os.kill(pid,0)
    finally:os.close(write);owner.close()


def test_closed_parent_pipe_cannot_start_a_child(tmp_path):
    owner,write=pipes();os.close(write);marker=tmp_path/'never-started'
    try:
        code,_,_=supervise([sys.executable,'-c','from pathlib import Path;Path('+repr(str(marker))+').touch()'],owner)
        assert code==1 and not marker.exists()
    finally:owner.close()


def test_cli_can_exit_with_parent_control_pipe_still_open(tmp_path):
    import shutil
    from scripts import desktop_runtime_supervisor as module
    wrapper=tmp_path/'desktop_runtime_supervisor.py';shutil.copy2(module.__file__,wrapper)
    (tmp_path/'install_desktop_optional_runtime.py').write_text('import json;print(json.dumps({"state":"installed_verified","id":"SYNTHETIC"}))\n')
    child=subprocess.Popen([sys.executable,'-I','-B',str(wrapper),'install'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        assert child.wait(timeout=5)==0
        assert b'installed_verified' in child.stdout.read() and child.stderr.read()==b''
    finally:child.stdin.close();child.stdout.close();child.stderr.close()
