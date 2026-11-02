#!/usr/bin/env python3
"""SC VPS diagnostics v1. Read-only, bounded, no secrets, and does not mutate services."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

BASE = Path('/var/lib/sc-vps-maintenance')
REPORT = BASE / 'diagnostic-v1.json'
UNIT_BROWSER = 'stripchat-browser-desktop.service'
UNIT_LINE = 'line-openchat-guard.service'
UNIT_FORWARD = 'livevpn-stripchat-forward.service'
SERVICES = (UNIT_BROWSER, UNIT_LINE, UNIT_FORWARD, 'sc-vps-maintenance.timer')


def call(*args: str) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=7, check=False)
        if p.returncode == 0:
            return p.stdout.strip()[:200]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return 'unknown'


def psi(kind: str) -> float | None:
    try:
        s = Path('/proc/pressure', kind).read_text()[:512].splitlines()[0]
        match = re.search(r'\bavg10=(\d+(?:\.\d+)?)', s)
        return float(match.group(1)) if match else None
    except (OSError, IndexError, ValueError):
        return None


def proc_cpu() -> tuple[int, int, int] | None:
    try:
        line = Path('/proc/stat').read_text()[:256].splitlines()[0]
        x = [int(n) for n in line.split()[1:]]
        if not line.startswith('cpu ') or len(x) < 5:
            return None
        return sum(x), x[3], x[4]
    except (OSError, ValueError, IndexError):
        return None


def cgroup_cpu(name: str) -> dict[str, int] | None:
    path = Path('/sys/fs/cgroup/system.slice') / name / 'cpu.stat'
    try:
        rows = path.read_text()[:2000].splitlines()
        d = {x[0]: int(x[1]) for s in rows if len(x := s.split()) == 2}
        return {k: d[k] for k in ('usage_usec', 'nr_periods', 'nr_throttled', 'throttled_usec') if k in d}
    except (OSError, ValueError):
        return None


def delta(a: dict | None, b: dict | None) -> dict | None:
    if a is None or b is None:
        return None
    d = {k: max(0, b[k] - a[k]) for k in b if k in a}
    if 'nr_periods' in d and 'nr_throttled' in d and d['nr_periods'] > 0:
        d['throttle_ratio'] = round(d['nr_throttled'] / d['nr_periods'], 3)
    return d


def cpu_delta(a: tuple[int,int,int] | None,b: tuple[int,int,int] | None) -> dict | None:
    if a is None or b is None:
        return None
    total = b[0]-a[0]
    if total <= 0:
        return None
    return {
        'busy_percent':round(100*(1 - ((b[1]-a[1]) + (b[2]-a[2]))/total),1),
        'iowait_percent':round(100*(b[2]-a[2])/total,1),
    }


def classify(pressure: float | None, usage: dict | None, browser: dict | None, browser_active: str, io: float | None) -> list[str]:
    reasons = []
    if browser_active != 'active':
        reasons.append('BROWSER_NOT_ACTIVE_CHECK_GUARD')
    if browser and browser.get('throttle_ratio',0) >= .7:
        reasons.append('CHROMIUM_CGROUP_THROTTLED_DO_NOT_LOWER_CPU_LIMIT')
    if pressure is not None and pressure >= 85:
        reasons.append('HIGH_RUNNABLE_CPU_CONTENTION')
        if usage and usage['busy_percent'] >= 85:
            reasons.append('HOST_CPU_CAPACITY_CONSTRAINED')
    if io is not None and io >= 20:
        reasons.append('IO_WAIT_PRESSURE')
    if not reasons:
        reasons.append('NO_CLEAR_HIGH_PRESSURE_IN_SAMPLE')
    reasons.append('LIVE_MODERATION_NOT_VERIFIED')
    return reasons


def chromium_process_count() -> int | None:
    # Count process names only; do not read command lines, cookies or profile data.
    try:
        count = 0
        for p in Path('/proc').iterdir():
            if p.name.isdigit():
                try:
                    if (p / 'comm').read_text()[:32].strip() == 'chromium':
                        count += 1
                except (FileNotFoundError, ProcessLookupError, PermissionError):
                    pass
        return count
    except OSError:
        return None


def read_host() -> dict:
    try:
        load = [round(x,2) for x in os.getloadavg()]
    except OSError:
        load = []
    try:
        mem = Path('/proc/meminfo').read_text()[:4096]
        fields = dict(re.findall(r'^(MemAvailable|SwapFree|SwapTotal):\s+(\d+)',mem,re.M))
        memory = {k:int(v) for k,v in fields.items()}
    except OSError:
        memory = {}
    return {'loadavg':load, 'memory_kb':memory,'cpu_psi10':psi('cpu'),'io_psi10':psi('io')}


def sample(seconds: int=3) -> dict:
    services = {name:call('systemctl','show',name,'-p','ActiveState','--value') for name in SERVICES}
    browser_quota = call('systemctl','show',UNIT_BROWSER,'-p','CPUQuotaPerSecUSec','--value')
    browser_weight = call('systemctl','show',UNIT_BROWSER,'-p','CPUWeight','--value')
    fwd_restart_sec = call('systemctl','show',UNIT_FORWARD,'-p','RestartUSec','--value')
    fwd_restart_count = call('systemctl','show',UNIT_FORWARD,'-p','NRestarts','--value')
    recorder = call('docker','inspect','-f','{{.State.Running}}','stripchat-recorder')
    docker_id = call('docker','inspect','-f','{{.Id}}','stripchat-recorder')
    recorder_scope = f'docker-{docker_id}.scope' if re.fullmatch(r'[a-f0-9]{64}', docker_id) else '_missing_recorder_scope'
    group_names = {'browser': UNIT_BROWSER, 'recorder': recorder_scope}
    a0 = proc_cpu()
    a = {key:cgroup_cpu(name) for key,name in group_names.items()}
    time.sleep(seconds)
    b0 = proc_cpu()
    b = {key:cgroup_cpu(name) for key,name in group_names.items()}
    dc = {key:delta(a[key],b[key]) for key in group_names}
    host = read_host()
    used = cpu_delta(a0,b0)
    result = {
        'schema':'sc-vps-diagnostic/v1',
        'timestamp_utc': dt.datetime.now(dt.timezone.utc).isoformat(),
        'sampling_seconds':seconds,
        'host':host,'host_cpu':used,'cgroup':dc,
        'services':services,
        'browser':{'quota':browser_quota,'weight':browser_weight},
        'forwarder':{'restart_delay':fwd_restart_sec,'restart_count':fwd_restart_count},
        'recorder_running':recorder == 'true',
        'chromium_processes':chromium_process_count(),
        'recording_verified':False,
        'stripchat_moderation_verified':False,
    }
    result['findings'] = classify(host['cpu_psi10'],used,dc['browser'],services[UNIT_BROWSER],host['io_psi10'])
    return result


def write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.is_symlink():
        raise RuntimeError('REPORT_PATH_IS_SYMLINK')
    fd,tmp=tempfile.mkstemp(prefix='.scdiag-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as h:
            os.fchmod(h.fileno(),0o600)
            json.dump(payload,h,sort_keys=True,ensure_ascii=False,indent=2)
            h.write('\n');h.flush();os.fsync(h.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument('--sample',type=int,default=3)
    p.add_argument('--print',dest='print_report',action='store_true')
    a=p.parse_args()
    if not (2<=a.sample<=10): p.error('sample must be 2..10 seconds')
    output=sample(a.sample)
    if a.print_report:
        print(json.dumps(output,ensure_ascii=False,sort_keys=True,indent=2))
    else:
        write_atomic(REPORT,output)
        print('SC_VPS_DIAGNOSTIC_RECORDED',str(REPORT),','.join(output['findings']))
    return 0

if __name__=='__main__':
    raise SystemExit(main())