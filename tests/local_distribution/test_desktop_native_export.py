"""Filesystem/software checks, not native-dialog or target-Windows validation."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('desktop_native_export', ROOT / 'scripts/desktop_native_export.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def request(tmp_path, name='evidence.csv'):
    tmp_path.chmod(0o700)
    return {'operation': 'inspect', 'path': str(tmp_path / name), 'extension': Path(name).suffix[1:],
            'install_root': str(tmp_path / 'installed'), 'data_root': str(tmp_path / 'internal-data')}


def write_request(base, body=b'paper,value\npublic,manual\n'):
    snapshot = exporter.process_request(base, io.BytesIO())['snapshot']
    return {**base, 'operation': 'write', 'snapshot': snapshot, 'byte_length': len(body),
            'sha256': hashlib.sha256(body).hexdigest()}, body


def test_new_export_is_private_exact_and_temp_removed(tmp_path):
    base = request(tmp_path)
    change, body = write_request(base)
    assert exporter.process_request(change, io.BytesIO(body)) == {'status': 'written', 'durability': 'confirmed'}
    assert Path(base['path']).read_bytes() == body
    if os.name != 'nt':
        assert stat.S_IMODE(Path(base['path']).stat().st_mode) == 0o600
    assert not list(tmp_path.glob('.litrev-export-*'))


def test_explicit_overwrite_replaces_only_matching_snapshot(tmp_path):
    base = request(tmp_path)
    target = Path(base['path'])
    target.write_bytes(b'original')
    change, body = write_request(base)
    assert exporter.process_request(change, io.BytesIO(body))['status'] == 'written'
    assert target.read_bytes() == body


@pytest.mark.parametrize('change', ['target_changed', 'target_created', 'parent_replaced'])
def test_conflicting_destination_preserves_existing_bytes(tmp_path, change):
    folder = tmp_path / 'exports'
    folder.mkdir(mode=0o700)
    base = request(folder)
    target = Path(base['path'])
    if change == 'target_changed':
        target.write_bytes(b'original')
    write, body = write_request(base)
    if change == 'parent_replaced':
        folder.rename(tmp_path / 'old-exports')
        folder.mkdir(mode=0o700)
    target.write_bytes(b'concurrent edit')
    with pytest.raises(exporter.ExportRejected, match='destination_changed'):
        exporter.process_request(write, io.BytesIO(body))
    assert target.read_bytes() == b'concurrent edit'


@pytest.mark.parametrize('body_change', ['truncated', 'extra', 'digest', 'too_large'])
def test_bad_body_preserves_old_target_and_cleans_private_temporary(tmp_path, body_change):
    base = request(tmp_path)
    target = Path(base['path'])
    target.write_bytes(b'original')
    write, body = write_request(base)
    if body_change == 'truncated': body = body[:-1]
    elif body_change == 'extra': body += b'!'
    elif body_change == 'digest': write['sha256'] = '0' * 64
    else: write['byte_length'] = exporter.MAX_BYTES + 1
    with pytest.raises(exporter.ExportRejected):
        exporter.process_request(write, io.BytesIO(body))
    assert target.read_bytes() == b'original'
    assert not list(tmp_path.glob('.litrev-export-*'))


def test_write_failure_preserves_old_target(tmp_path):
    base = request(tmp_path)
    target = Path(base['path'])
    target.write_bytes(b'original')
    write, body = write_request(base)
    with mock.patch.object(exporter.os, 'write', side_effect=OSError('synthetic write error')):
        with pytest.raises(OSError):
            exporter.process_request(write, io.BytesIO(body))
    assert target.read_bytes() == b'original'
    assert not list(tmp_path.glob('.litrev-export-*'))


def test_destination_changed_during_write_is_rejected(tmp_path):
    base = request(tmp_path)
    target = Path(base['path'])
    target.write_bytes(b'original')
    write, body = write_request(base)
    real_write = exporter.os.write
    def concurrent(fd, value):
        target.write_bytes(b'concurrent')
        return real_write(fd, value)
    with mock.patch.object(exporter.os, 'write', side_effect=concurrent):
        with pytest.raises(exporter.ExportRejected, match='destination_changed'):
            exporter.process_request(write, io.BytesIO(body))
    assert target.read_bytes() == b'concurrent'


def test_new_publication_does_not_overwrite_concurrent_creation(tmp_path):
    base = request(tmp_path)
    write, body = write_request(base)
    target = Path(base['path'])
    original = exporter.files.publish_new
    def raced(source, destination):
        target.write_bytes(b'concurrent')
        return original(source, destination)
    with mock.patch.object(exporter.files, 'publish_new', side_effect=raced):
        with pytest.raises(FileExistsError):
            exporter.process_request(write, io.BytesIO(body))
    assert target.read_bytes() == b'concurrent'


def test_post_publication_sync_error_reports_written_but_not_durable(tmp_path):
    base = request(tmp_path)
    write, body = write_request(base)
    with mock.patch.object(exporter.files, 'sync_directory', side_effect=OSError('synthetic disk sync error')):
        assert exporter.process_request(write, io.BytesIO(body)) == {'status': 'written', 'durability': 'unconfirmed'}
    assert Path(base['path']).read_bytes() == body


@pytest.mark.parametrize('name', ['Other.app/out.csv', 'Other.APP/out.csv', 'internal-data/out.csv', 'installed/out.csv'])
def test_application_and_internal_paths_rejected(tmp_path, name):
    base = request(tmp_path)
    base['path'] = str(tmp_path / name)
    with pytest.raises(exporter.ExportRejected):
        exporter.process_request(base, io.BytesIO())


@pytest.mark.skipif(os.name == 'nt', reason='Native Windows reparse/ACL qualification is separate.')
@pytest.mark.parametrize('kind', ['target', 'parent'])
def test_symlink_paths_rejected(tmp_path, kind):
    base = request(tmp_path)
    if kind == 'target':
        other = tmp_path / 'other.csv'
        other.write_bytes(b'protected original')
        Path(base['path']).symlink_to(other)
    else:
        (tmp_path / 'real').mkdir(mode=0o700)
        (tmp_path / 'linked').symlink_to(tmp_path / 'real', target_is_directory=True)
        base['path'] = str(tmp_path / 'linked/out.csv')
    with pytest.raises(ValueError):
        exporter.process_request(base, io.BytesIO())


@pytest.mark.skipif(os.name == 'nt', reason='Uses POSIX ownership/mode simulation; not Windows ACL evidence.')
def test_unsafe_parent_or_foreign_owner_not_chmodded(tmp_path):
    base = request(tmp_path)
    tmp_path.chmod(0o777)
    with pytest.raises(exporter.ExportRejected):
        exporter.process_request(base, io.BytesIO())
    assert stat.S_IMODE(tmp_path.stat().st_mode) == 0o777
    tmp_path.chmod(0o700)
    with mock.patch.object(exporter.files, 'owned_path', return_value=False):
        with pytest.raises(exporter.ExportRejected):
            exporter.process_request(base, io.BytesIO())


def test_helper_cli_uses_stdin_and_reports_no_path_or_source_body(tmp_path):
    base = request(tmp_path)
    write, body = write_request(base, b'private-note-never-logged')
    result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/desktop_native_export.py')],
                            input=json.dumps(write).encode() + b'\n' + body,
                            capture_output=True, timeout=10, check=False)
    assert result.returncode == 0
    assert json.loads(result.stdout)['status'] == 'written'
    assert result.stderr == b''
    assert str(tmp_path).encode() not in result.stdout
    assert body not in result.stdout
    assert Path(base['path']).read_bytes() == body


def test_rejected_cli_has_bounded_nonprivate_error(tmp_path):
    result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'scripts/desktop_native_export.py')],
                            input=b'{"private-note":"not an export request"}\n', capture_output=True, timeout=10)
    assert result.returncode == 1
    assert result.stderr == b''
    assert json.loads(result.stdout) == {'status': 'rejected', 'code': 'invalid_request'}
