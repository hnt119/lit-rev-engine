#!/usr/bin/env python3
"""Run the existing two loopback servers; Ctrl-C stops owned child groups."""
import argparse
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SAFE_ENVIRONMENT = {"PATH", "HOME", "USER", "LOGNAME", "TMPDIR", "TMP", "TEMP",
                    "LANG", "LC_ALL", "LC_CTYPE", "DISPLAY", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"}


class LocalLaunchError(ValueError):
    pass


def validate_ports(api_port, web_port):
    if not all(1024 <= port <= 65535 for port in (api_port, web_port)) or api_port == web_port:
        raise LocalLaunchError("Choose two different local ports between 1024 and 65535.")


def check_ports_available(api_port, web_port):
    validate_ports(api_port, web_port)
    sockets = []
    try:
        for kind, port in (("api", api_port), ("web", web_port)):
            connection = socket.socket()
            sockets.append(connection)
            # Match the servers' address reuse after a recently closed TCP
            # connection. This does not permit sharing an active listener.
            connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                connection.bind(("127.0.0.1", port))
            except OSError:
                raise LocalLaunchError(f"Local {kind} port {port} is unavailable. Choose --{kind}-port with an unused port; no existing process was stopped.") from None
    finally:
        for connection in sockets:
            connection.close()


def local_environment(inherited, *, data_dir, api_port, web_port, node, isolated=False, allow_live=False, browser_host="127.0.0.1"):
    """Distribution receives an allowlist, never inherited app/provider settings."""
    if browser_host not in {"localhost", "127.0.0.1"}:
        raise LocalLaunchError("Browser host must be localhost or 127.0.0.1.")
    env = {key: value for key, value in inherited.items() if not isolated or key in SAFE_ENVIRONMENT}
    if isolated:
        env.update(MVP_MAP_ENABLED="0", MVP_SEARCH_PLANNER_ENABLED="0", MVP_PROPOSALS_ENABLED="0",
                   PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", NODE_ENV="production")
        if allow_live:
            email = inherited.get("NCBI_EMAIL", "").strip()
            key = inherited.get("NCBI_API_KEY", "").strip()
            if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                raise LocalLaunchError("--allow-live requires a valid NCBI_EMAIL in your shell. Its value will not be printed.")
            if key and not re.fullmatch(r"[A-Za-z0-9_-]{10,128}", key):
                raise LocalLaunchError("NCBI_API_KEY has an invalid format; remove or correct it before using --allow-live.")
            env["NCBI_EMAIL"] = email
            if key:
                env["NCBI_API_KEY"] = key
    for key in list(env):
        if key.startswith(("MVP_HOSTED_", "RENDER_")) or key in {"MVP_PUBLIC_ORIGIN", "MVP_PERSISTENT_ROOT"}:
            env.pop(key)
    env.update(MVP_DEPLOYMENT_MODE="local", MVP_WEB_DATA_DIR=str(Path(data_dir).expanduser().absolute()),
               MVP_API_HOST=f"127.0.0.1:{api_port}", MVP_API_ORIGIN=f"http://127.0.0.1:{api_port}",
               MVP_WEB_ORIGIN=f"http://{browser_host}:{web_port}", NEXT_TELEMETRY_DISABLED="1")
    env["PATH"] = str(Path(node).absolute().parent) + os.pathsep + env.get("PATH", os.defpath)
    return env


def server_commands(root, python, node, api_port, web_port, production):
    root = Path(root)
    next_cli = root / "apps/web/node_modules/next/dist/bin/next"
    if not next_cli.is_file():
        raise LocalLaunchError("Setup required: install the locked web dependencies first.")
    if production and not (root / "apps/web/.next/BUILD_ID").is_file():
        raise LocalLaunchError("Setup required: build the production web application first.")
    return [
        ([str(python), "-m", "uvicorn", "src.web_api.app:app_factory", "--factory", "--host", "127.0.0.1",
          "--port", str(api_port), "--workers", "1", "--no-access-log", "--no-proxy-headers",
          "--timeout-graceful-shutdown", "10"], root),
        ([str(node), str(next_cli), "start" if production else "dev", "--hostname", "127.0.0.1",
          "--port", str(web_port)], root / "apps/web"),
    ]


def listener_owned(pid, port):
    """Check the spawned PID owns this exact IPv4 loopback listening socket."""
    if sys.platform == "darwin":
        result = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid),
                                 "-iTCP@127.0.0.1:" + str(port), "-sTCP:LISTEN", "-F", "pn"],
                                capture_output=True, text=True, timeout=3)
        rows = result.stdout.splitlines()
        return result.returncode == 0 and "p" + str(pid) in rows and "n127.0.0.1:" + str(port) in rows
    if sys.platform.startswith("linux"):
        try:
            inodes = set()
            for entry in Path(f"/proc/{pid}/fd").iterdir():
                try:
                    target = entry.readlink().as_posix()
                except OSError:
                    continue
                if target.startswith("socket:["):
                    inodes.add(target[8:-1])
            rows = Path("/proc/net/tcp").read_text().splitlines()[1:]
            return any(parts[1] == f"0100007F:{port:04X}" and parts[3] == "0A" and parts[9] in inodes
                       for parts in (row.split() for row in rows))
        except (OSError, IndexError):
            return False
    raise LocalLaunchError("This local preview currently supports macOS and Linux only.")


