"""Explicit local/hosted policy, without request-derived deployment settings.

Hosted mode is deliberately one mounted, private data tree and one exact HTTPS
origin. It does not enable generation or obtain external credentials.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping
from urllib.parse import urlsplit

from src.mvp.bootstrap import ROOT


def _origin(value, *, hosted=False):
    try:
        parts = urlsplit(value)
        port = parts.port
        if (not isinstance(value, str) or not value or parts.username or parts.password
                or parts.path or parts.query or parts.fragment or not parts.hostname
                or value != parts.scheme + "://" + parts.netloc
                or parts.netloc != parts.hostname + (":" + str(port) if port else "")
                or parts.scheme not in ({"https"} if hosted else {"http", "https"})
                or (hosted and (parts.hostname.endswith(".localhost")
                    or parts.hostname.endswith("-")
                    or len(parts.hostname) > 253
                    or any(len(label) > 63 for label in parts.hostname.split("."))
                    or not re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z][a-z0-9-]*", parts.hostname)))
                or (port is not None and not 1 <= port <= 65535)
                or (hosted and port == 443)):
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise ValueError("Configure one exact canonical application origin.") from None
    return value


def _absolute_path(value, setting):
    if not isinstance(value, (str, Path)) or not str(value) or not Path(value).is_absolute():
        raise ValueError(f"{setting} must be an absolute private path.")
    path = Path(value)
    if ".." in path.parts or path != Path(os.path.normpath(path)):
        raise ValueError(f"{setting} must be a canonical absolute private path.")
    return path


@dataclass(frozen=True)
class DeploymentConfig:
    mode: str
    api_host: str
    api_origin: str
    public_origin: str
    data_dir: Path
    persistent_root: Path | None = None
    invite_sha256: str | None = field(default=None, repr=False)

    @property
    def hosted(self):
        return self.mode == "hosted"

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None):
        values = os.environ if environ is None else environ
        mode = values.get("MVP_DEPLOYMENT_MODE", "local")
        if mode not in {"local", "hosted"}:
            raise ValueError("MVP_DEPLOYMENT_MODE must be local or hosted.")
        if mode == "local":
            host = values.get("MVP_API_HOST", "127.0.0.1:8765")
            origin = values.get("MVP_WEB_ORIGIN", "http://127.0.0.1:3000")
            validate_local(host, origin)
            return cls(mode, host, "http://" + host, origin,
                       Path(values.get("MVP_WEB_DATA_DIR") or ROOT / ".mvp-web-state"))
        if values.get("MVP_HOSTED_INGRESS") != "render":
            raise ValueError("Hosted mode requires the explicitly supported Render HTTPS ingress.")
        origin = _origin(values.get("MVP_PUBLIC_ORIGIN"), hosted=True)
        host = values.get("MVP_API_HOST")
        upstream = values.get("MVP_API_ORIGIN")
        if host != "127.0.0.1:8765" or upstream != "http://127.0.0.1:8765":
            raise ValueError("Hosted FastAPI must use the configured literal internal loopback listener.")
        if values.get("MVP_WEB_ORIGIN", origin) != origin:
            raise ValueError("Hosted browser origin must match MVP_PUBLIC_ORIGIN exactly.")
        root = _absolute_path(values.get("MVP_PERSISTENT_ROOT"), "MVP_PERSISTENT_ROOT")
        directory = _absolute_path(values.get("MVP_WEB_DATA_DIR"), "MVP_WEB_DATA_DIR")
        if root == Path("/") or directory == root or not directory.is_relative_to(root):
            raise ValueError("Hosted data must be a private descendant of the persistent mount.")
        digest = values.get("MVP_HOSTED_INVITE_SHA256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Hosted admission requires a SHA-256 digest of a securely generated invitation code.")
        for setting in ("MVP_PROPOSALS_ENABLED", "MVP_SEARCH_PLANNER_ENABLED", "MVP_MAP_ENABLED"):
            if values.get(setting, "0") != "0":
                raise ValueError("Hosted generation and new map computation are disabled in this release.")
        return cls(mode, host, upstream, origin, directory, root, digest)

    def validate_storage(self):
        """Validate the real mount before any hosted registry/source is created."""
        if not self.hosted:
            return
        from src.mvp.workspace_ui import private_directory
        root = self.persistent_root
        if (root is None or not root.is_dir() or root.is_symlink()
                or any(path.is_symlink() for path in root.parents)
                or not os.path.ismount(root)):
            raise ValueError("Hosted persistent root must be an existing mounted, non-symlink directory.")
        directory = private_directory(self.data_dir)
        # Probe write + fsync without leaving research or a readiness artifact.
        descriptor, name = tempfile.mkstemp(prefix=".storage-probe-", dir=directory)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, b"storage-ready\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
            os.unlink(name)


def validate_local(allowed_host, allowed_origin):
    try:
        backend = urlsplit("http://" + allowed_host)
        origin = urlsplit(allowed_origin)
        loopback = {"127.0.0.1", "localhost", "::1"}
        if (backend.hostname not in loopback or backend.netloc != allowed_host or backend.path
                or backend.username or backend.password or backend.query or backend.fragment
                or origin.hostname not in loopback or origin.scheme not in {"http", "https"}
                or origin.path or origin.query or origin.fragment or origin.username or origin.password):
            raise ValueError
        # Force validation of syntactically malformed ports too.
        backend.port, origin.port
    except (TypeError, ValueError):
        raise ValueError("The local API Host and application Origin must be exact loopback origins") from None
