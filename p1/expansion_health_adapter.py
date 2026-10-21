"""Lightweight, read-only public expansion-health response adapter.

Candidate integration contract; it is not attached to a live FastAPI route.
FastAPI handlers may return this mapping as JSON from their existing GET
endpoint. The only file IO is a bounded single read of the atomic snapshot.
Do not make this endpoint an automatic process restart or import trigger.
"""
from __future__ import annotations

from pathlib import Path

from expansion_snapshot import read_public_snapshot

DISPLAY_STATES = frozenset({
    "running", "idle", "paused", "failed", "completed",
    "progress_unknown", "progress_stale", "snapshot_stale",
    "completion_unverified", "unknown",
})


def public_expansion_health(
    snapshot_path: str | Path, *, now_epoch: float | None = None,
    stale_after: int = 180,
) -> dict:
    """Describe observed progress honestly, without implying engine liveness.

    Unknown/stale snapshots must lead to human checkpoint inspection,
    never force worker or DB changes. 'healthy' refers ONLY to observation
    freshness, not web-server readiness or successful data import.
    """
    observation = read_public_snapshot(
        snapshot_path, now_epoch=now_epoch, stale_after=stale_after
    )
    state = observation.get("status")
    if state not in DISPLAY_STATES:
        state = "unknown"
    if state in {"unknown", "snapshot_stale", "progress_unknown", "progress_stale"}:
        action = "investigate_checkpoint_and_worker"
    elif state == "completion_unverified":
        action = "verify_formal_checkpoint"
    elif state == "failed":
        action = "inspect_error_and_recovery_safety"
    else:
        action = "none"

    return {
        "schema": "judun.expansion.health-summary.v1",
        "expansion_state": state,
        "last_known_status": observation.get("last_known_status"),
        "observation_trustworthy": observation.get("status_confident") is True,
        "snapshot_age_seconds": observation.get("snapshot_age_seconds"),
        "last_progress_age_seconds": observation.get("last_progress_age_seconds"),
        "phase": observation.get("phase") if state != "unknown" else None,
        "rounds_completed": observation.get("rounds_completed"),
        "validated_total": observation.get("validated_total"),
        "formal_records_added_total": observation.get("formal_records_added_total"),
        "checkpoint_verified": observation.get("checkpoint_verified") is True,
        "manual_next_action": action,
        "automatic_restart_permitted": False,
        "formal_import_permitted": False,
    }
