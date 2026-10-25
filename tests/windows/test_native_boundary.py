"""Native Windows gates. Skips elsewhere are NOT Windows validation."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from threading import Event
import time

import pytest

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='Actual Windows kernel required')
ROOT = Path(__file__).resolve().parents[2]


def run(code, *args, **kwargs):
    return subprocess.run([sys.executable, '-c', code, *map(str, args)], cwd=ROOT,
        capture_output=True, text=True, timeout=15, **kwargs)


def test_private_current_sid_acl_strict_read_and_atomic_replace(tmp_path):
    from src.platform_support import private_directory, open_private, owned_path, atomic_replace
    from src.platform_support.windows import current_sid, require_runtime
    root = private_directory(tmp_path / 'Research 空间 with spaces')
    assert owned_path(root, private=True)
    path = root / 'settings.json'
    fd = open_private(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, b'{"public_fixture": true}'); os.close(fd)
    assert owned_path(path, private=True)
    fd = open_private(path, os.O_RDONLY, strict=True); assert os.read(fd, 100).startswith(b'{'); os.close(fd)
    temp = root / 'replacement.json'
    fd = open_private(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.write(fd, b'new'); os.close(fd)
    atomic_replace(temp, path); assert path.read_bytes() == b'new'
    _, _, con, _, security, *_ = require_runtime()
    acl = security.ACL(); acl.AddAccessAllowedAce(security.ACL_REVISION, con.FILE_ALL_ACCESS,
        security.CreateWellKnownSid(security.WinWorldSid, None))
    security.SetNamedSecurityInfo(str(path), security.SE_FILE_OBJECT,
        security.DACL_SECURITY_INFORMATION | security.UNPROTECTED_DACL_SECURITY_INFORMATION, None, None, acl, None)
    assert not owned_path(path, private=True)
    with pytest.raises(ValueError): open_private(path, os.O_RDONLY, strict=True)


def test_hardlink_reparse_junction_and_unsafe_windows_paths_refused(tmp_path):
    from src.platform_support import private_directory, open_private, assert_no_links, is_link
    root = private_directory(tmp_path / 'private')
    path = root / 'one'; fd = open_private(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd)
    os.link(path, root / 'two')
    with pytest.raises(ValueError): open_private(root / 'two', os.O_RDWR)
    target = tmp_path / 'target'; target.mkdir()
    junction = tmp_path / 'junction'
    # mklink is a cmd built-in, with fixture-only generated paths. No shell
    # string interpolation and no application command wrappers are used.
    result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(junction), str(target)], capture_output=True, timeout=10)
    assert result.returncode == 0, 'Native junction setup failed; gate cannot be skipped'
    try:
        assert is_link(junction)
        with pytest.raises(ValueError): private_directory(junction / 'unsafe')
    finally: junction.rmdir()
    for value in (r'\\server\share\data', r'\\?\C:\data', str(root / 'settings.json:secret'), str(root / 'NUL'), str(root / 'trailing.')):
        with pytest.raises(ValueError): assert_no_links(value)


def test_real_lockfileex_cross_process_shared_exclusive_and_nonblocking(tmp_path):
    from src.platform_support import private_directory, open_private
    from src.platform_support import locks
    root = private_directory(tmp_path / 'lock state'); path = root / 'lock'
    fd = open_private(path, os.O_CREAT | os.O_RDWR)
    code = '''import os,sys
from src.platform_support import open_private
from src.platform_support import locks
fd=open_private(sys.argv[1],os.O_RDWR)
try:
 locks.flock(fd,int(sys.argv[2])|locks.LOCK_NB)
 print('acquired')
except BlockingIOError:print('blocked')
finally:os.close(fd)
'''
    try:
        locks.flock(fd, locks.LOCK_SH)
        assert run(code, path, locks.LOCK_SH).stdout.strip() == 'acquired'
        assert run(code, path, locks.LOCK_EX).stdout.strip() == 'blocked'
        locks.flock(fd, locks.LOCK_UN)
        assert run(code, path, locks.LOCK_EX).stdout.strip() == 'acquired'
    finally: os.close(fd)


def test_pack_liveness_never_signals_a_windows_pid(tmp_path, monkeypatch):
    from src.platform_support import is_process_alive
    monkeypatch.setattr(os, 'kill', lambda *_: pytest.fail('Windows liveness must never call os.kill'))
    assert is_process_alive(os.getpid())
    assert not is_process_alive(None)
    assert not is_process_alive(2 ** 30)


def test_non_utf8_locale_preserves_exact_private_unicode_json(tmp_path, monkeypatch):
    import locale
    from scripts import local_preview as preview
    from src.web_api.runtime_settings import RuntimeSettings, RuntimePreferences, SettingsPut
    from src.mvp.retrieval_packs import _write
    assert sys.flags.utf8_mode == 0, 'The gate must exercise ordinary locale mode, not Python UTF-8 mode'
    assert locale.getpreferredencoding(False).lower().replace('-', '') != 'utf8', 'A real non-UTF8 Windows locale is required'
    root = preview.private_directory(tmp_path / 'Locale 数据')
    value = {'text': '亚洲女性 🧬 e\u0301 — non-ASCII exact JSON'}
    path = root / 'launcher.json'; preview.atomic_json(path, value)
    assert preview.checked_json(path) == value
    assert json.loads(path.read_bytes()) == value
    _write(root / 'pack-state.json', value)
    assert json.loads((root / 'pack-state.json').read_bytes()) == value
    preferences = RuntimePreferences.model_validate({'ai': {'model': value['text']}})
    owner = 'a' * 64
    settings = RuntimeSettings(root)
    settings.put(owner, SettingsPut(expected_revision=0, preferences=preferences))
    assert RuntimeSettings(root).get(owner)['preferences']['ai']['model'] == value['text']


def test_long_unicode_private_path_and_process_arguments(tmp_path):
    from src.platform_support import private_directory, open_private, owned_path
    from src.platform_support.processes import WindowsJob
    root = private_directory(tmp_path / ('Long 空间 ' + 'nested ' * 5).rstrip())
    path = root
    while len(str(path)) < 280: path = path / ('directory ' + 'x' * 25)
    private_directory(path)
    target = path / 'public.json'; fd = open_private(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, b'public fixture'); os.close(fd)
    assert owned_path(target, private=True) and target.read_bytes() == b'public fixture'
    # list2cmdline quotes data arguments, never interprets their metacharacters.
    marker = root / 'argv.json'
    arguments = ['space value', 'Unicode 数据', '& echo must-not-execute', '%PATH%', 'quote"value']
    code = 'import json,sys;from pathlib import Path;Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))'
    job = WindowsJob()
    try:
        child = job.spawn([sys.executable, '-c', code, str(marker), *arguments], ROOT, os.environ)
        assert child.wait(timeout=10) == 0
        assert json.loads(marker.read_text()) == arguments
    finally: job.close()


def test_named_pipe_auth_status_stop_and_native_server_identity(tmp_path):
    from scripts import local_preview as preview
    from src.platform_support.control import connect
    data = preview.private_directory(tmp_path / 'Data 空间')
    state = preview.private_directory(data / '.preview')
    stop = Event(); identity = {'token': 'a' * 64, 'instance': 'b' * 32, 'pid': os.getpid(), 'phase': 'ready'}
    controller = preview.Controller(state, stop, identity)
    with preview.owner_lock(state):
        controller.start(); preview.atomic_json(state / 'owner.json', identity)
        try:
            # Repeat real client connect/read/close cycles to catch response
            # loss if buffered bytes are discarded by a premature disconnect.
            for _ in range(10):
                assert preview.control_request(data, 'status')['status'] == 'ready'
            connection = connect(state, os.getpid())
            connection.sendall((json.dumps({'action': 'stop', 'token': 'c' * 64, 'instance': 'b' * 32}) + '\n').encode())
            assert preview.read_message(connection)['status'] == 'denied'; connection.close()
            assert not stop.is_set()
            with pytest.raises(ValueError): connect(state, os.getpid() + 1)
            connection = connect(state, os.getpid())
            connection.sendall((json.dumps({'action': 'stop', 'token': 'a' * 64, 'instance': 'b' * 32}) + '\n').encode())
            assert preview.read_message(connection)['status'] == 'stopping'; connection.close()
            assert stop.wait(2)
        finally: controller.close()


def test_job_kills_only_owned_children_and_exact_listener_required(tmp_path):
    from src.platform_support.processes import WindowsJob, windows_listener_owned
    with socket.socket() as probe, socket.socket() as other:
        probe.bind(('127.0.0.1', 0)); port = probe.getsockname()[1]
        other.bind(('127.0.0.1', 0)); foreign_port = other.getsockname()[1]
    code = 'import socket,time; s=socket.socket();s.bind(("127.0.0.1",'+str(port)+'));s.listen();time.sleep(60)'
    job = WindowsJob()
    marker = tmp_path / 'foreign-listening.txt'
    foreign_code = 'import socket,time,sys;from pathlib import Path;s=socket.socket();s.bind(("127.0.0.1",'+str(foreign_port)+'));s.listen();Path(sys.argv[1]).write_bytes(b"ready");time.sleep(60)'
    foreign = subprocess.Popen([sys.executable, '-c', foreign_code, str(marker)])
    try:
        child = job.spawn([sys.executable, '-c', code], ROOT, os.environ)
        deadline = time.monotonic() + 5
        while not windows_listener_owned(child, port) and time.monotonic() < deadline: time.sleep(.05)
        assert windows_listener_owned(child, port)
        assert not windows_listener_owned(child, port + 1)
        assert not windows_listener_owned(foreign.pid, port)
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline: time.sleep(.05)
        assert marker.exists()
        assert not windows_listener_owned(child, foreign_port)
        job.close()
        assert foreign.poll() is None
    finally:
        job.close(); foreign.terminate(); foreign.wait(timeout=5)


def test_parent_crash_closes_job_and_children(tmp_path):
    from src.platform_support import private_directory, is_process_alive
    directory = private_directory(tmp_path / 'Crash state 空间'); marker = directory / 'child.json'
    code = '''import json,os,sys,time
from pathlib import Path
from src.platform_support.processes import WindowsJob
job=WindowsJob();child=job.spawn([sys.executable,'-c','import time;time.sleep(120)'],Path.cwd(),os.environ)
Path(sys.argv[1]).write_text(json.dumps({'pid':child.pid}))
time.sleep(120)
'''
    parent = subprocess.Popen([sys.executable, '-c', code, str(marker)], cwd=ROOT)
    try:
        deadline = time.monotonic() + 7
        while not marker.exists() and time.monotonic() < deadline:
            assert parent.poll() is None; time.sleep(.05)
        assert marker.exists()
        pid = json.loads(marker.read_text())['pid']; assert is_process_alive(pid)
        # Owned Popen handle, never a stored PID kill.
        parent.kill(); parent.wait(timeout=5)
        deadline = time.monotonic() + 7
        while is_process_alive(pid) and time.monotonic() < deadline: time.sleep(.05)
        assert not is_process_alive(pid)
    finally:
        if parent.poll() is None: parent.kill(); parent.wait(timeout=5)


def test_stopped_backup_restore_preserves_original_and_rejects_live_owner(tmp_path):
    import argparse
    from scripts import local_preview as preview
    from src.platform_support import open_private, owned_path
    root = preview.private_directory(tmp_path / 'research')
    data = preview.private_directory(root / 'Data 空间')
    path = data / 'public-fixture.json'; fd = open_private(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, b'{"draft": "retained"}'); os.close(fd)
    output = tmp_path / 'backup.tar.gz'
    args = argparse.Namespace(command='backup', data_dir=data, output=output)
    state = preview.private_directory(data / '.preview')
    with preview.owner_lock(state):
        with pytest.raises(preview.LocalLaunchError): preview.stopped_backup(args)
    assert preview.stopped_backup(args)['files'] >= 1
    assert owned_path(output, private=True)
    import tarfile
    with tarfile.open(output, 'r:gz') as archive:
        assert archive.extractfile('data/.preview/owner.lock').read() == b''
    destination = root / 'Restored 空间'
    args = argparse.Namespace(command='restore', data_dir=data, archive=output, destination=destination)
    assert preview.stopped_backup(args)['files'] >= 1
    assert (destination / path.name).read_bytes() == path.read_bytes()
    assert owned_path(destination / path.name, private=True)
    with pytest.raises(ValueError): preview.stopped_backup(args)
