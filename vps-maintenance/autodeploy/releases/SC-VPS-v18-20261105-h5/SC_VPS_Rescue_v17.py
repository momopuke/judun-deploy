#!/usr/bin/env python3
"""Recover durable encrypted receipts and measure browser resource contention.

Read-only workload sampling. Only this diagnostic's units and evidence are written.
No application settings, recordings, containers, or workload services are changed.
"""
from __future__ import annotations
import argparse, base64, fcntl, json, os, stat, subprocess, time
from pathlib import Path
import SC_VPS_Rescue_v15 as v15
import SC_VPS_Rescue_v16 as v16

VERSION='17.0.0'
ROOT=Path('/var/lib/sc-vps-diagnostics-v17')
SOURCE=Path('/root/sc-vps-rescue-v17/SC_VPS_Rescue_v17.py')
SERVICE=Path('/etc/systemd/system/sc-vps-diagnostics-v17.service')
TIMER=Path('/etc/systemd/system/sc-vps-diagnostics-v17.timer')
CG=Path('/sys/fs/cgroup/system.slice/stripchat-browser-desktop.service')
PUBLIC_KEY='-----BEGIN PUBLIC KEY-----\nMIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAupsBfhpz6CMcEuSITz5p\nuuFSKw6aRkLCGFP0emO/N1puSahkjLoQjmt6b7XFDepjeoF4eV28s8YuOVo68nc1\nNt6bCXQS1QnZw95uGBNDbnpacNcMbMy0f5y48GUCa/U7o91SgXxIAezqmlqTG60t\nKWTy7u5HM+TRq3h6Pf1DOjyMphGA2lZcwJdaGZ/jeWV2FPV2srIF7/knLDKtk72n\ng7S7UrHmDGogQf9bPHzjSlCNUC8do2D17XtJ84QBq/YfIYFcBRkZt9+NL/2ul9ZR\nYpUHyR5JCQvJ0YyHj/pWPIeGZPXVDOhLJrBs4mLaQkue/L4vhAExd37R1S1tKX2N\ny0A66imetAGJiuMcOLcKezADdhK5dAdG7sjWzL+8X/0YSeEny4WROQ+TEsOI5NOi\nvRfuVp8KpIfqHsWUaDfEetJBkLD7KD3nKyM6xmEdv7bYA5Vd2HSYB4AEwAazfa2m\nt6ZXDqyEe8hpMCSn/TLyIH6vds5P6sRpjmCtCzOsIYw9gcZZcoC4g3TPA0S9DBfq\nOhaT/ml4KSqbLbj9kDAYcAfkRGDwROA2NFecs16qFyRhrg0zOgIV5oqPer8eNJXK\nfwtF5diIMOOkQhcYG+EDGV4Dilv6mQiYLwnw9dLwHJX4mR2HLDIAukb8ZmVo953o\nhqkA7ytVLUmOBMFThAgsjdECAwEAAQ==\n-----END PUBLIC KEY-----\n'
SERVICE_TEXT='''# SC-VPS-DIAGNOSTICS-MANAGED-v17
[Unit]
Description=SC VPS durable encrypted contention receipt
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v17/SC_VPS_Rescue_v17.py --report
CPUQuota=15%
MemoryMax=110M
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=80s
NoNewPrivileges=yes
PrivateTmp=yes
'''
TIMER_TEXT='''# SC-VPS-DIAGNOSTICS-MANAGED-v17
[Unit]
Description=SC VPS encrypted contention receipt every ten minutes
[Timer]
OnBootSec=45s
OnUnitInactiveSec=600s
AccuracySec=15s
RandomizedDelaySec=10s
Unit=sc-vps-diagnostics-v17.service
[Install]
WantedBy=timers.target
'''

def read(path, cap=4096):
    try:
        if path.is_symlink() or not path.is_file():return None
        with path.open() as f:return f.read(cap)
    except OSError:return None

def fields(path):
    out={}
    for line in (read(path) or '').splitlines():
        a=line.split()
        if len(a)==2 and a[1].isdigit():out[a[0]]=int(a[1])
    return out

