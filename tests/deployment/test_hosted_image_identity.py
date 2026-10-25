"""Opt-in verification of an explicitly built local hosted image.

Normal test runs never contact Docker. After building the approved image, run:
LITREV_HOSTED_TEST_IMAGE="sha256:<image-id>" python -m pytest -q \
    tests/deployment/test_hosted_image_identity.py

The probe starts no application services, mounts no data, disables networking,
and removes its synthetic home-directory files before the container exits.
It does not establish actual hosted-provider SSH availability.
"""
import json
import os
import re
import subprocess

import pytest


IDENTITY_PROBE = r'''
import grp
import json
import os
from pathlib import Path
import pwd
import stat
import subprocess
import tempfile

assert (os.getuid(), os.getgid(), os.geteuid(), os.getegid()) == (10001,) * 4, "Non-root runtime identity changed"
account = pwd.getpwuid(10001)
assert (account.pw_name, account.pw_gid) == ("litrev", 10001), "Runtime passwd entry changed"
assert grp.getgrgid(10001).gr_name == "litrev", "Runtime group changed"
assert account.pw_dir == "/home/litrev", "Runtime passwd home is missing or incorrect"
assert os.environ.get("HOME") == account.pw_dir, "Runtime HOME disagrees with passwd home"
assert account.pw_shell == "/bin/sh", "Runtime account requires a usable shell"
assert os.access(account.pw_shell, os.X_OK), "Runtime shell is not executable"
subprocess.run([account.pw_shell, "-c", "exit 0"], check=True)

home = Path(account.pw_dir)
assert Path.home() == home, "Runtime expanduser home disagrees with passwd home"
ssh = home / ".ssh"
for directory in (home, ssh):
    metadata = directory.lstat()
    assert stat.S_ISDIR(metadata.st_mode), "Private operator directory is absent or a symlink"
    assert (metadata.st_uid, metadata.st_gid) == (10001, 10001), "Private operator directory has incorrect ownership"
    assert stat.S_IMODE(metadata.st_mode) == 0o700, "Private operator directory must be mode0700"
assert not list(ssh.iterdir()), "An image must not ship SSH keys or credentials"

for directory in (home, ssh):
    # Exercise the runtime user's real permissions instead of merely checking
    # declarations in the Dockerfile. No credential filenames are introduced.
    descriptor, name = tempfile.mkstemp(prefix=".packaging-public-probe-", dir=directory)
    try:
        os.write(descriptor, b"Synthetic public packaging permission probe\n")
        os.fsync(descriptor)
        assert stat.S_IMODE(os.fstat(descriptor).st_mode) == 0o600
    finally:
        os.close(descriptor)
        os.unlink(name)
assert not list(ssh.iterdir()), "Packaging permission probe left an artifact"
print(json.dumps({"status": "PASS", "uid": 10001, "gid": 10001,
                  "home": str(home), "shell": account.pw_shell,
                  "home_mode": "0700", "ssh_mode": "0700", "ssh_empty": True}))
'''


def test_built_hosted_image_has_private_non_root_operator_home():
    image = os.environ.get("LITREV_HOSTED_TEST_IMAGE")
    if not image:
        pytest.skip("Opt-in: set LITREV_HOSTED_TEST_IMAGE to an explicitly built local image ID")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", image), "Use an immutable local image ID, not a tag"
    inspected = subprocess.run(
        ["docker", "image", "inspect", "--format",
         "{{json .Config.User}}\n{{json .Config.Entrypoint}}\n{{json .Config.WorkingDir}}\n{{json .Config.Healthcheck}}\n{{json .Os}}\n{{json .Architecture}}", image],
        text=True, capture_output=True, timeout=15, check=True,
    )
    user, entrypoint, workdir, healthcheck, operating_system, architecture = map(json.loads, inspected.stdout.splitlines())
    assert user == "10001:10001"
    assert entrypoint == ["python", "scripts/run_hosted.py"]
    assert workdir == "/app"
    assert healthcheck["Test"][0] == "CMD-SHELL"
    assert "127.0.0.1:8765/readyz" in healthcheck["Test"][1]
    assert operating_system == "linux" and architecture in {"amd64", "arm64"}, "Use a supported Linux image platform"
    platform = operating_system + "/" + architecture
    result = subprocess.run(
        ["docker", "run", "--rm", "--platform", platform, "--pull", "never", "--network", "none",
         "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
         "--entrypoint", "python", image, "-I", "-c", IDENTITY_PROBE],
        text=True, capture_output=True, timeout=30, check=True,
    )
    assert not result.stderr
    assert json.loads(result.stdout) == {
        "status": "PASS", "uid": 10001, "gid": 10001,
        "home": "/home/litrev", "shell": "/bin/sh",
        "home_mode": "0700", "ssh_mode": "0700", "ssh_empty": True,
    }
