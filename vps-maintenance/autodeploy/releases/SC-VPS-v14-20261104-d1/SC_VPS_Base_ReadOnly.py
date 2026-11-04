#!/usr/bin/env python3
"""SC VPS Rescue v5: fail-closed diagnostics + narrowly-scoped, reversible fixes.

No remote connection or credential handling. Only execute on the intended VPS.
Never stops/restarts Docker, Recorder, gateway, or Line Guard.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time

VERSION = "5.0.0"
STATE = Path("/var/lib/sc-vps-rescue-v5")
BROWSER = "stripchat-browser-desktop.service"
FORWARDER = "livevpn-stripchat-forward.service"
REQUIRED_CONTAINERS = ("stripchat-recorder", "stripchat-gateway")
UNITS = (BROWSER, FORWARDER, "line-openchat-guard.service", "stripchat-guard.service")
MIN_RESTART_SEC = 60.0
TARGET_BROWSER_PERCENT = 20.0
SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.@-]+$")


class RescueError(Exception):
    pass


def run(*argv, timeout=15):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, "", type(e).__name__


def require_root():
    if os.geteuid() != 0:
        raise RescueError("Root is required; run on the VPS as root")
    if not Path("/run/systemd/system").exists():
        raise RescueError("Systemd host not detected; aborting")
    if not shutil.which("docker") or not shutil.which("systemctl"):
        raise RescueError("Missing docker/systemctl; aborting")


def get_prop(unit, key):
    assert SAFE_NAME.fullmatch(unit) and SAFE_NAME.fullmatch(key)
    rc, out, _ = run("systemctl", "show", "--value", "-p", key, unit)
    return out if rc == 0 else ""


def unit_state(unit):
    # One systemctl process per unit; important on a CPU-starved 1-vCPU droplet.
    keys = ("LoadState", "ActiveState", "SubState", "MainPID", "CPUQuotaPerSecUSec",
            "CPUWeight", "NRestarts", "ExecMainStatus", "RestartUSec")
    opts = tuple(part for key in keys for part in ("-p", key))
    rc, out, _ = run("systemctl", "show", "--no-pager", *opts, unit, timeout=12)
    values = dict(line.split("=", 1) for line in out.splitlines() if "=" in line) if rc == 0 else {}
    return {key: values.get(key, "") for key in keys}


def parse_timespan(s):
    """Convert systemd human timespans to seconds; None means infinity/unknown."""
    if not s or s.strip().lower() in ("infinity", "n/a", "unset", "[not set]"):
        return None
    # Unitless integer on systemctl show is microseconds.
    if re.fullmatch(r"\d+", s.strip()):
        return int(s.strip()) / 1_000_000
    units = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6,
             "ms": 0.001, "s": 1, "sec": 1, "min": 60, "h": 3600, "d": 86400}
    parts = re.findall(r"(\d+(?:\.\d+)?)\s*(ns|us|µs|ms|sec|min|s|h|d)(?![a-z])", s, re.I)
    residual = re.sub(r"\d+(?:\.\d+)?\s*(?:ns|us|µs|ms|sec|min|s|h|d)(?![a-z])", "", s, flags=re.I)
    if not parts or residual.strip():
        return None
    return sum(float(num) * units[unit.lower()] for num, unit in parts)


def cpu_quota_percent(s):
    if s.strip().lower() == "infinity":
        return float("inf")
    sec = parse_timespan(s)
    return None if sec is None else 100.0 * sec


def docker_state(name):
    # Never use shell, no Docker config/env output.
    rc, out, _ = run("docker", "inspect", "--format", "{{.Id}}|{{.State.Running}}|{{.State.Status}}", name)
    if rc != 0:
        return {"exists": False, "running": False, "id": "", "status": "missing"}
    parts = out.split("|")
    if len(parts) != 3:
        return {"exists": False, "running": False, "id": "", "status": "unparseable"}
    return {"exists": True, "running": parts[1] == "true", "id": parts[0], "status": parts[2]}


def cpu_pressure():
    try:
        line = next(x for x in Path("/proc/pressure/cpu").read_text().splitlines() if x.startswith("some "))
        return float(re.search(r"avg10=([0-9.]+)", line).group(1))
    except (OSError, StopIteration, AttributeError, ValueError):
        return None


def top_processes():
    rc, out, _ = run("ps", "-eo", "pid,ppid,comm,%cpu,%mem", "--sort=-%cpu", timeout=10)
    return out.splitlines()[:14] if rc == 0 else []


def user_not_found_counts():
    # Only collect sanitized identifiers from bounded last-hour journal sample.
    rc, out, _ = run("journalctl", "-u", "strip-recovery-watchdog.service",
                     "--since", "1 hour ago", "-n", "400", "--no-pager", "-o", "cat", timeout=12)
    if rc != 0:
        return {"source_available": False, "sampled_lines": 0, "matches": None, "sampled_account_names": []}
    lines = out.splitlines()
    count = 0
    names = set()
    for line in lines:
        if "User not found" not in line:
            continue
        count += 1
        found = re.search(r"User not found\s*[:\-]?\s*(?:for\s+)?(?:user\s+)?[\"']?([_a-zA-Z0-9-]{2,40})", line)
        if found and found.group(1).lower() not in ("user", "found", "error"):
            names.add(found.group(1))
    return {"source_available": True, "sampled_lines": len(lines), "matches": count,
            "sampled_account_names": sorted(names)[:20], "sampling_limit": 400}


def snapshot():
    up_rc, uptime, _ = run("uptime", timeout=5)
    free_rc, free, _ = run("free", "-m", timeout=5)
    df_rc, df, _ = run("df", "-P", "-h", "/", timeout=5)
    return {"at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "uptime": uptime if up_rc == 0 else "unavailable",
            "memory": free if free_rc == 0 else "unavailable",
            "disk": df if df_rc == 0 else "unavailable",
            "cpu_pressure_avg10": cpu_pressure(),
            "containers": {name: docker_state(name) for name in REQUIRED_CONTAINERS},
            "units": {name: unit_state(name) for name in UNITS},
            "top_processes": top_processes(),
            "missing_user_journal": user_not_found_counts()}


def docker_protected(before, after):
    for name in REQUIRED_CONTAINERS:
        x, y = before["containers"][name], after["containers"][name]
        if not x["running"] or not y["running"] or x["id"] != y["id"]:
            return False
    return True


def write_json(path, content):
    # Separate JSON snapshot; mode 0600, no secrets collected.
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump(content, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


