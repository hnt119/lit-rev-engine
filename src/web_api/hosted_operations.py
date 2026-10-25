"""Stopped-application operations for one persistent local SQLite deployment.

The supervisor holds the same exclusive lock as backup and restore. This is a
whole-application consistency boundary, not a claim that arbitrary live file
copies or independently launched API processes are safe.
"""
from contextlib import contextmanager
from src.platform_support import locks as fcntl
import hashlib
import json
import os
from src.platform_support import publish_new, sync_directory, private_tempdir, private_tempfile
from src.platform_support import open_private, restrict_fd, restrict_path, private_directory as platform_private_directory, is_link
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import stat
import tarfile
import tempfile

MAX_ARCHIVE_BYTES = 4 * 1024 ** 3
MAX_FILE_BYTES = 1024 ** 3
MAX_ARCHIVE_FILES = 100_000
MANIFEST = "litrev-backup-manifest.json"


class OperationError(ValueError):
    """A safe operator-facing failure; never includes stored research content."""


@contextmanager
def hosted_lock(root):
    """Nonblocking OS lock, retained through child reaping and shutdown."""
    root = Path(root)
    if not root.is_dir() or is_link(root) or root.resolve() != root.absolute():
        raise OperationError("The persistent root must be an existing real directory.")
    path = root / ".litrev-instance.lock"
    fd = open_private(path, os.O_CREAT | os.O_RDWR | 0, 0o600)
    try:
        restrict_fd(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise OperationError("Another hosted instance or stopped-app operation owns this disk; stop the entire application first.") from None
        yield
    finally:
        os.close(fd)


def _safe_tree(directory):
    directory = Path(directory)
    entries, total = [], 0
    for path in sorted(directory.rglob("*")):
        mode = path.lstat().st_mode
        if is_link(path) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)) or (stat.S_ISREG(mode) and path.stat().st_nlink != 1):
            raise OperationError("Data contains a link or special file; backup was refused.")
        if stat.S_ISDIR(mode):
            continue
        size = path.stat().st_size
        total += size
        if size > MAX_FILE_BYTES or total > MAX_ARCHIVE_BYTES or len(entries) >= MAX_ARCHIVE_FILES:
            raise OperationError("Backup exceeds the bounded archive limits.")
        relative = path.relative_to(directory).as_posix()
        entries.append((path, relative, size))
    return entries


def _check_databases(directory):
    for path in Path(directory).rglob("*.sqlite3"):
        try:
            # With no pending journal, immutable reads avoid SQLite creating
            # empty WAL/SHM files merely to inspect a stopped database. A real
            # pending WAL must be read normally, never silently ignored.
            pending = any(sidecar.exists() and sidecar.stat().st_size for sidecar in
                          (Path(str(path) + "-wal"), Path(str(path) + "-journal")))
            db = sqlite3.connect(path.as_uri() + "?mode=ro" + ("" if pending else "&immutable=1"), uri=True)
            try:
                valid = db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
            finally:
                db.close()
        except sqlite3.Error:
            valid = False
        if not valid:
            raise OperationError("A SQLite store failed integrity checking; no backup or restoration was published.")


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def create_backup(root, directory, output, *, validate_storage=None, operation_lock=None):
    """All stores, registry, drafts, jobs and artifacts in one stopped snapshot."""
    root, directory, output = (Path(value).absolute() for value in (root, directory, output))
    if (not directory.is_dir() or root.resolve() != root or directory.resolve() != directory
            or not directory.is_relative_to(root) or directory == root):
        raise OperationError("Backup requires a private data directory below the persistent root.")
    if output.is_relative_to(root.resolve()) or output.exists() or is_link(output):
        raise OperationError("Use a new output file outside the persistent disk, then protect the off-service copy.")
    if not output.parent.is_dir() or output.parent.resolve() != output.parent:
        raise OperationError("The backup output parent must already exist.")
    with (hosted_lock(root) if operation_lock is None else operation_lock):
        if validate_storage is not None:
            validate_storage()
        entries = _safe_tree(directory)
        # Validate a copy, never the only original. Some SQLite journal modes
        # need writable derived SHM state even for a read-only connection.
        snapshot = private_tempdir(prefix=".litrev-snapshot-", parent=output.parent)
        fd, temporary = private_tempfile(prefix=".litrev-backup-", parent=output.parent)
        try:
            for path, relative, _ in entries:
                target = snapshot / relative
                platform_private_directory(target.parent)
                with path.open("rb") as source, os.fdopen(open_private(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY), "wb") as destination:
                    restrict_path(target, 0o600)
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
            _check_databases(snapshot)
            entries = _safe_tree(snapshot)
            manifest = {"schema": "litrev.stopped-backup.v1", "files": {
                relative: {"size": size, "sha256": _sha256(path)} for path, relative, size in entries}}
            restrict_fd(fd, 0o600)
            raw_stream = os.fdopen(fd, "wb")
            fd = None
            with raw_stream as raw:
                with tarfile.open(fileobj=raw, mode="w:gz") as archive:
                    import io
                    payload = json.dumps(manifest, sort_keys=True).encode()
                    info = tarfile.TarInfo(MANIFEST)
                    info.mode, info.size = 0o600, len(payload)
                    archive.addfile(info, io.BytesIO(payload))
                    for path, relative, _ in entries:
                        info = archive.gettarinfo(str(path), arcname="data/" + relative)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mode = 0o600
                        with path.open("rb") as source:
                            archive.addfile(info, source)
                raw.flush()
                os.fsync(raw.fileno())
            # Hard-link publication is atomic and refuses an output created by
            # another operator after initial validation. No overwrite fallback.
            publish_new(temporary, output)
            _fsync_directory(output.parent)
        finally:
            if fd is not None:
                os.close(fd)
            Path(temporary).unlink(missing_ok=True)
            shutil.rmtree(snapshot)
    return {"files": len(entries), "bytes": sum(size for _, _, size in entries)}


