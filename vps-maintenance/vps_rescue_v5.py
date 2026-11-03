#!/usr/bin/env python3
"""SC VPS one-pass v5: pinned diagnostics + conditional FFmpeg restart backoff.
No browser/recorder/LINE/JUDUN stop, restart, credential access or log upload.
"""
from __future__ import annotations
import datetime as dt
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

DIAG_URL = ("https://raw.githubusercontent.com/momopuke/judun-deploy/"
            "35ad4f51ca6eb100b009441ff0c27638c014bc08/"
            "vps-maintenance/diagnostic_v1.py")
DIAG_SHA = "235acabd79067a650dbfc9c3fab342735f3aa3c3"
STATE = Path("/var/lib/sc-vps-maintenance/state.json")
REPORT = Path("/var/lib/sc-vps-maintenance/v5-final-report.json")
CONF = Path("/etc/systemd/system/livevpn-stripchat-forward.service.d/95-sc-vps-v5-backoff.conf")
BACKUPS = Path("/var/backups/sc-vps-maintenance")
SERVICE = "livevpn-stripchat-forward.service"
HEADER = "# SC-VPS-V5-MANAGED backoff\n"

class Blocked(Exception):
    pass

def git_sha(raw):
    return hashlib.sha1((f"blob {len(raw)}\0").encode()+raw).hexdigest()

def run(*args):
    try:
        p = subprocess.run(args,capture_output=True,text=True,timeout=20,check=False)
    except (OSError,subprocess.TimeoutExpired) as ex:
        raise Blocked("COMMAND_UNAVAILABLE_OR_TIMEOUT "+args[0]) from ex
    if p.returncode:
        raise Blocked("COMMAND_FAILED "+args[0]+" rc="+str(p.returncode))
    return p.stdout.strip()

def prop(service,key):
    return run("systemctl","show",service,"-p",key,"--value")

def to_seconds(x):
    x=x.strip()
    if x=="infinity": return math.inf
    scale={"us":0.000001,"ms":0.001,"s":1,"min":60,"h":3600,"d":86400}
    cursor=0
    val=0.
    for m in re.finditer(r"(\d+(?:\.\d+)?)(us|ms|min|s|h|d)",x):
        if x[cursor:m.start()].strip(): return None
        val+=float(m.group(1))*scale[m.group(2)]
        cursor=m.end()
    return val if cursor>0 and not x[cursor:].strip() else None

