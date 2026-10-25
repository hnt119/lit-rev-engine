import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from scripts.run_hosted import Supervisor


def test_successful_early_child_exit_is_still_failure(tmp_path):
    supervisor = Supervisor([([sys.executable, "-c", "raise SystemExit(0)"], tmp_path),
                             ([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path)], shutdown_seconds=1)
    assert supervisor.run() == 1
    assert all(child.returncode is not None for child in supervisor.children.values())


def test_nonzero_child_exit_propagates_and_sibling_reaped(tmp_path):
    supervisor = Supervisor([([sys.executable, "-c", "raise SystemExit(7)"], tmp_path),
                             ([sys.executable, "-c", "import time; time.sleep(60)"], tmp_path)], shutdown_seconds=1)
    assert supervisor.run() == 7
    assert all(child.returncode is not None for child in supervisor.children.values())


def test_sigterm_forwarded_with_bounded_forced_shutdown(tmp_path):
    marker = tmp_path / "signal.txt"
    pidfile = tmp_path / "child.pid"
    child = ("import os,signal,time,pathlib; "
             f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid())); "
             f"signal.signal(signal.SIGTERM, lambda *_: pathlib.Path({str(marker)!r}).write_text('TERM')); "
             "time.sleep(60)")
    harness = ("import sys; from scripts.run_hosted import Supervisor; "
               f"raise SystemExit(Supervisor([([sys.executable,'-c',{child!r}],{str(tmp_path)!r})],shutdown_seconds=.2).run())")
    process = subprocess.Popen([sys.executable, "-c", harness], cwd=Path(__file__).resolve().parents[2])
    try:
        deadline = time.monotonic() + 5
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        assert pidfile.exists()
        process.send_signal(signal.SIGTERM)
        assert process.wait(timeout=5) == 0
        assert marker.read_text() == "TERM"
        child_pid = int(pidfile.read_text())
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("supervisor left the child alive or unreaped")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
