"""POSIX interprocess serialization for tiny public expansion snapshots.

Used only on the Linux VPS candidate controller path. The lock file is
intentionally persistent: unlinking an in-use flock inode would allow two
writers to acquire different locks for the same snapshot. No background
monitor, worker restart or data import occurs here.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import fcntl
import math
import os
import stat
import time


@contextmanager
def exclusive_status_lock(snapshot_path: str | Path, *, timeout_seconds: float = 0.75):
    """Lock exactly one snapshot pathname with bounded waiting.

    The caller MUST hold this lock around BOTH the prior snapshot check and
    os.replace(). A timeout is an explicit write failure, never an excuse to
    replace a newer committed snapshot. On non-POSIX runtimes this module
    intentionally fails at import rather than silently offering no lock.
    """
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0 or timeout_seconds > 5):
        raise ValueError("lock timeout must be finite and at most 5 seconds")
    target = Path(snapshot_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Never block in open() against a malicious named pipe at the lock path.
    flags = os.O_CREAT | os.O_RDWR | os.O_NONBLOCK
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(target) + ".lock", flags, 0o600)
    acquired = False
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_nlink != 1):
            raise ValueError("untrusted expansion lock file")
        # Existing lockfiles might have been created with permissive modes.
        os.fchmod(fd, 0o600)
        deadline = time.monotonic() + timeout_seconds
        while not acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError as error:
                if time.monotonic() >= deadline:
                    raise TimeoutError("snapshot writer busy") from error
                time.sleep(0.025)
        yield
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
