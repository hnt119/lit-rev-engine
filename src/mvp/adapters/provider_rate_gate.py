"""Bounded same-user process sharing for the fixed literature-provider gates.

Only default live HTTP uses this gate. A lock covers timing, never a network
request. The state contains a monotonic timestamp, not URLs or credentials.
"""
from src.platform_support import locks as fcntl
import math
import os
from src.platform_support import current_user_key, private_directory, open_private
from pathlib import Path
import stat
import tempfile
import time

from ..ports import ProviderFailure


def wait_for_provider(host, interval, *, directory=None):
    if host not in {"eutils.ncbi.nlm.nih.gov", "www.ebi.ac.uk", "api.crossref.org"}:
        raise ProviderFailure("invalid_endpoint", "Unsupported provider rate gate.")
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or not math.isfinite(interval) or not 0 < interval <= 1:
        raise ValueError("The fixed provider interval must be positive and at most one second")
    folder = Path(directory) if directory is not None else Path(tempfile.gettempdir()).resolve() / ("lit-rev-provider-gates-" + current_user_key())
    descriptor = None
    acquired = False
    try:
        private_directory(folder)
        descriptor = open_private(folder / (host + ".gate"), os.O_CREAT | os.O_RDWR)
        deadline = time.monotonic() + 2.0
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ProviderFailure("rate_gate_busy", "The local shared provider gate is busy; retry explicitly.", True)
                time.sleep(.02)
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = os.read(descriptor, 64)
        try:
            previous = float(raw) if raw else float("-inf")
            if raw and not math.isfinite(previous):
                raise ValueError("Non-finite timing record")
        except ValueError:
            raise ProviderFailure("rate_gate_invalid", "The shared provider timing record is invalid; no request was sent.") from None
        current = time.monotonic()
        # A timestamp from before a machine restart cannot cause an unbounded
        # sleep. Waiting one interval still preserves spacing for this owner.
        remaining = min(interval, max(0.0, interval - (current - previous)))
        if remaining:
            time.sleep(remaining)
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        os.write(descriptor, repr(time.monotonic()).encode("ascii"))
    except ProviderFailure:
        raise
    except (OSError, ValueError):
        raise ProviderFailure("rate_gate_unavailable", "The private shared provider gate is unavailable; no request was sent.", True) from None
    finally:
        if descriptor is not None:
            try:
                if acquired: fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally: os.close(descriptor)
