#!/usr/bin/env python3
"""PID-1 supervisor for one hosted Next.js/API instance on one durable disk."""
import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.web_api.hosted_operations import hosted_lock


class Supervisor:
    """Own child process groups; forward termination, reap, propagate failure."""
    def __init__(self, commands, *, env=None, shutdown_seconds=20):
        self.commands, self.env = commands, env
        self.shutdown_seconds = shutdown_seconds
        self.children = {}
        self.stopping = False

    def request_stop(self, signum, _frame):
        self.stopping = True

    def _reap(self):
        exited = []
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not pid:
                break
            if pid in self.children:
                self.children[pid].returncode = os.waitstatus_to_exitcode(status)
                exited.append(self.children[pid].returncode)
            # PID1 additionally reaps adopted descendants here. No process
            # details, request URLs or environment values enter the logs.
        return exited

    def _signal_groups(self, signum):
        for child in self.children.values():
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass

    def _shutdown(self):
        self._signal_groups(signal.SIGTERM)
        deadline = time.monotonic() + self.shutdown_seconds
        while any(child.returncode is None for child in self.children.values()) and time.monotonic() < deadline:
            self._reap()
            time.sleep(0.025)
        # Also terminate descendants left behind after a primary child exited.
        self._signal_groups(signal.SIGKILL)
        deadline = time.monotonic() + 3
        while any(child.returncode is None for child in self.children.values()) and time.monotonic() < deadline:
            self._reap()
            time.sleep(0.025)
        self._reap()

    def run(self):
        previous = {signum: signal.signal(signum, self.request_stop) for signum in (signal.SIGTERM, signal.SIGINT)}
        try:
            for command, cwd in self.commands:
                child = subprocess.Popen(command, cwd=cwd, env=self.env, start_new_session=True)
                self.children[child.pid] = child
            while not self.stopping:
                exited = self._reap()
                if exited:
                    print("A required hosted process exited; stopping the application.", file=sys.stderr, flush=True)
                    return next((code for code in exited if 0 < code < 256), 1)
                time.sleep(0.1)
            return 0
        finally:
            self._shutdown()
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def main():
    from src.web_api.deployment import DeploymentConfig
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    try:
        config = DeploymentConfig.from_environment()
        if config.mode != "hosted":
            raise ValueError("The hosted supervisor requires explicit hosted mode.")
        port = int(os.environ.get("PORT", "10000"))
        if not 1024 <= port <= 65535 or port == 8765:
            raise ValueError("Choose one public port between 1024 and 65535, other than the internal API port.")
        if not args.node or not Path(args.node).is_file():
            raise ValueError("The production Node runtime is missing.")
        next_cli = ROOT / "apps/web/node_modules/next/dist/bin/next"
        if not next_cli.is_file() or not (ROOT / "apps/web/.next/BUILD_ID").is_file():
            raise ValueError("Build the production frontend before hosted startup.")
        env = os.environ.copy()
        env.update(MVP_API_HOST="127.0.0.1:8765", MVP_API_ORIGIN="http://127.0.0.1:8765",
                   MVP_WEB_ORIGIN=config.public_origin, NEXT_TELEMETRY_DISABLED="1", NODE_ENV="production")
        commands = [
            ([sys.executable, "-m", "uvicorn", "src.web_api.app:app_factory", "--factory", "--host", "127.0.0.1",
              "--port", "8765", "--workers", "1", "--no-access-log", "--no-proxy-headers", "--timeout-graceful-shutdown", "15"], ROOT),
            ([args.node, str(next_cli), "start", "--hostname", "0.0.0.0", "--port", str(port)], ROOT / "apps/web"),
        ]
        os.umask(0o077)
        with hosted_lock(config.persistent_root):
            config.validate_storage()
            print("Starting one hosted application; data remains on its configured persistent disk.", flush=True)
            return Supervisor(commands, env=env).run()
    except (ValueError, OSError):
        print("Hosted startup refused. Check exact origin, admission, mounted private storage and production build configuration.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
