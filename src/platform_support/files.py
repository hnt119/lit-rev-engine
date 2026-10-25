"""Owned private paths/files. Windows permissions are ACLs, never chmod bits."""
import hashlib
import os
from pathlib import Path
import stat

IS_WINDOWS = os.name == 'nt'


def _windows():
    from . import windows
    windows.require_runtime()
    return windows


def is_link(path):
    path = Path(path)
    try:
        info = path.lstat()
        return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


def assert_no_links(path):
    path = Path(path).expanduser().absolute()
    if IS_WINDOWS:
        return _windows().assert_no_reparse(path)
    if any(is_link(item) for item in (path, *path.parents)):
        raise ValueError('Private paths must not contain symlinks or reparse points.')
    return path


def private_directory(path):
    path = assert_no_links(path)
    if IS_WINDOWS:
        return _windows().private_directory(path)
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.is_dir() or path.stat().st_uid != os.getuid():
        raise ValueError('Private directory must be owned by the current user.')
    path.chmod(0o700)
    return path


def open_private(path, flags, mode=0o600, *, strict=False):
    path = assert_no_links(path)
    if IS_WINDOWS:
        return _windows().open_private(path, flags, strict=strict)
    descriptor = os.open(path, (flags & ~os.O_TRUNC) | os.O_NOFOLLOW, mode)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise ValueError('Private file must be an ordinary owned file.')
        if strict and stat.S_IMODE(metadata.st_mode) != mode:
            raise ValueError('Private file permissions are unsafe.')
        if not strict:
            os.fchmod(descriptor, mode)
        if flags & os.O_TRUNC:
            os.ftruncate(descriptor, 0)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def owned_fd(descriptor, *, private=False, mode=0o600):
    if IS_WINDOWS:
        return _windows().owned_fd(descriptor, private=private)
    info = os.fstat(descriptor)
    return info.st_uid == os.getuid() and (not private or stat.S_IMODE(info.st_mode) == mode)


def owned_path(path, *, private=False, mode=None):
    try:
        path = assert_no_links(path)
        if IS_WINDOWS:
            return _windows().owned_path(path, private=private)
        info = path.stat()
        return info.st_uid == os.getuid() and (not private or stat.S_IMODE(info.st_mode) == (mode or (0o700 if path.is_dir() else 0o600)))
    except (OSError, ValueError):
        return False


def restrict_fd(descriptor, mode=0o600):
    if IS_WINDOWS:
        return _windows().restrict_fd(descriptor)
    os.fchmod(descriptor, mode)


def restrict_path(path, mode=0o600):
    path = assert_no_links(path)
    if IS_WINDOWS:
        return _windows().restrict_path(path)
    path.chmod(mode)


def current_user_key():
    if IS_WINDOWS:
        return hashlib.sha256(_windows().current_sid_text().encode()).hexdigest()[:32]
    return str(os.getuid())


def is_process_alive(pid):
    if type(pid) is not int or pid < 1:
        return False
    if IS_WINDOWS:
        return _windows().is_process_alive(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def venv_python(directory):
    return Path(directory) / ('Scripts/python.exe' if IS_WINDOWS else 'bin/python')


def atomic_replace(source, destination):
    assert_no_links(source); assert_no_links(destination)
    if IS_WINDOWS:
        _windows().move(source, destination, replace=True)
    else:
        os.replace(source, destination)


def publish_new(source, destination, *, directory=False):
    """Atomic no-overwrite publication; never replace the only data copy."""
    assert_no_links(source); assert_no_links(destination)
    if IS_WINDOWS:
        _windows().move(source, destination)
    elif directory:
        os.rename(source, destination)
    else:
        os.link(source, destination)


def sync_directory(directory):
    if IS_WINDOWS:
        # Windows publication uses MoveFileEx WRITE_THROUGH after file fsync.
        # There is no claimed POSIX directory-fsync equivalence here.
        assert_no_links(directory)
        return
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
