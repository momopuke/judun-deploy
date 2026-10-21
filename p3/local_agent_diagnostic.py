"""On-VPS JUDUN pull-agent READ-ONLY diagnostic, for trusted operators.

No systemctl start/stop, no deployment, no credential reads beyond safe
non-secret config fields, no source/database mutation. Do not publish raw logs.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

CONFIG = Path("/opt/judun-autodeploy/config.env")
SERVICE = "judun-autodeploy.service"
TIMER = "judun-autodeploy.timer"
STATE = Path("/opt/judun-autodeploy/state.env")
SAFE_CONFIG = frozenset({"REPO", "BRANCH", "CHANNEL", "CHANNEL_SIG"})
ALLOWED_VALUE = re.compile(r"^[A-Za-z0-9._/-]{1,160}$")
EVENT_MARKERS = {
    "signature_failure": "Channel signature verification failed",
    "source_download_failure": "Could not download encrypted payload",
    "encrypted_payload_sha_mismatch": "Encrypted payload SHA256 mismatch",
    "base_artifact_mismatch": "Base artifact mismatch",
    "local_app_unavailable": "Local /health/build is unavailable",
    "release_already_processed": "Release already processed",
    "success": "[SUCCESS] Auto-deployed and verified",
    "rollback": "[ROLLBACK]",
    "release_apply_failure": "apply.sh returned rc=",
    "target_health_failure": "Target build did not become healthy",
    "network_unavailable": "Auto-deploy channel is not available",
    "lock_busy": "Another auto-deploy check is already running",
}


def run_status(*args: str) -> str:
    try:
        x = subprocess.run(args, capture_output=True, text=True, timeout=6, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "UNAVAILABLE"
    value = x.stdout.strip().splitlines()
    result = value[0].strip() if value else ""
    return result if result in {
        "active", "inactive", "failed", "activating", "deactivating",
        "enabled", "disabled", "static", "masked",
    } else "UNAVAILABLE"


def config_summary(text: str) -> dict:
    # Parse only known non-secret literal keys; never 'source' a shell config.
    found = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in SAFE_CONFIG and ALLOWED_VALUE.fullmatch(value):
            found[key] = value
    return found


def classify_logs(raw: str) -> dict:
    # Never export raw systemd log lines (may include private paths/errors).
    lines = raw.splitlines()[-250:]
    return {key: sum(token in line for line in lines)
            for key, token in EVENT_MARKERS.items()}


# Examine chronological event order, not just counts. A stale signature failure
# may precede a successful run; the converse can also happen. Output only a
# fixed event name, never a raw journal line or its secrets.
OBSERVED_EVENT_KEYS = (
    "signature_failure", "source_download_failure",
    "encrypted_payload_sha_mismatch", "base_artifact_mismatch",
    "local_app_unavailable", "release_apply_failure",
    "target_health_failure", "network_unavailable", "rollback",
    "success", "release_already_processed", "lock_busy",
)


def latest_agent_event(raw: str) -> str:
    latest = "NONE"
    for line in raw.splitlines()[-250:]:
        for name in OBSERVED_EVENT_KEYS:
            if EVENT_MARKERS[name] in line:
                latest = name
                break
    return latest


def collect() -> dict:
    info = {
        "schema": "judun.p3.local-agent-diagnostic.v1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "LOCAL_READ_ONLY",
        "agent_installed": CONFIG.is_file(),
        "timer_enabled": run_status("systemctl", "is-enabled", TIMER),
        "timer_active": run_status("systemctl", "is-active", TIMER),
        "service_active": run_status("systemctl", "is-active", SERVICE),
        "service_ever_successful": "UNKNOWN",
        "config": {},
        "local_version": "NOT_VERIFIED",
        "agent_log_categories": {},
        "agent_last_observed_event": "NONE",
        "no_vps_changes": True,
        "service_success_observed_in_sample": False,
        "pull_agent_required_for_https_v3": False,
    }
    if CONFIG.is_file():
        try:
            # Configuration might contain secrets; only safe fields leave memory.
            info["config"] = config_summary(CONFIG.read_text("utf-8")[:4096])
        except (OSError, UnicodeError):
            pass
    try:
        p = subprocess.run(
            ["journalctl", "-u", SERVICE, "-n", "250", "--no-pager", "--output=cat", "-q"],
            capture_output=True, text=True, timeout=8, check=False,
        )
        if p.returncode == 0:
            # The journal is chronological; keep the newest bounded bytes.
            # Prefix truncation can hide the latest run if the sampled
            # journal is unusually verbose, causing stale failures to win.
            safe_window = p.stdout[-150000:]
            info["agent_log_categories"] = classify_logs(safe_window)
            info["agent_last_observed_event"] = latest_agent_event(safe_window)
            # The bounded journal can only prove a success marker was
            # observed in its sample; do not imply all-time success.
            observed = info["agent_log_categories"].get("success", 0) > 0
            info["service_success_observed_in_sample"] = observed
            info["service_ever_successful"] = ("OBSERVED_IN_RECENT_SAMPLE"
                                               if observed else "UNKNOWN")
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        with urlopen("http://127.0.0.1:8000/health/build", timeout=5) as response:
            data = json.loads(response.read(65537))
        version = data.get("display_version") or data.get("version")
        artifact = data.get("artifact_id")
        if (isinstance(version, str) and
            re.fullmatch(r"v?\d+\.\d+\.\d+", version) and
            isinstance(artifact, str) and
            re.fullmatch(r"JUDUN-[A-Za-z0-9._-]{1,100}", artifact) and
            artifact.startswith("JUDUN-" + version.removeprefix("v") + "-")):
            info["local_version"] = {"display_version": version, "artifact_id": artifact}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    info["diagnostic"] = diagnose(info)
    return info


def diagnose(info: dict) -> str:
    if not info.get("agent_installed"):
        return "AGENT_NOT_INSTALLED_OR_CONFIG_MISSING"
    if info.get("timer_enabled") != "enabled" or info.get("timer_active") != "active":
        return "AGENT_TIMER_NOT_ENABLED_OR_INACTIVE"
    counts = info.get("agent_log_categories", {})
    # This describes only the last recognizable event in the sampled journal
    # window, not proof of the *current* release or source-tree integrity.
    latest = info.get("agent_last_observed_event", "NONE")
    most_recent = {
        "signature_failure": "SIGNED_CHANNEL_VERIFICATION_FAILED",
        "encrypted_payload_sha_mismatch": "RECORDED_ENCRYPTED_PAYLOAD_SHA_MISMATCH",
        "base_artifact_mismatch": "RECORDED_BASE_ARTIFACT_MISMATCH",
        "source_download_failure": "RECORDED_CHANNEL_OR_PAYLOAD_DOWNLOAD_FAILURE",
        "network_unavailable": "RECORDED_CHANNEL_OR_PAYLOAD_DOWNLOAD_FAILURE",
        "release_apply_failure": "RECORDED_DEPLOY_OR_HEALTH_FAILURE",
        "target_health_failure": "RECORDED_DEPLOY_OR_HEALTH_FAILURE",
        "local_app_unavailable": "RECORDED_LOCAL_APP_UNAVAILABLE",
        "rollback": "RECORDED_ROLLBACK_LIVE_STATE_UNKNOWN",
        "success": "RECORDED_SUCCESS_BUT_LIVE_UNVERIFIED",
        "release_already_processed": "RECORDED_ALREADY_PROCESSED_LIVE_UNVERIFIED",
        "lock_busy": "RECORDED_AGENT_LOCK_BUSY_LIVE_UNVERIFIED",
    }
    if latest in most_recent:
        return most_recent[latest]
    if counts.get("signature_failure"):
        return "SIGNED_CHANNEL_VERIFICATION_FAILED"
    if counts.get("encrypted_payload_sha_mismatch"):
        return "RECORDED_ENCRYPTED_PAYLOAD_SHA_MISMATCH"
    if counts.get("base_artifact_mismatch"):
        return "RECORDED_BASE_ARTIFACT_MISMATCH"
    if counts.get("network_unavailable") or counts.get("source_download_failure"):
        return "RECORDED_CHANNEL_OR_PAYLOAD_DOWNLOAD_FAILURE"
    if counts.get("release_apply_failure") or counts.get("target_health_failure"):
        return "RECORDED_DEPLOY_OR_HEALTH_FAILURE"
    return "AGENT_RUN_STATE_NOT_PROVEN_BY_STATIC_CHECKS"


def main() -> int:
    print("P3_LOCAL_AGENT_READONLY_DIAGNOSTIC",
          json.dumps(collect(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