def health_ready(port, path, expected, host="127.0.0.1"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request("GET", path, headers={"Host": f"{host}:{port}"})
        reply = connection.getresponse()
        return reply.status == 200 and json.loads(reply.read(1024)) == expected
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


class LocalServers:
    """Direct child groups; readiness never trusts foreign listeners."""
    def __init__(self, commands, env, api_port, web_port, *, shutdown_seconds=12, browser_host="127.0.0.1", pass_fds=()):
        self.commands, self.env = commands, env
        self.api_port, self.web_port = api_port, web_port
        self.shutdown_seconds = shutdown_seconds
        self.browser_host = browser_host
        self.children = []
        self.pass_fds = tuple(pass_fds)

    def start(self):
        check_ports_available(self.api_port, self.web_port)
        for command, cwd in self.commands:
            self.children.append(subprocess.Popen(command, cwd=cwd, env=self.env, start_new_session=True, pass_fds=self.pass_fds))

    def check_children(self):
        if any(child.poll() is not None for child in self.children):
            raise LocalLaunchError("A required local server exited. Both owned servers are stopping; inspect this terminal and run setup if dependencies changed.")

    def wait_ready(self, stop, timeout=60):
        deadline = time.monotonic() + timeout
        while not stop.is_set() and time.monotonic() < deadline:
            self.check_children()
            owned = all(listener_owned(child.pid, port) for child, port in zip(self.children, (self.api_port, self.web_port)))
            if owned and health_ready(self.api_port, "/readyz", {"ready": True}) and health_ready(self.web_port, "/healthz", {"status": "ok"}, self.browser_host):
                self.check_children()
                if all(listener_owned(child.pid, port) for child, port in zip(self.children, (self.api_port, self.web_port))):
                    return True
            stop.wait(.15)
        if stop.is_set():
            return False
        raise LocalLaunchError("Local startup did not become ready in time. Check this terminal, unused ports and setup; no browser was opened.")

    def stop(self):
        # External stop clients never signal a recorded PID. Only our direct
        # Popen children started in fresh sessions receive group signals.
        for child in self.children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + self.shutdown_seconds
        for child in self.children:
            try:
                child.wait(timeout=max(.01, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        # A primary may have exited before a descendant in its owned group.
        for child in self.children:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        for child in self.children:
            child.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".mvp-web-state")
    parser.add_argument("--api-port", type=int, default=8765)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--browser-host", choices=("localhost", "127.0.0.1"), default="127.0.0.1")
    parser.add_argument("--node", default=shutil.which("node"), help="Node.js executable (20.9+; tested with Node 24)")
    parser.add_argument("--production", action="store_true", help="Run an already-built Next.js application")
    args = parser.parse_args()
    if not args.node or not Path(args.node).is_file():
        parser.error("Install Node.js or supply --node /absolute/path/to/node")
    if not all(1024 <= port <= 65535 for port in (args.api_port, args.web_port)) or args.api_port == args.web_port:
        parser.error("Choose two different local ports between 1024 and 65535")
    from threading import Event
    stop = Event()
    servers = None
    previous = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        env = local_environment(os.environ, data_dir=args.data_dir, api_port=args.api_port, web_port=args.web_port, node=args.node, browser_host=args.browser_host)
        servers = LocalServers(server_commands(ROOT, sys.executable, args.node, args.api_port, args.web_port, args.production), env, args.api_port, args.web_port, browser_host=args.browser_host)
        servers.start()
        if servers.wait_ready(stop):
            print(f"Local workspace ready: http://{args.browser_host}:{args.web_port} — Ctrl-C stops both servers.", flush=True)
        while not stop.wait(.2):
            servers.check_children()
        return 0
    except (LocalLaunchError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if servers:
            servers.stop()
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    raise SystemExit(main())
