"""Integration candidate: tiny atomic event snapshot for expansion status.

The production handler is NOT modified by this module. The controller should
publish only after a committed/proven checkpoint; GET health should read this
file rather than traverse run files or parse entire formal evidence bundles.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import os
import tempfile
import time

from snapshot_write_lock import exclusive_status_lock

MAX_BYTES = 8192
STATUS_VALUES = {"running", "idle", "paused", "failed", "completed"}
# Public status deliberately uses a closed set of generic phase labels.
# No arbitrary URL, exception, credential or internal filesystem path leaks.
PUBLIC_PHASES = frozenset({
    "queued", "discover", "fetch", "parse", "validate", "qa",
    "stage", "checkpoint", "import", "finalize", "idle", "waiting",
    "paused", "complete", "retry", "sleep", "other",
})
ALLOWED_COUNTS = ("rounds_completed", "validated_total", "formal_records_added_total")
ALLOWED_TEXT = ("phase",)
SCHEMA = "judun.expansion.public-status.v1"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_event_snapshot(path: str | Path, data: dict, *, updated_at: str | None = None):
    """Atomic overwrite; never writes full logs, source URLs, secrets or personal data."""
    if not isinstance(data, dict):
        raise ValueError("expected summary mapping")
    status = data.get("status")
    if not isinstance(status, str) or status not in STATUS_VALUES:
        raise ValueError("invalid expansion state")
    stamp = updated_at or utc_now()
    progress = data.get("last_progress_at")
    # Neither a heartbeat NOR a non-running terminal-state event proves a
    # fresh completed-work checkpoint. Never synthesize progress timestamps.
    # The trusted controller must provide the last genuine progress event.
    stamp_epoch = _parse_time(stamp)
    # Reject poisoned future events at WRITE time. Otherwise one bad event
    # makes every subsequent honest event look like clock rollback.
    if stamp_epoch > time.time() + 60:
        raise ValueError("snapshot timestamp is in the future")
    if progress is not None:
        progress_epoch = _parse_time(progress)
        if progress_epoch > stamp_epoch + 60:
            raise ValueError("progress timestamp newer than snapshot")
    payload = {"schema": SCHEMA, "status": status,
               "updated_at": stamp,
               "last_progress_at": progress}
    for key in ALLOWED_COUNTS:
        val = data.get(key, 0)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            raise ValueError("invalid count: " + key)
        payload[key] = val
    for key in ALLOWED_TEXT:
        val = data.get(key)
        payload[key] = val if isinstance(val, str) and val in PUBLIC_PHASES else "other"
    payload["checkpoint_verified"] = data.get("checkpoint_verified") is True
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized status snapshot")
    target = Path(path)
    # The same advisory lock must cover BOTH read/compare and atomic replace.
    # On the Linux VPS this also serializes concurrent controller processes.
    with exclusive_status_lock(target):
        # Reject sequential clock rollback from an older controller event.
        # Atomic replacement alone prevents partial bytes, not stale overwrites.
        # The live controller still needs a single-writer/serialized-event policy
        # for concurrent workers; this preflight is not a distributed lock.
        try:
            with target.open("rb") as previous_file:
                previous_bytes = previous_file.read(MAX_BYTES + 1)
            if len(previous_bytes) <= MAX_BYTES:
                previous = json.loads(previous_bytes.decode("utf-8"))
                if isinstance(previous, dict) and previous.get("schema") == SCHEMA:
                    try:
                        previous_time = _parse_time(previous.get("updated_at"))
                    except (TypeError, ValueError):
                        previous_time = None
                    if previous_time is not None:
                        if _parse_time(stamp) < previous_time:
                            raise ValueError("snapshot timestamp regressed")
                        # These counters are cumulative within one controller
                        # lineage. An older round must never erase committed
                        # totals, even if it carries a newer heartbeat timestamp.
                        # A genuine epoch reset must use a new trusted snapshot
                        # lineage rather than silently decreasing these totals.
                        old_progress = previous.get("last_progress_at")
                        if old_progress is not None and progress is not None:
                            try:
                                if _parse_time(progress) < _parse_time(old_progress):
                                    raise ValueError("progress timestamp regressed")
                            except (TypeError, ValueError) as exc:
                                if str(exc) == "progress timestamp regressed":
                                    raise
                                # An invalid old clock must not be trusted to
                                # block a fresh, validated controller record.
                                pass
                        for count_key in ALLOWED_COUNTS:
                            prior_count = previous.get(count_key)
                            if (type(prior_count) is int and prior_count >= 0
                                    and payload[count_key] < prior_count):
                                raise ValueError("cumulative count regressed: " + count_key)
        except FileNotFoundError:
            pass
        except (UnicodeError, json.JSONDecodeError, TypeError, KeyError):
            # The prior file is corrupt; permit replacing it with a validated
            # small new snapshot. Other file read failures remain visible.
            pass
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=str(target.parent), prefix=".expansion.", suffix=".tmp", delete=False) as f:
                temp_name = f.name
                f.write(raw)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, target)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    return payload


def _parse_time(value):
    if not isinstance(value, str):
        raise ValueError("invalid timestamp")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("missing timezone")
    return dt.timestamp()


def read_public_snapshot(path: str | Path, *, now_epoch: float | None = None, stale_after: int = 180):
    """O(1) bounded read and stale warning; never restarts workers or replays data."""
    if type(stale_after) is not int or stale_after < 1:
        raise ValueError("stale_after must be a positive integer")
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("snapshot too large")
        p = json.loads(raw.decode("utf-8"))
        if not isinstance(p, dict):
            raise ValueError("invalid snapshot shape")
        if (p.get("schema") != SCHEMA
                or not isinstance(p.get("status"), str)
                or p["status"] not in STATUS_VALUES):
            raise ValueError("invalid snapshot schema")
        now = now_epoch if now_epoch is not None else time.time()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise ValueError("invalid observation clock")
        snapshot_time = _parse_time(p["updated_at"])
        if snapshot_time > now + 60:
            raise ValueError("future-dated status snapshot")
        snapshot_age = max(0, int(now - snapshot_time))
        state = p["status"]
        progress_stamp = p.get("last_progress_at")
        last = _parse_time(progress_stamp) if progress_stamp is not None else None
        if last is not None and last > now + 60:
            raise ValueError("future-dated progress")
        age = max(0, int(now - last)) if last is not None else None
        if last is not None and last > snapshot_time + 60:
            raise ValueError("progress timestamp later than snapshot")
        # A stale state file is no longer proof that an old idle/completed
        # controller is alive. Preserve what it *last said* separately.
        if snapshot_age > stale_after:
            observed = "progress_stale" if state == "running" and age is not None and age > stale_after else "snapshot_stale"
        elif state == "running" and age is None:
            observed = "progress_unknown"
        elif state == "running" and age > stale_after:
            observed = "progress_stale"
        elif state == "completed" and p.get("checkpoint_verified") is not True:
            observed = "completion_unverified"
        else:
            observed = state
        for count in ALLOWED_COUNTS:
            number = p[count]
            if type(number) is not int or number < 0:
                raise ValueError("invalid snapshot count")
        phase = p.get("phase", "")
        if not isinstance(phase, str) or phase not in PUBLIC_PHASES:
            raise ValueError("invalid status phase")
        return {
            "status": observed,
            "last_known_status": state,
            "last_progress_age_seconds": age,
            "last_progress_at": progress_stamp,
            "updated_at": p["updated_at"],
            "snapshot_age_seconds": snapshot_age,
            "snapshot_stale": snapshot_age > stale_after,
            "status_confident": (
                snapshot_age <= stale_after and observed not in (
                    "progress_unknown", "progress_stale", "completion_unverified"
                )
            ),
            "phase": phase,
            **{k: p[k] for k in ALLOWED_COUNTS},
            "checkpoint_verified": p.get("checkpoint_verified") is True,
            "automatic_restart_permitted": False,
        }
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        return {"status": "unknown", "reason": "snapshot_missing_or_invalid",
                "automatic_restart_permitted": False}
