#!/usr/bin/env python3
"""Run the two loopback-only v0.2 servers; Ctrl-C stops both child processes."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / ".mvp-web-state")
    parser.add_argument("--api-port", type=int, default=8765)
    parser.add_argument("--web-port", type=int, default=3000)
    parser.add_argument("--node", default=shutil.which("node"), help="Node.js executable (20.9+; tested with Node 24)")
    parser.add_argument("--production", action="store_true", help="Run an already-built Next.js application")
    args = parser.parse_args()
    if not args.node or not Path(args.node).is_file():
        parser.error("Install Node.js or supply --node /absolute/path/to/node")
    if not all(1024 <= port <= 65535 for port in (args.api_port, args.web_port)) or args.api_port == args.web_port:
        parser.error("Choose two different local ports between 1024 and 65535")
    next_cli = ROOT / "apps/web/node_modules/next/dist/bin/next"
    if not next_cli.is_file():
        parser.error("Install the locked apps/web dependencies before starting")
    env = os.environ.copy()
    env.update(MVP_WEB_DATA_DIR=str(args.data_dir.expanduser().absolute()),
               MVP_API_HOST=f"127.0.0.1:{args.api_port}",
               MVP_API_ORIGIN=f"http://127.0.0.1:{args.api_port}",
               MVP_WEB_ORIGIN=f"http://127.0.0.1:{args.web_port}",
               NEXT_TELEMETRY_DISABLED="1")
    env["PATH"] = str(Path(args.node).absolute().parent) + os.pathsep + env.get("PATH", "")
    commands = [
        [sys.executable, "-m", "uvicorn", "src.web_api.app:app_factory", "--factory",
         "--host", "127.0.0.1", "--port", str(args.api_port)],
        [args.node, str(next_cli), "start" if args.production else "dev",
         "--hostname", "127.0.0.1", "--port", str(args.web_port)],
    ]
    children = []
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for command in commands:
            children.append(subprocess.Popen(command, cwd=ROOT if command is commands[0] else ROOT / "apps/web", env=env))
        print(f"Local workspace: http://127.0.0.1:{args.web_port} — Ctrl-C stops both servers.", flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.25)
        return next((child.returncode for child in children if child.returncode), 0)
    except KeyboardInterrupt:
        return 0
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
