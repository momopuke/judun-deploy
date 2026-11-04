#!/usr/bin/env python3
"""SC VPS Rescue v7 - cgroup throttling and CPU/IO/memory contention probe.

Uses kernel PSI, cgroup v2 cpu.stat (interval deltas), host CPU and runqueue counters.
A conservatively gated, runtime-only browser quota probe may be attempted. No
recordings, Docker containers, passwords, URLs, stream keys, or app state read.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import SC_VPS_Base_ReadOnly as v5

VERSION = "7.0.0"
STATE = Path("/var/lib/sc-vps-rescue-v7")
BROWSER = v5.BROWSER
FWD = v5.FORWARDER
PROBE_TARGET = 30.0
WATCH_UNITS = (
    BROWSER, FWD, "stripchat-guard.service", "line-openchat-guard.service",
    "strip-recovery-watchdog.service", "advisor.service", "judun-deploy.service",
    "strip-size-rotator.service", "strip-rec-audit.service", "strip-media-web.service",
)

class RescueFailure(Exception):
    pass


def read_file(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


def int_kv(body):
    out = {}
    for line in body.splitlines():
        a = line.split()
        if len(a) == 2 and a[1].isdigit():
            out[a[0]] = int(a[1])
    return out


def psi_info(body):
    result = {}
    for line in body.splitlines():
        a = line.split()
        if not a or a[0] not in ("some", "full"):
            continue
        vals = {}
        for token in a[1:]:
            if "=" not in token: continue
            key, raw = token.split("=", 1)
            if key not in ("avg10", "avg60", "avg300", "total"): continue
            try: vals[key] = int(raw) if key == "total" else float(raw)
            except ValueError: pass
        result[a[0]] = vals
    return result


def proc_cpu():
    line = next((x for x in read_file("/proc/stat").splitlines() if x.startswith("cpu ")), "")
    try:
        ints = [int(x) for x in line.split()[1:9]]
        if len(ints) < 8: return None
        # guest/guest_nice already included in user/nice. Do not double count them.
        return ints
    except ValueError:
        return None


def host_snapshot():
    raw = read_file("/proc/stat")
    load = read_file("/proc/loadavg").strip().split()
    stat = {}
    for line in raw.splitlines():
        arr = line.split()
        if len(arr) == 2 and arr[0] in ("procs_running", "procs_blocked"):
            try: stat[arr[0]] = int(arr[1])
            except ValueError: pass
    mem = {}
    for line in read_file("/proc/meminfo").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].endswith(":") and parts[1].isdigit():
            mem[parts[0].rstrip(":")] = int(parts[1])
    return {"cpu": proc_cpu(), "psi": {kind: psi_info(read_file("/proc/pressure/"+kind)) for kind in ("cpu", "memory", "io")},
            "procs_running": stat.get("procs_running"), "procs_blocked": stat.get("procs_blocked"),
            "load1": load[0] if load else "unknown", "runqueue": load[3] if len(load)>3 else "unknown",
            "mem_available_kib":mem.get("MemAvailable"), "swap_free_kib":mem.get("SwapFree")}


def safe_cgroup_path(value):
    # All paths must come from a live systemd ControlGroup or Docker init PID cgroup.
    # Never allow absolute file paths to escape /sys/fs/cgroup through traversal/symlinks.
    if not value.startswith("/") or "\x00" in value:
        return None
    parts = value.split("/")
    if ".." in parts or "." in parts or not all(re.fullmatch(r"[-A-Za-z0-9_.@:\\]*",part) for part in parts):
        return None
    root = Path("/sys/fs/cgroup").resolve()
    p = (root / value.lstrip("/")).resolve()
    if not p.is_relative_to(root): return None
    return p if p.is_dir() else None


def cgroup_for_pid(pid):
    if not isinstance(pid,int) or pid<=1: return None
    for line in read_file(f"/proc/{pid}/cgroup").splitlines():
        if line.startswith("0::"):
            return safe_cgroup_path(line[3:])
    return None


def observed_cgroups():
    groups = {}
    for unit in WATCH_UNITS:
        rc, out, _ = v5.run("systemctl", "show", "-p", "ControlGroup", "--value", unit, timeout=8)
        if rc == 0:
            p = safe_cgroup_path(out.strip())
            if p: groups[unit] = p
    # Docker inspection exposes only PID, running state and ID (no sensitive env/ports).
    for name in v5.REQUIRED_CONTAINERS:
        rc, out, _ = v5.run("docker", "inspect", "--format", "{{.State.Pid}}|{{.State.Running}}", name, timeout=8)
        a = out.split("|") if rc==0 else []
        if len(a)==2 and a[0].isdigit() and a[1]=="true":
            p = cgroup_for_pid(int(a[0]))
            if p: groups["docker:"+name] = p
    return groups


def group_snapshot(groups):
    return {name:{"cpu_stat":int_kv(read_file(p/"cpu.stat")),
                  "cpu_max":read_file(p/"cpu.max").strip()[:40],
                  "cpu_psi":psi_info(read_file(p/"cpu.pressure")),
                  "memory_psi":psi_info(read_file(p/"memory.pressure")),
                  "io_psi":psi_info(read_file(p/"io.pressure")),
                  "pids_current":read_file(p/"pids.current").strip()[:30]}
            for name,p in groups.items()}


def psi_delta(before, after, kind="some"):
    x=before.get(kind,{}).get("total")
    y=after.get(kind,{}).get("total")
    return None if x is None or y is None or y<x else y-x


def delta_percent(delta_us, seconds):
    return None if delta_us is None or seconds<=0 else round(100*delta_us/(seconds*1e6),2)


def sample(groups, duration=4.0):
    t0=time.monotonic()
    h0=host_snapshot(); g0=group_snapshot(groups)
    time.sleep(duration)
    h1=host_snapshot(); g1=group_snapshot(groups)
    secs=time.monotonic()-t0
    usage={}
    if h0["cpu"] and h1["cpu"]:
        diff=[max(0,b-a) for a,b in zip(h0["cpu"],h1["cpu"])]
        all_ticks=sum(diff)
        if all_ticks>0:
            usage={"productive_pct":round(100*sum(diff[i] for i in (0,1,2,5,6))/all_ticks,2),
                   "steal_pct":round(100*diff[7]/all_ticks,2),
                   "idle_pct":round(100*diff[3]/all_ticks,2),
                   "iowait_pct":round(100*diff[4]/all_ticks,2)}
    pressure={kind:{"some_avg10":h1["psi"][kind].get("some",{}).get("avg10"),
                    "some_interval_pct":delta_percent(psi_delta(h0["psi"][kind],h1["psi"][kind]),secs),
                    "full_avg10":h1["psi"][kind].get("full",{}).get("avg10"),
                    "full_interval_pct":delta_percent(psi_delta(h0["psi"][kind],h1["psi"][kind],"full"),secs)}
              for kind in ("cpu","memory","io")}
    by_group={}
    for name,old in g0.items():
        current=g1.get(name, {})
        o=old["cpu_stat"];n=current.get("cpu_stat",{})
        d=lambda k: n.get(k,0)-o.get(k,0) if k in n and k in o and n[k]>=o[k] else None
        periods=d("nr_periods"); throttled=d("nr_throttled")
        by_group[name]={"cpu_max":current.get("cpu_max", ""),
                        "usage_pct_one_core":delta_percent(d("usage_usec"),secs),
                        "throttled_periods":throttled,"periods":periods,
                        "throttle_ratio_pct":round(100*throttled/periods,2) if periods and throttled is not None else None,
                        "throttled_usec_delta":d("throttled_usec"),
                        "cpu_pressure_some_pct":delta_percent(psi_delta(old["cpu_psi"],current.get("cpu_psi",{})),secs),
                        "cpu_pressure_full_pct":delta_percent(psi_delta(old["cpu_psi"],current.get("cpu_psi",{}),"full"),secs),
                        "pids_current":current.get("pids_current", "")}
    return {"duration_s":round(secs,2),"usage":usage,"pressure":pressure,
            "load1":h1["load1"],"runqueue":h1["runqueue"],
            "procs_running":h1["procs_running"],"procs_blocked":h1["procs_blocked"],
            "mem_available_mib":round(h1["mem_available_kib"]/1024,1) if h1["mem_available_kib"] is not None else None,
            "swap_free_mib":round(h1["swap_free_kib"]/1024,1) if h1["swap_free_kib"] is not None else None,
            "groups":by_group}


