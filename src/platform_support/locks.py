"""Real cross-process shared/exclusive OS locks with existing flock semantics."""
import os

LOCK_SH, LOCK_EX, LOCK_NB, LOCK_UN = 1, 2, 4, 8


def flock(descriptor, operation):
    if os.name != 'nt':
        import fcntl
        return fcntl.flock(descriptor, operation)
    from .windows import flock as native_flock
    return native_flock(descriptor, operation)