def pressure(path):
    out=[]
    for name in ('some','full'):
        val=None
        for line in (read(path) or '').splitlines():
            a=line.split()
            if a and a[0]==name:
                for f in a[1:]:
                    if f.startswith('avg10='):
                        try:val=round(float(f[6:]),2)
                        except ValueError:pass
        out.append(val)
    return out

def rate(a,b,k,t):
    x=a.get(k);y=b.get(k)
    return round((y-x)/t,1) if x is not None and y is not None and y>=x and t>0 else None

def detail(a,b,t):
    q=(read(CG/'cpu.max') or '').split()
    quota=[int(x) if x.isdigit() else x for x in q] if len(q)==2 else None
    return {'q':quota,'th':rate(a,b,'nr_throttled',t),
            'bc':pressure(CG/'cpu.pressure'),'bm':pressure(CG/'memory.pressure'),
            'mm':(read(CG/'memory.max') or '').strip()[:24],
            'sw':int((read(CG/'memory.swap.current') or '0').strip())//1048576,
            'nc':os.cpu_count(),'cs':(read(CG/'cpuset.cpus.effective') or '').strip()[:40]}

def packets():
    a=fields(CG/'cpu.stat');start=time.monotonic()
    data=v16.diagnose()
    elapsed=max(.1,time.monotonic()-start)
    b=fields(CG/'cpu.stat')
    data.update(v=17,k='base')
    extra=detail(a,b,elapsed)
    extra.update(v=17,k='detail',ts=data['ts'],seq=data.get('seq'))
    return [data,extra]

def send_packets(data):
    v15.PUBLIC_KEY=PUBLIC_KEY
    for item in data:
        v15.send(v15.encrypt(item))

def report():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(ROOT/'lock','a+') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data=packets();v15.safe_write(ROOT/'last_report.json',{'packets':data})
        send_packets(data)
        print('SC_VPS_V17_REPORT_PASS ts='+str(data[0]['ts']),flush=True)
    return 0

def install():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    if SOURCE.is_symlink() or not SOURCE.is_file():raise v15.Refused('signed_source_absent')
    wanted={SERVICE:SERVICE_TEXT.encode(),TIMER:TIMER_TEXT.encode()}
    old={p:v15.read_unit(p) for p in wanted}
    if any(old[p] is not None and old[p]!=body for p,body in wanted.items()):raise v15.Refused('foreign_unit_conflict')
    created=[]
    try:
        for path,body in wanted.items():
            if old[path] is None:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
                with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
                created.append(path)
        v15.cmd('systemctl','daemon-reload');v15.cmd('systemctl','enable','--now',TIMER.name)
        if v15.cmd('systemctl','is-active',TIMER.name)!='active':raise v15.Refused('timer_inactive')
        v15.safe_write(ROOT/'install.json',{'status':'enabled','version':17,'at':int(time.time())})
    except Exception:
        if created:
            subprocess.run(['systemctl','disable','--now',TIMER.name],capture_output=True,timeout=15)
            for path in created:
                if v15.read_unit(path)==wanted[path]:path.unlink()
            subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=15)
        raise
    try:return report()
    except (v15.Refused,OSError) as e:
        print('SC_VPS_V17_INSTALLED_REPORT_PENDING '+type(e).__name__,flush=True);return 0

def rollback():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    if v15.read_unit(SERVICE)!=SERVICE_TEXT.encode() or v15.read_unit(TIMER)!=TIMER_TEXT.encode():raise v15.Refused('foreign_units_changed')
    v15.cmd('systemctl','disable','--now',TIMER.name);return 0

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    for k in ('apply','report','status','rollback'):g.add_argument('--'+k,action='store_true')
    a=p.parse_args()
    if a.status:
        print(json.dumps(v15.read_json(ROOT/'last_report.json')));return 0
    return install() if a.apply else report() if a.report else rollback()

if __name__=='__main__':
    try:raise SystemExit(main())
    except (v15.Refused,OSError,ValueError,BlockingIOError) as e:
        print('SC_VPS_V17_SAFE_ABORT '+type(e).__name__+' '+str(e)[:80]);raise SystemExit(3)
