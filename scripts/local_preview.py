#!/usr/bin/env python3
"""Set up and run the existing local app. No Docker, hosted state or data migration."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
from threading import Event, Thread
import time
import venv
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_web import LocalLaunchError, LocalServers, local_environment, server_commands, validate_ports
from scripts.local_beta_settings import load_settings, feature_environment
from scripts.license_policy import validate_distribution_license

VERSION = "0.3.0-beta.3"
VENV = ".venv-preview"
SETUP = ".local-preview-setup.json"
OWNED = ".local-preview-owned"


def default_data_dir():
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/LiteratureReviewEngine"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share") / "lit-rev-engine"


def supported_platform():
    if not (sys.platform == "darwin" or sys.platform.startswith("linux")):
        raise LocalLaunchError("macOS arm64 is tested; Linux installation is unverified and Windows is unsupported in this beta.")


def private_directory(path):
    path = Path(path).expanduser().absolute()
    if any(item.is_symlink() for item in (path, *path.parents)):
        raise LocalLaunchError("Use a private data path without symlinks (on macOS use /private/tmp instead of /tmp for QA).")
    if path.exists() and (not path.is_dir() or path.stat().st_uid != os.getuid()):
        raise LocalLaunchError("The preview directory must be owned by the current user.")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".new-" + secrets.token_hex(6))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def checked_json(path):
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 16384:
        raise LocalLaunchError("Private launcher metadata is unsafe; nothing was signalled.")
    return json.loads(path.read_text())


def fingerprint(root):
    """Bind setup to application/build inputs, excluding generated/private files."""
    root = Path(root)
    paths = [root / name for name in ("requirements-hosted.txt", "requirements-web-lock.txt",
             "scripts/local_preview.py", "scripts/run_web.py", "scripts/local_beta_settings.py",
             "scripts/check_local_beta.py", "scripts/license_policy.py", "requirements-map.txt",
             "requirements-map-lock.txt", "requirements-retrieval.txt", "src/mvp/retrieval_pack_manifest.json",
             "src/mvp/retrieval_pack_notices.json", "LICENSE", "THIRD_PARTY_NOTICES.md", "apps/streamlit/theme/tokens.css")]
    paths += list((root / "src").rglob("*.py"))
    for directory, subdirectories, files in os.walk(root / "apps/web"):
        subdirectories[:] = [name for name in subdirectories if name not in {"node_modules", ".next", ".git"}]
        paths += [Path(directory) / name for name in files if not name.startswith(".env") and not name.endswith(".tsbuildinfo")]
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        if path.is_symlink():
            raise LocalLaunchError("Application source inputs must not be symlinks; extract a clean release.")
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def reject_web_env_files(root):
    # Next loads these files independently of our subprocess environment.
    if any(path.name in {".env", ".env.local", ".env.production", ".env.production.local"}
           for path in (Path(root) / "apps/web").glob(".env*")):
        raise LocalLaunchError("Remove local Next.js .env files from the extracted app before setup/launch; use the explicit private --config or --allow-live route instead.")


def executable(path, name):
    value = path or shutil.which(name)
    if not value or not Path(value).is_file() or not os.access(value, os.X_OK):
        raise LocalLaunchError(f"Install {name} first or supply --{name} /absolute/path/to/{name}.")
    return str(Path(value).absolute())


def command_version(command, env):
    try:
        result = subprocess.run(command, env=env, capture_output=True, text=True, check=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        raise LocalLaunchError("A required runtime could not report its version. Check the supplied executable paths.") from None
    return result.stdout.strip()


def prerequisites(node=None, pnpm=None, *, require_pnpm=True):
    supported_platform()
    if sys.version_info[:2] != (3, 12):
        raise LocalLaunchError("Run this command using Python3.12 (python3.12 scripts/local_preview.py ...).")
    node = executable(node, "node")
    env = local_environment(os.environ, data_dir=default_data_dir(), api_port=8765, web_port=3000, node=node, isolated=True)
    version = command_version([node, "--version"], env)
    if not re.fullmatch(r"v24\.[0-9]+\.[0-9]+", version):
        raise LocalLaunchError("Install Node.js24; this preview is tested on Node24 and does not download a runtime automatically.")
    result = {"node": node, "node_version": version}
    if require_pnpm:
        pnpm = executable(pnpm, "pnpm")
        if command_version([pnpm, "--version"], env) != "10.20.0":
            raise LocalLaunchError("Install pnpm10.20.0 explicitly (npm install --global pnpm@10.20.0), or supply --pnpm with that executable.")
        result["pnpm"] = pnpm
    return result


def setup(args):
    validate_distribution_license(ROOT)
    tools = prerequisites(args.node, args.pnpm)
    reject_web_env_files(ROOT)
    target = ROOT / VENV
    if target.is_symlink() or (target.exists() and not (target / OWNED).is_file()):
        raise LocalLaunchError("An unowned .venv-preview already exists. Move it aside manually before setup; no data directory was changed.")
    if target.exists():
        shutil.rmtree(target)
    venv.EnvBuilder(with_pip=True).create(target)
    (target / OWNED).write_text(VERSION + "\n")
    python = target / "bin/python"
    env = local_environment(os.environ, data_dir=default_data_dir(), api_port=8765, web_port=3000,
                            node=tools["node"], isolated=True, browser_host="localhost")
    requirements = ["-r", "requirements-hosted.txt"]
    if getattr(args, "with_maps", False):
        requirements += ["-r", "requirements-map.txt"]
    if getattr(args, "with_retrieval", False):
        requirements += ["-r", "requirements-retrieval.txt"]
    commands = [([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *requirements], ROOT),
                ([tools["pnpm"], "install", "--frozen-lockfile"], ROOT / "apps/web"),
                ([tools["pnpm"], "build"], ROOT / "apps/web")]
    for command, cwd in commands:
        result = subprocess.run(command, cwd=cwd, env=env)
        if result.returncode:
            raise LocalLaunchError("Setup failed while installing/building locked dependencies. Check this terminal and network access, then rerun setup; research data was not migrated.")
    atomic_json(ROOT / SETUP, {"version": VERSION, "root": str(ROOT), "fingerprint": fingerprint(ROOT),
                              "python": str(python), "optional_map_dependencies": bool(getattr(args, "with_maps", False)),
                              "optional_retrieval_dependencies": bool(getattr(args, "with_retrieval", False)), **tools})
    return {"status": "setup_complete", "version": VERSION, "data_created": False,
            "optional_map_dependencies": bool(getattr(args, "with_maps", False)),
            "optional_retrieval_dependencies": bool(getattr(args, "with_retrieval", False)), "model_downloads": 0}


@contextmanager
def installation_lock(shared=False):
    """Setup cannot replace a runtime used by this installation's live app."""
    descriptor = os.open(ROOT / ".local-preview-install.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise LocalLaunchError("The installation lock is unsafe.")
        try:
            fcntl.flock(descriptor, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LocalLaunchError("This installation is running or being set up. Stop its preview before setup; research data was not changed.") from None
        yield descriptor
    finally:
        os.close(descriptor)


def launch_configuration(args):
    marker = ROOT / SETUP
    if not marker.is_file():
        raise LocalLaunchError("Setup required: run python3.12 scripts/local_preview.py setup first.")
    configured = checked_json(marker)
    if configured.get("root") != str(ROOT) or configured.get("version") != VERSION or configured.get("fingerprint") != fingerprint(ROOT):
        raise LocalLaunchError("Setup required after an app update or folder move. Rerun setup; the separate data directory stays in place.")
    tools = prerequisites(args.node or configured.get("node"), require_pnpm=False)
    python = ROOT / VENV / "bin/python"
    version_env = local_environment(os.environ, data_dir=default_data_dir(), api_port=args.api_port,
                                    web_port=args.web_port, node=tools["node"], isolated=True)
    version = command_version([str(python), "--version"], version_env) if python.is_file() else ""
    if not re.fullmatch(r"Python 3\.12\.[0-9]+", version):
        raise LocalLaunchError("Setup required: the private Python3.12 runtime is missing or invalid.")
    reject_web_env_files(ROOT)
    validate_ports(args.api_port, args.web_port)
    return python, tools["node"]


def state_paths(data_dir):
    data_dir = Path(data_dir).expanduser().absolute()
    if ".." in data_dir.parts:
        raise LocalLaunchError("Use a canonical data directory without '..'; research data must remain outside the app folder.")
    if data_dir == ROOT or data_dir.is_relative_to(ROOT):
        raise LocalLaunchError("Distributed research data must live outside the application folder. Choose --data-dir with a private external path.")
    state = data_dir / ".preview"
    if len(str(state / "control").encode()) > 100:
        raise LocalLaunchError("The local control-socket path is too long. Choose a shorter private --data-dir (for QA, /private/tmp/lre-preview-qa).")
    return data_dir, state


@contextmanager
def owner_lock(state):
    descriptor = os.open(state / "owner.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise LocalLaunchError("Launcher ownership file is unsafe.")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise LocalLaunchError("This data directory already has a running preview. Use status/stop with the same --data-dir.") from None
        yield descriptor
    finally:
        os.close(descriptor)


def lock_held(state):
    try:
        descriptor = os.open(state / "owner.lock", os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return False
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise LocalLaunchError("Launcher ownership file is unsafe; nothing was signalled.")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
    finally:
        os.close(descriptor)


def read_message(connection):
    value = bytearray()
    while len(value) <= 4096:
        block = connection.recv(min(1024, 4097 - len(value)))
        if not block:
            break
        value.extend(block)
        if b"\n" in value:
            break
    if len(value) > 4096 or b"\n" not in value:
        raise ValueError("Invalid local control request")
    return json.loads(value.split(b"\n", 1)[0])


class Controller:
    def __init__(self, state, stop, identity):
        self.path, self.stop, self.identity = state / "control", stop, identity
        self.socket = None
        self.thread = None
        self.bound = False

    def start(self):
        if self.path.exists() or self.path.is_symlink():
            metadata = self.path.lstat()
            if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid():
                raise LocalLaunchError("Unexpected local control path; nothing was removed.")
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.settimeout(.5)
                probe.connect(str(self.path))
            except ConnectionRefusedError:
                self.path.unlink()
            else:
                raise LocalLaunchError("A control socket is live without this launcher lock; nothing was removed.")
            finally:
                probe.close()
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.bind(str(self.path))
        self.bound = True
        self.path.chmod(0o600)
        self.socket.listen(4)
        self.socket.settimeout(.2)
        self.thread = Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        try:
            while not self.stop.is_set():
                try:
                    connection, _ = self.socket.accept()
                except socket.timeout:
                    continue
                with connection:
                    connection.settimeout(.5)
                    try:
                        request = read_message(connection)
                        authorized = (request.get("instance") == self.identity["instance"]
                                      and isinstance(request.get("token"), str)
                                      and hmac.compare_digest(request["token"], self.identity["token"]))
                        if not authorized or request.get("action") not in {"status", "stop"}:
                            response = {"status": "denied"}
                        else:
                            response = {key: value for key, value in self.identity.items() if key != "token"}
                            response["status"] = self.identity["phase"]
                            if request["action"] == "stop":
                                response["status"] = "stopping"
                                self.stop.set()
                        connection.sendall((json.dumps(response) + "\n").encode())
                    except (OSError, ValueError, TypeError, AttributeError):
                        pass
        except OSError:
            if not self.stop.is_set():
                self.stop.set()

    def close(self):
        if self.socket:
            self.socket.close()
        if self.thread:
            self.thread.join(timeout=2)
        if self.bound:
            self.path.unlink(missing_ok=True)


def control_request(data_dir, action):
    supported_platform()
    data_dir, state = state_paths(data_dir)
    if any(item.is_symlink() for item in (state, *state.parents)):
        raise LocalLaunchError("Private launcher paths cannot contain symlinks; nothing was signalled.")
    if not state.exists() or not lock_held(state):
        return {"status": "stopped", "data_dir": str(data_dir)}
    for path in (data_dir, state):
        metadata = path.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise LocalLaunchError("Launcher state directories must be private and owned by this user; nothing was signalled.")
    identity = checked_json(state / "owner.json")
    if not re.fullmatch(r"[0-9a-f]{64}", identity.get("token", "")) or not re.fullmatch(r"[0-9a-f]{32}", identity.get("instance", "")):
        raise LocalLaunchError("Private launcher identity is invalid; nothing was signalled.")
    connection = socket.socket(socket.AF_UNIX)
    try:
        connection.settimeout(2)
        connection.connect(str(state / "control"))
        connection.sendall((json.dumps({"action": action, "token": identity["token"], "instance": identity["instance"]}) + "\n").encode())
        response = read_message(connection)
        if response.get("instance") != identity["instance"] or response.get("pid") != identity["pid"]:
            raise LocalLaunchError("The local controller identity did not match; nothing was signalled.")
    except (OSError, ValueError, KeyError, TypeError):
        raise LocalLaunchError("The launcher owns its lock but is not responding. Return to its terminal and use Ctrl-C; no PID was signalled.") from None
    finally:
        connection.close()
    if action == "stop":
        deadline = time.monotonic() + 20
        while lock_held(state) and time.monotonic() < deadline:
            time.sleep(.1)
        if lock_held(state):
            raise LocalLaunchError("The owned launcher did not stop in time. Return to its terminal; no unverified process was killed.")
        response["status"] = "stopped"
    return response


def configured_environment(args, node, data):
    path = getattr(args, "config", None)
    if path is not None and getattr(args, "allow_live", False):
        raise LocalLaunchError("Choose the private --config route or legacy --allow-live, not both. Put explicit live contact settings in the private file when combining features.")
    settings = load_settings(path, ROOT)
    env = local_environment(os.environ, data_dir=data, api_port=args.api_port, web_port=args.web_port,
                            node=node, isolated=True, allow_live=getattr(args, "allow_live", False), browser_host=args.browser_host)
    env.update(feature_environment(settings))
    cache = getattr(args, 'retrieval_cache', None)
    if cache:
        cache = Path(cache).expanduser()
        if (not cache.is_absolute() or '..' in cache.parts or cache.resolve().is_relative_to(ROOT.resolve())
            or any(path.is_symlink() for path in (cache, *cache.parents))):
            raise LocalLaunchError('Use an absolute private external retrieval cache without symlinks.')
        if cache.exists() and (not cache.is_dir() or cache.stat().st_uid != os.getuid() or stat.S_IMODE(cache.stat().st_mode) != 0o700):
            raise LocalLaunchError('Retrieval cache must be an owned mode-0700 directory.')
        env['LITREV_RETRIEVAL_CACHE'] = str(cache)
    return env


def check_configuration(args):
    validate_distribution_license(ROOT)
    python, node = launch_configuration(args)
    env = configured_environment(args, node, default_data_dir())
    result = subprocess.run([str(python), str(ROOT / "scripts/check_local_beta.py")],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
    try:
        report = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise LocalLaunchError("Configuration inspection failed; rerun setup for the extracted beta. No settings were printed.") from None
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return result.returncode


def launch(args, *, installation_descriptor=None):
    python, node = launch_configuration(args)
    data, state = state_paths(args.data_dir)
    env = configured_environment(args, node, data)
    private_directory(data)
    private_directory(state)
    stop = Event()
    identity = {"instance": secrets.token_hex(16), "token": secrets.token_hex(32), "pid": os.getpid(),
                "phase": "starting", "data_dir": str(data), "url": f"http://{args.browser_host}:{args.web_port}",
                "api_port": args.api_port, "web_port": args.web_port, "version": VERSION}
    servers = LocalServers(server_commands(ROOT, python, node, args.api_port, args.web_port, True), env,
                           args.api_port, args.web_port, browser_host=args.browser_host)
    with owner_lock(state) as owner_descriptor:
        # Keep both locks alive even if the controller is killed abruptly.
        # Orphan recovery remains explicit; no stale PID is ever signalled.
        servers.pass_fds = tuple(fd for fd in (owner_descriptor, installation_descriptor) if fd is not None)
        controller = Controller(state, stop, identity)
        wrote_owner = False
        previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            controller.start()
            atomic_json(state / "owner.json", identity)
            wrote_owner = True
            servers.start()
            if servers.wait_ready(stop):
                identity["phase"] = "ready"
                atomic_json(state / "owner.json", identity)
                print(json.dumps({key: value for key, value in identity.items() if key != "token"}), flush=True)
                if not args.no_browser:
                    webbrowser.open(identity["url"])
            while not stop.wait(.2):
                servers.check_children()
            return {"status": "stopped", "data_dir": str(data)}
        finally:
            stop.set()
            identity["phase"] = "stopping"
            servers.stop()
            controller.close()
            if wrote_owner:
                (state / "owner.json").unlink(missing_ok=True)
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    commands = parser.add_subparsers(dest="command", required=True)
    install = commands.add_parser("setup", help="Install the locked core runtime and build the production UI; no model weights")
    install.add_argument("--node")
    install.add_argument("--pnpm")
    install.add_argument("--with-retrieval", action="store_true", help="Install optional pinned local evidence-retrieval dependencies; no model weights")
    install.add_argument("--with-maps", action="store_true", help="Explicitly install existing pinned optional local mapping dependencies; never weights")
    run = commands.add_parser("launch", help="Run in this terminal; Ctrl-C stops both owned servers")
    run.add_argument("--node", help="Override the Node executable recorded by setup")
    run.add_argument("--api-port", type=int, default=8765)
    run.add_argument("--web-port", type=int, default=3000)
    run.add_argument("--browser-host", choices=("localhost", "127.0.0.1"), default="localhost")
    run.add_argument("--retrieval-cache", type=Path, help="Explicit private external model/index cache; does not install or index")
    run.add_argument("--no-browser", action="store_true")
    run.add_argument("--config", type=Path, help="Validated private JSON file outside the app; only existing local adapters and NCBI live opt-in")
    run.add_argument("--allow-live", action="store_true", help="Explicitly allow only validated NCBI_EMAIL/NCBI_API_KEY from this shell")
    check = commands.add_parser("check-config", help="Inspect explicit settings and optional setup without loading models or contacting providers")
    check.add_argument("--config", type=Path)
    check.add_argument("--node")
    check.add_argument("--retrieval-cache", type=Path)
    check.set_defaults(api_port=8765, web_port=3000, browser_host="localhost", allow_live=False)
    for command in (run, commands.add_parser("status"), commands.add_parser("stop")):
        command.add_argument("--data-dir", type=Path, default=default_data_dir())
    args = parser.parse_args()
    try:
        if args.command in {"setup", "launch", "check-config"}:
            with installation_lock(shared=args.command != "setup") as descriptor:
                if args.command == "check-config":
                    return check_configuration(args)
                result = setup(args) if args.command == "setup" else launch(args, installation_descriptor=descriptor)
        else:
            result = control_request(args.data_dir, args.command)
        print(json.dumps(result), flush=True)
        return 0
    except (LocalLaunchError, OSError, ValueError, subprocess.SubprocessError) as error:
        print("Local beta: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
