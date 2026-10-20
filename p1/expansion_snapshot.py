"""Integration candidate: tiny atomic event snapshot for expansion status.

The production handler is NOT modified by this module. The controller should
publish only after a committed/proven checkpoint; GET health should read this
file rather than traverse run files or parse entire formal evidence bundles.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile
import time

MAX_BYTES = 8192
STATUS_VALUES = {"running", "idle", "paused", "failed", "completed"}
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
    if status not in STATUS_VALUES:
        raise ValueError("invalid expansion state")
    payload = {"schema": SCHEMA, "status": status,
               "updated_at": updated_at or utc_now(),
               "last_progress_at": data.get("last_progress_at") or updated_at or utc_now()}
    for key in ALLOWED_COUNTS:
        val = data.get(key, 0)
        if not isinstance(val, int) or isinstance(val, bool) or val < 0:
            raise ValueError("invalid count: " + key)
        payload[key] = val
    for key in ALLOWED_TEXT:
        val = str(data.get(key) or "")[:70]
        payload[key] = val
    payload["checkpoint_verified"] = data.get("checkpoint_verified") is True
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized status snapshot")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=str(target.parent), prefix=".expansion.", suffix=".tmp", delete=False) as f:
            temp_name = f.name
            f.write(raw)
            f.flush()
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
    if not isinstance(stale_after, int) or stale_after < 1:
        raise ValueError("stale_after must be positive")
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("snapshot too large")
        p = json.loads(raw.decode("utf-8"))
        if p.get("schema") != SCHEMA or p.get("status") not in STATUS_VALUES:
            raise ValueError("invalid snapshot schema")
        last = _parse_time(p["last_progress_at"])
        age = max(0, int((now_epoch if now_epoch is not None else time.time()) - last))
        state = p["status"]
        observed = "progress_stale" if state == "running" and age > stale_after else state
        return {
            "status": observed,
            "last_known_status": state,
            "last_progress_age_seconds": age,
            "last_progress_at": p["last_progress_at"],
            "updated_at": p["updated_at"],
            "phase": p.get("phase", ""),
            **{k: p[k] for k in ALLOWED_COUNTS},
            "checkpoint_verified": p.get("checkpoint_verified") is True,
            "automatic_restart_permitted": False,
        }
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        return {"status": "unknown", "reason": "snapshot_missing_or_invalid",
                "automatic_restart_permitted": False}
