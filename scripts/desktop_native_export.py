"""Narrow bundled native export writer; request metadata and bytes arrive on stdin.

No credentials, source bodies or selected paths are logged. This helper does not
open research databases, invoke models, or use a developer/system interpreter.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.platform_support import files

MAX_BYTES = 64 * 1024 * 1024
MAX_HEADER = 16 * 1024


class ExportRejected(ValueError):
    """Deliberately excludes selected paths and source contents from messages."""


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _ordinary_path(value: object) -> Path:
    if not isinstance(value, str) or not value or '\0' in value:
        raise ExportRejected('unsafe_destination')
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        raise ExportRejected('unsafe_destination')
    if os.name == 'nt':
        # The platform helper also rejects UNC, device paths and alternate streams.
        from src.platform_support.windows import _full
        path = _full(path)
    return path


def _windows_safe_acl(path: Path, *, ancestor: bool = False) -> bool:
    """Permit ordinary inherited Downloads ACLs, but no foreign write grants.

    Do not change the user's selected directory permissions. Administrator and
    SYSTEM control are OS privileges; other accounts must not have write access.
    New output itself receives the platform helper's protected private ACL.
    """
    from src.platform_support import windows
    _, _, con, _, security, *_ = windows.require_runtime()
    handle = windows._handle(path, directory=path.is_dir())
    try:
        descriptor = windows._security(handle)
        acl = descriptor.GetSecurityDescriptorDacl()
        if acl is None:
            return False
        allowed = {
            windows.current_sid_text(),
            security.ConvertSidToStringSid(security.CreateWellKnownSid(security.WinLocalSystemSid, None)),
            security.ConvertSidToStringSid(security.CreateWellKnownSid(security.WinBuiltinAdministratorsSid, None)),
        }
        write_mask = con.GENERIC_ALL | con.GENERIC_WRITE | con.DELETE | con.WRITE_DAC | con.WRITE_OWNER | con.FILE_DELETE_CHILD
        if not ancestor:
            write_mask |= con.FILE_WRITE_DATA | con.FILE_APPEND_DATA | con.FILE_WRITE_EA | con.FILE_WRITE_ATTRIBUTES
        # A volume root may permit creation of new sibling folders. That alone
        # cannot replace an existing owned child; delete-child/control grants can.
        for index in range(acl.GetAceCount()):
            header, mask, sid = acl.GetAce(index)
            if header[0] == con.ACCESS_DENIED_ACE_TYPE:
                continue
            if header[0] != con.ACCESS_ALLOWED_ACE_TYPE:
                return False
            # Inherit-only ACEs do not grant access to this object.
            if header[1] & con.INHERIT_ONLY_ACE:
                continue
            if mask & write_mask and security.ConvertSidToStringSid(sid) not in allowed:
                return False
        return True
    finally:
        handle.Close()


def _safe_owned(path: Path) -> bool:
    if not files.owned_path(path):
        return False
    if os.name == 'nt':
        return _windows_safe_acl(path)
    return not (stat.S_IMODE(path.stat().st_mode) & 0o022)


def _identity(path: Path) -> dict:
    info = path.stat()
    return {'dev': info.st_dev, 'ino': info.st_ino, 'mode': info.st_mode,
            'size': info.st_size, 'mtime_ns': info.st_mtime_ns,
            'ctime_ns': info.st_ctime_ns}


def inspect_destination(request: dict) -> tuple[Path, dict]:
    path = _ordinary_path(request.get('path'))
    extension = request.get('extension')
    if extension not in {'csv', 'json'} or path.suffix.lower() != '.' + extension:
        raise ExportRejected('invalid_extension')
    if any(part.lower().endswith('.app') for part in path.parts):
        raise ExportRejected('application_destination')
    for key in ('install_root', 'data_root'):
        root = _ordinary_path(request.get(key))
        if _inside(path, root):
            raise ExportRejected('internal_destination')
    files.assert_no_links(path)
    parent = path.parent
    if not parent.is_dir() or not _safe_owned(parent):
        raise ExportRejected('unsafe_destination')
    # An ordinary ancestor can be owned by root/system, but a foreign writable
    # ancestor would permit replacement of the chosen path. Sticky /tmp is safe
    # only above the already-owned, non-writable selected parent.
    if os.name == 'nt':
        if any(not _windows_safe_acl(ancestor, ancestor=True) for ancestor in parent.parents):
            raise ExportRejected('unsafe_destination')
    else:
        for ancestor in parent.parents:
            info = ancestor.stat()
            writable = stat.S_IMODE(info.st_mode) & 0o022
            if writable and not (info.st_mode & stat.S_ISVTX and info.st_uid in {0, os.getuid()}):
                raise ExportRejected('unsafe_destination')
    exists = path.exists()
    if exists and (not path.is_file() or not _safe_owned(path)):
        raise ExportRejected('unsafe_destination')
    ancestors = []
    for item in (parent, *parent.parents):
        identity = _identity(item)
        ancestors.append({key: identity[key] for key in ('dev', 'ino', 'mode')})
    snapshot = {
        # Directory size/timestamps change when our own private temp is created;
        # only immutable identity and ownership/mode bind the parent hierarchy.
        'ancestors': ancestors,
        'target': _identity(path) if exists else None,
    }
    return path, snapshot


def _validate_request(request: object) -> dict:
    if not isinstance(request, dict):
        raise ExportRejected('invalid_request')
    common = {'operation', 'path', 'extension', 'install_root', 'data_root'}
    operation = request.get('operation')
    expected = common if operation == 'inspect' else common | {'snapshot', 'byte_length', 'sha256'}
    if operation not in {'inspect', 'write'} or set(request) != expected:
        raise ExportRejected('invalid_request')
    return request


def process_request(request: dict, stream: BinaryIO) -> dict:
    request = _validate_request(request)
    path, snapshot = inspect_destination(request)
    if request['operation'] == 'inspect':
        if stream.read(1):
            raise ExportRejected('invalid_request')
        return {'status': 'inspected', 'snapshot': snapshot}
    if request['snapshot'] != snapshot:
        raise ExportRejected('destination_changed')
    length = request['byte_length']
    if type(length) is not int or not 0 <= length <= MAX_BYTES:
        raise ExportRejected('size_limit')
    digest = request['sha256']
    if not isinstance(digest, str) or not re.fullmatch('[a-f0-9]{64}', digest):
        raise ExportRejected('invalid_request')
    descriptor = None
    temporary = None
    try:
        descriptor, temporary_name = files.private_tempfile(parent=path.parent, prefix='.litrev-export-')
        temporary = Path(temporary_name)
        hasher = hashlib.sha256()
        remaining = length
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ExportRejected('incomplete_body')
            remaining -= len(chunk)
            hasher.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(descriptor, view)
                if written < 1:
                    raise ExportRejected('write_failed')
                view = view[written:]
        if stream.read(1) or hasher.hexdigest() != digest:
            raise ExportRejected('body_mismatch')
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        _, current = inspect_destination(request)
        if current != snapshot:
            raise ExportRejected('destination_changed')
        if snapshot['target'] is None:
            files.publish_new(temporary, path)
        else:
            files.atomic_replace(temporary, path)
        try:
            files.sync_directory(path.parent)
        except OSError:
            return {'status': 'written', 'durability': 'unconfirmed'}
        return {'status': 'written', 'durability': 'confirmed'}
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None:
            # No-follow checks prevent a raced directory/link from causing
            # cleanup outside the originally selected ordinary destination.
            try:
                files.assert_no_links(temporary)
                temporary.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        # A completed atomic replacement is never undone: interruption after
        # publication can leave a written file even if the caller got no reply.


def main() -> int:
    try:
        header = sys.stdin.buffer.readline(MAX_HEADER + 1)
        if len(header) > MAX_HEADER or not header.endswith(b'\n'):
            raise ExportRejected('invalid_request')
        request = json.loads(header)
        result = process_request(request, sys.stdin.buffer)
        sys.stdout.write(json.dumps(result, separators=(',', ':')) + '\n')
        return 0
    except Exception as error:
        code = str(error) if isinstance(error, ExportRejected) else 'destination_or_write_failed'
        sys.stdout.write(json.dumps({'status': 'rejected', 'code': code}, separators=(',', ':')) + '\n')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
