"""Small JSON contracts and no-follow, bounded local artifact I/O."""

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from uuid import uuid4

MAX_RECEIPT_BYTES = 100 * 1024 * 1024
MAX_ASSESSMENT_BYTES = 1024 * 1024
MAX_RECORDS = 10000
MAX_HISTORY_BYTES = 64 * 1024 * 1024
STATUSES = {"not_assessed", "sufficient", "partial", "insufficient", "uncertain"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    try:
        result = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
        result.encode("utf-8")
        return result
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError("Expected finite valid JSON") from None


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def is_digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def read_json(data):
    def pairs(rows):
        output = {}
        for key, value in rows:
            require(key not in output, "Duplicate JSON key")
            output[key] = value
        return output
    try:
        value = json.loads(data, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
        canonical(value)
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise ValueError("Invalid finite JSON") from None


def absolute_path(path):
    path = Path(path)
    require(".." not in path.parts, "Parent traversal is not allowed")
    return Path(os.path.abspath(path))


@contextmanager
def directory_fd(path, create=False):
    """Walk every ancestor using directory descriptors; never resolve a symlink."""
    path = absolute_path(path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        yield fd
    except OSError as error:
        raise ValueError("Local directory must be accessible and contain no symlinks") from error
    finally:
        os.close(fd)


def read_at(fd, name, limit):
    require(isinstance(name, str) and name not in {"", ".", ".."} and "/" not in name,
            "Expected a contained filename")
    try:
        handle = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            metadata = os.fstat(handle)
            require(stat.S_ISREG(metadata.st_mode) and metadata.st_size <= limit,
                    "Artifact must be a bounded regular non-symlink file")
            chunks, count = [], 0
            while True:
                chunk = os.read(handle, min(65536, limit + 1 - count))
                if not chunk:
                    break
                chunks.append(chunk)
                count += len(chunk)
                require(count <= limit, "Artifact exceeds its size bound")
            require(os.fstat(handle).st_size == metadata.st_size == count,
                    "Artifact changed while being read")
            return b"".join(chunks)
        finally:
            os.close(handle)
    except OSError as error:
        raise ValueError("Artifact must be a readable regular non-symlink file") from error


def read_bounded(path, limit=MAX_ASSESSMENT_BYTES):
    path = absolute_path(path)
    with directory_fd(path.parent) as fd:
        return read_at(fd, path.name, limit)


def write_at_new(fd, name, data):
    """Publish a complete immutable file with an exclusive hard-link operation."""
    require("/" not in name and name not in {"", ".", ".."}, "Invalid output filename")
    temporary = ".workbench-" + uuid4().hex
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        except FileExistsError:
            raise ValueError("Output already exists; choose a new immutable path") from None
        os.fsync(fd)
    finally:
        os.unlink(temporary, dir_fd=fd)


def write_new(path, value):
    path = absolute_path(path)
    with directory_fd(path.parent, create=True) as fd:
        write_at_new(fd, path.name, (canonical(value) + "\n").encode("utf-8"))


def finite_seconds(value):
    return value is None or (type(value) in (int, float) and math.isfinite(value) and value >= 0)
