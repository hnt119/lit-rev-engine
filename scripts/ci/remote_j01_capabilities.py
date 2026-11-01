#!/usr/bin/env python3
"""Remote-only prerequisite discovery. No app, browser launch, or qualification pass.

Public stdout/summary is constructed from a fixed metadata schema. No environment,
process command lines, credentials, profiles, databases or arbitrary logs exported.
"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

SOURCE = "a54cd9acc9cca860acc0e2aabcee01f9329276c4"


def main():
    result = {
        "schema": "litrev.remote-j01-capabilities.v1",
        "reviewed_source_sha": SOURCE,
        "source_identity": "NOT_RUN",
        "runner": "ubuntu-26.04 standard GitHub-hosted public VM",
        "kernel": platform.release()[:100],
        "architecture": platform.machine()[:30],
        "landlock_abi": None,
        "landlock_errno": None,
        "chrome_version": None,
        "chrome_executable_sha256": None,
        "linux_isolation": "NOT_RUN",
        "chromium_sandbox": "NOT_RUN",
        "browser_driver": "NOT_RUN",
        "actual_j01": "NOT_RUN",
        "status": "BLOCKED",
        "reason": "remote_guard",
    }
    if os.environ.get("GITHUB_ACTIONS") != "true" or platform.system() != "Linux":
        return result
    source = Path(os.environ["J01_REVIEWED_SOURCE"])
    p = subprocess.run(["git", "-C", str(source), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    if p.returncode or p.stdout.strip() != SOURCE:
        result["reason"] = "source_identity_mismatch"
        return result
    result["source_identity"] = "PASSED"
    if platform.machine() not in ("x86_64", "aarch64"):
        result["reason"] = "unsupported_syscall_architecture"
        return result
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    abi = libc.syscall(444, 0, 0, 1)  # landlock_create_ruleset VERSION, no policy changes
    if abi < 0:
        result["landlock_errno"] = ctypes.get_errno()
    else:
        result["landlock_abi"] = abi
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    if chrome:
        resolved = Path("/opt/google/chrome/chrome")
        if not resolved.is_file():
            resolved = Path(chrome).resolve()
        with resolved.open("rb") as stream:
            result["chrome_executable_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        p = subprocess.run([chrome, "--version"], capture_output=True, text=True, timeout=15)
        match = re.search(r"\b\d+\.\d+\.\d+\.\d+\b", p.stdout)
        if p.returncode == 0 and match:
            result["chrome_version"] = match.group()
    if abi < 9:
        result["reason"] = "landlock_abi9_required_for_pathname_unix_isolation"
    else:
        result["status"] = "PREREQUISITE_PASSED"
        result["reason"] = "full_isolation_and_browser_qualification_still_required"
    return result


if __name__ == "__main__":
    try:
        value = main()
    except Exception as error:
        value = {"schema": "litrev.remote-j01-capabilities.v1", "status": "BLOCKED", "reason": "capability_probe_error", "error_type": type(error).__name__, "actual_j01": "NOT_RUN"}
    encoded = json.dumps(value, sort_keys=True)
    print("J01_CAPABILITIES_JSON=" + encoded)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("## J01 capability discovery (not acceptance)\n\n```json\n" + json.dumps(value, indent=2, sort_keys=True) + "\n```\n")
    raise SystemExit(0 if value["status"] == "PREREQUISITE_PASSED" else 2)