def atomic(path,raw,mode=0o600):
    if path.is_symlink(): raise Blocked("SYMLINK_TARGET")
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=".v5-",dir=str(path.parent))
    try:
        with os.fdopen(fd,"wb") as f:
            os.fchmod(f.fileno(),mode)
            f.write(raw);f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def load_diag():
    try:
        with urlopen(Request(DIAG_URL,headers={"User-Agent":"SC-VPS-v5/1"}),timeout=25) as r:
            raw=r.read(16000)
    except (OSError,TimeoutError) as ex:
        raise Blocked("PINNED_DIAGNOSTIC_FETCH_FAILED") from ex
    if git_sha(raw)!=DIAG_SHA: raise Blocked("PINNED_DIAGNOSTIC_SHA_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="v5diag-") as t:
        p=Path(t)/"diagnostic.py";p.write_bytes(raw)
        spec=importlib.util.spec_from_file_location("sc_vps_readonly_diag",p)
        module=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

def preflight():
    if os.geteuid()!=0: raise Blocked("ROOT_REQUIRED")
    if not STATE.is_file() or STATE.is_symlink() or STATE.stat().st_size>8192:
        raise Blocked("KNOWN_AGENT_STATE_MISSING")
    s=json.loads(STATE.read_text())
    if s.get("last_seq",0)<3 or s.get("status")!="applied":
        raise Blocked("KNOWN_AGENT_NOT_ENROLLED")
    if prop("stripchat-browser-desktop.service","LoadState")!="loaded":
        raise Blocked("BROWSER_UNIT_MISSING")
    return s

def assess_forwarder():
    if prop(SERVICE,"LoadState")!="loaded": return {"status":"SKIP_NO_FORWARDER"}
    p={k:prop(SERVICE,k) for k in ("ActiveState","SubState","RestartUSec","NRestarts","ExecMainStatus")}
    interval=to_seconds(p["RestartUSec"])
    if interval is None: return {"status":"SKIP_UNKNOWN_RESTART_DELAY","before":p}
    if not p["NRestarts"].isdigit() or not p["ExecMainStatus"].isdigit():
        return {"status":"SKIP_UNKNOWN_COUNTERS","before":p}
    if p["ActiveState"]!="activating" or p["SubState"]!="auto-restart" or int(p["NRestarts"])<1000 or int(p["ExecMainStatus"])==0:
        return {"status":"SKIP_NOT_CONFIRMED_STORM","before":p}
    if interval>=180: return {"status":"ALREADY_BACKOFF","before":p}
    return {"status":"ELIGIBLE","before":p}

def fix_forwarder(a):
    if a["status"]!="ELIGIBLE": return a
    if CONF.is_symlink(): return {**a,"status":"BLOCKED_SYMLINK_CONFIG"}
    old=CONF.read_bytes() if CONF.exists() else None
    if old is not None and not old.startswith(HEADER.encode()):
        return {**a,"status":"BLOCKED_EXISTING_CONFIG"}
    if shutil.disk_usage(CONF.parent.parent).free<64*1024*1024:
        return {**a,"status":"SKIP_LOW_DISK"}
    backup=None
    if old is not None:
        if BACKUPS.is_symlink(): return {**a,"status":"BLOCKED_BACKUP_SYMLINK"}
        backup=BACKUPS/("ffmpeg-v5-"+dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S")+".conf")
        atomic(backup,old)
    try:
        atomic(CONF,(HEADER+"[Service]\nRestartSec=180s\n").encode(),0o644)
        run("systemctl","daemon-reload")
        seconds=to_seconds(prop(SERVICE,"RestartUSec"))
        if seconds is None or seconds<180: raise Blocked("RESTART_DELAY_DID_NOT_APPLY")
        return {**a,"status":"BACKOFF_180S_APPLIED","after_delay":prop(SERVICE,"RestartUSec"),"backup":str(backup) if backup else None}
    except Exception:
        try:
            if old is None: CONF.unlink(missing_ok=True)
            else: atomic(CONF,old,0o644)
            run("systemctl","daemon-reload")
            return {**a,"status":"ROLLED_BACK"}
        except Exception:
            return {**a,"status":"ROLLBACK_FAILED"}

def digest(s):
    return {k:s[k] for k in ("timestamp_utc","host","host_cpu","cgroup","services","browser","forwarder","recorder_running","chromium_processes","findings")}

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--diagnose-only",action="store_true")
    a=ap.parse_args()
    with open("/run/sc-vps-v5.lock","w") as lock:
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as e:raise Blocked("ALREADY_RUNNING") from e
        agent=preflight()
        diag=load_diag()
        before=digest(diag.sample(5))
        assessment=assess_forwarder()
        action=assessment if a.diagnose_only else fix_forwarder(assessment)
        rounds=[]
        for i in range(5):
            s=digest(diag.sample(5))
            rounds.append(s)
            print(f"[ROUND {i+1}/5] PSI={s['host']['cpu_psi10']} LOAD={s['host']['loadavg']} "
                  f"CPU={s['host_cpu']} chromium={s['chromium_processes']}",flush=True)
        after=rounds[-1]
        issues=[]
        if after["services"].get("stripchat-browser-desktop.service")!="active":issues.append("BROWSER_NOT_ACTIVE")
        if after["services"].get("line-openchat-guard.service")!="active":issues.append("LINE_GUARD_NOT_ACTIVE")
        if after["services"].get("sc-vps-maintenance.timer")!="active":issues.append("MAINTENANCE_TIMER_NOT_ACTIVE")
        if not after["recorder_running"]:issues.append("RECORDER_NOT_RUNNING")
        if action.get("status")=="ROLLBACK_FAILED":issues.append("FFMPEG_ROLLBACK_FAILED")
        if any(s["host"]["cpu_psi10"] is None or s["host"]["cpu_psi10"]>=85 for s in rounds):
            issues.append("CPU_CONTENTION_REMAINS_HIGH")
        # These require live user-authorized streaming and moderation tests.
        issues+=["STRIPCHAT_REAL_MUTE_NOT_VERIFIED","RECORDING_OUTPUT_NOT_VERIFIED"]
        report={"schema":"sc-vps-v5/1","at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
                "sequence":agent["last_seq"],"before":before,"ffmpeg_action":action,
                "five_rounds":rounds,"status":"PARTIAL" if issues else "PASS",
                "outstanding":issues}
        atomic(REPORT,(json.dumps(report,ensure_ascii=False,indent=2)+"\n").encode())
        print("FFMPEG_ACTION",json.dumps(action,ensure_ascii=False))
        print("REPORT",str(REPORT))
        print("RESULT",report["status"],"OUTSTANDING",",".join(issues))
        return 3 if issues else 0

if __name__=="__main__":
    try:sys.exit(main())
    except (Blocked,OSError,KeyError,ValueError) as e:
        print("SC_VPS_V5_BLOCKED",str(e) if isinstance(e,Blocked) else type(e).__name__,file=sys.stderr)
        sys.exit(5)