def _fsync_directory(directory):
    sync_directory(directory)


def restore_backup(root, archive_path, destination, *, validate_storage=None, operation_lock=None):
    """Verify into a new directory; never overwrite or replace the only copy."""
    root, archive_path, destination = (Path(value).absolute() for value in (root, archive_path, destination))
    if (root.resolve() != root or destination == root or not destination.is_relative_to(root) or destination.exists()
            or is_link(destination) or destination.parent != root or is_link(archive_path)):
        raise OperationError("Restore requires a new direct child directory of the persistent root.")
    with (hosted_lock(root) if operation_lock is None else operation_lock):
        if validate_storage is not None:
            validate_storage()
        staging = private_tempdir(prefix=".litrev-restore-", parent=root)
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                members, names, total = [], set(), 0
                for member in archive:
                    name = PurePosixPath(member.name)
                    if (not member.isfile() or name.is_absolute() or ".." in name.parts
                            or str(name) != member.name or member.name in names or member.size > MAX_FILE_BYTES):
                        raise OperationError("Unsafe or duplicate archive entry; restoration was refused.")
                    if os.name == 'nt' and ('\\' in member.name or ':' in member.name):
                        raise OperationError('This archive contains unsupported Windows path components; restoration was refused.')
                    names.add(member.name)
                    if member.name != MANIFEST and (len(name.parts) < 2 or name.parts[0] != "data"):
                        raise OperationError("Unexpected archive entry; restoration was refused.")
                    total += member.size
                    if total > MAX_ARCHIVE_BYTES or len(names) > MAX_ARCHIVE_FILES + 1:
                        raise OperationError("Archive exceeds restoration bounds.")
                    members.append(member)
                if MANIFEST not in names:
                    raise OperationError("The backup manifest is missing.")
                manifest_member = next(item for item in members if item.name == MANIFEST)
                if manifest_member.size > 32 * 1024 ** 2:
                    raise OperationError("The backup manifest exceeds its bound.")
                manifest = json.load(archive.extractfile(manifest_member))
                if (not isinstance(manifest, dict) or manifest.get("schema") != "litrev.stopped-backup.v1" or not isinstance(manifest.get("files"), dict)
                        or set(manifest["files"]) != {item.name[5:] for item in members if item.name != MANIFEST}):
                    raise OperationError("The archive and its manifest disagree.")
                for member in members:
                    if member.name == MANIFEST:
                        continue
                    relative = member.name[5:]
                    target = staging / relative
                    platform_private_directory(target.parent)
                    with archive.extractfile(member) as source, os.fdopen(open_private(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY), "wb") as output:
                        restrict_path(target, 0o600)
                        shutil.copyfileobj(source, output, length=1024 * 1024)
                        output.flush()
                        os.fsync(output.fileno())
                    if manifest["files"][relative] != {"size": target.stat().st_size, "sha256": _sha256(target)}:
                        raise OperationError("A backup file failed exact manifest verification.")
            _check_databases(staging)
            # Serialized by the same lock; destination cannot be a live hosted
            # directory. Refuse any concurrently created path before publish.
            if destination.exists() or is_link(destination):
                raise OperationError("Restore destination now exists; nothing was overwritten.")
            publish_new(staging, destination, directory=True)
            _fsync_directory(root)
            return {"files": len(manifest["files"]), "bytes": total - manifest_member.size}
        except (tarfile.TarError, json.JSONDecodeError, UnicodeError, KeyError, TypeError) as error:
            raise OperationError("The backup archive is invalid; restoration was refused.") from error
        finally:
            if staging.exists():
                shutil.rmtree(staging)
