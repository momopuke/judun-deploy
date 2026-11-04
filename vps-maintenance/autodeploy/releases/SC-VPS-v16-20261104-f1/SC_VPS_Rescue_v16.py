#!/usr/bin/env python3
"""SC VPS v16 read-only, bounded CPU cause diagnosis with encrypted telemetry.

Samples cgroup CPU usage, /proc/PID/stat and known systemd restart counters;
reports only aggregated process classes and numeric metrics, not command lines,
usernames, user content or logs. Does not change a running service.
"""
from __future__ import annotations
import argparse, datetime as dt, fcntl, json, os, re, stat, subprocess, time
from pathlib import Path
import SC_VPS_Rescue_v15 as v15

VERSION='16.0.0'
ROOT=Path('/var/lib/sc-vps-diagnostics-v16')
SOURCE=Path('/root/sc-vps-rescue-v16/SC_VPS_Rescue_v16.py')
SERVICE=Path('/etc/systemd/system/sc-vps-cpu-diagnosis-v16.service')
TIMER=Path('/etc/systemd/system/sc-vps-cpu-diagnosis-v16.timer')
SERVICE_TEXT='''# SC-VPS-CPU-DIAGNOSIS-MANAGED-v16
[Unit]
Description=SC VPS encrypted CPU root-cause sample
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v16/SC_VPS_Rescue_v16.py --report
CPUQuota=15%
MemoryMax=110M
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=65s
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
'''
TIMER_TEXT='''# SC-VPS-CPU-DIAGNOSIS-MANAGED-v16
[Unit]
Description=SC VPS unattended CPU cause diagnosis every ten minutes
[Timer]
OnBootSec=180s
OnUnitInactiveSec=600s
AccuracySec=20s
RandomizedDelaySec=15s
Persistent=false
Unit=sc-vps-cpu-diagnosis-v16.service
[Install]
WantedBy=timers.target
'''

KNOWN={'chromium':'chromium','chrome':'chromium','headless_shell':'chromium',
       'python':'python','python3':'python','node':'node','ffmpeg':'ffmpeg',
       'rclone':'rclone','caddy':'caddy','dockerd':'docker','containerd':'docker',
       'systemd':'systemd','bash':'shell','sh':'shell','curl':'net','wget':'net',
       'Xvfb':'xserver','Xorg':'xserver'}
MAX_PIDS=1200

def category(name):
    name=name.strip()
    for key,val in KNOWN.items():
        if name==key or name.startswith(key+'-') or name.startswith(key+'.'):
            return val
    return 'other'

def proc_stat(path):
    try:
        raw=path.read_text()
        n=raw.rfind(')')
        if n<0 or not raw.startswith(str(int(path.parent.name))+' ('):return None
        name=raw[raw.find('(')+1:n]
        tail=raw[n+2:].split()
        if len(tail)<20:return None
        return {'cat':category(name),'ticks':int(tail[11])+int(tail[12]),'start':int(tail[19])}
    except (OSError,ValueError,IndexError):return None

def proc_snapshot(root=Path('/proc')):
    out={}
    try: entries=list(root.iterdir())[:3000]
    except OSError:return {}
    for item in entries:
        if len(out)>=MAX_PIDS:break
        if not item.name.isdecimal():continue
        s=proc_stat(item/'stat')
        if s:out[item.name]=s
    return out

def cpu_stat(path=Path('/proc/stat')):
    try:
        fields=path.read_text().splitlines()[0].split()
        if fields[0]!='cpu':return None
        nums=[int(x) for x in fields[1:]]
        if len(nums)<5:return None
        return {'total':sum(nums),'idle':nums[3]+nums[4]}
    except (OSError,ValueError,IndexError):return None

def browser_cpu(path=Path('/sys/fs/cgroup/system.slice/stripchat-browser-desktop.service/cpu.stat')):
    try:
        for line in path.read_text().splitlines():
            k,*v=line.split()
            if k=='usage_usec' and len(v)==1:return int(v[0])
    except (OSError,ValueError):pass
    return None

def contrib(before,after,elapsed,ticks_per_sec=None):
    rate=ticks_per_sec or os.sysconf('SC_CLK_TCK')
    if elapsed<=0 or rate<=0:return []
    sums={}
    for pid,q in after.items():
        old=before.get(pid)
        if not old or old['start']!=q['start'] or old['cat']!=q['cat']:continue
        diff=q['ticks']-old['ticks']
        if not 0<=diff<=rate*elapsed*8:continue
        sums[q['cat']]=sums.get(q['cat'],0.0)+100*diff/(rate*elapsed)
    return [[key,round(value,1)] for key,value in sorted(sums.items(),key=lambda it:(-it[1],it[0]))[:6]]

def unit_state(name):
    if name not in ('livevpn-stripchat-forward.service','strip-recovery-watchdog.service'):
        return None
    try:
        raw=v15.cmd('systemctl','show','--no-pager','-p','ActiveState',
                 '-p','NRestarts','-p','ExecMainStatus',name,timeout=7)
    except v15.Refused:return None
    d=dict(line.split('=',1) for line in raw.splitlines() if '=' in line)
    out={}
    out['active']=d.get('ActiveState') in ('active','activating')
    for key,new in [('NRestarts','r'),('ExecMainStatus','x')]:
        n=d.get(key,'')
        out[new]=int(n) if n.isdigit() and int(n)<=100000000 else None
    return out

def diagnose():
    a=proc_snapshot();cpu0=cpu_stat();cb=browser_cpu();start=time.monotonic()
    base=v15.report_data(delay=3)
    elapsed=max(.1,time.monotonic()-start)
    b=proc_snapshot();cpu1=cpu_stat();ca=browser_cpu()
    bp=round((ca-cb)/10000/elapsed,1) if ca is not None and cb is not None and ca>=cb else None
    overall=None
    if cpu0 and cpu1:
        delta=cpu1['total']-cpu0['total'];idle=cpu1['idle']-cpu0['idle']
        if delta>0 and 0<=idle<=delta:overall=round(100*(delta-idle)/delta,1)
    base.update({'v':16,'pc':contrib(a,b,elapsed),'bp':bp,'use':overall,
                 'fwd':unit_state('livevpn-stripchat-forward.service'),
                 'wd':unit_state('strip-recovery-watchdog.service')})
    return base

def report():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(ROOT/'lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data=diagnose();v15.safe_write(ROOT/'last_report.json',data)
        v15.send(v15.encrypt(data))
        print('SC_VPS_V16_REPORT_PASS v=16 ts='+str(data['ts']),flush=True)
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
        v15.safe_write(ROOT/'install.json',{'status':'v16_diagnostics_enabled',
            'at':dt.datetime.now(dt.timezone.utc).isoformat(),'protected_restarts':0})
    except Exception:
        if created:
            subprocess.run(['systemctl','disable','--now',TIMER.name],capture_output=True,timeout=15)
            for path in created:
                if v15.read_unit(path)==wanted[path]:path.unlink()
            subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=15)
        raise
    try:return report()
    except v15.Refused as e:
        print('SC_VPS_V16_INSTALLED_REPORT_PENDING',str(e)[:90]);return 0

def status():
    print('SC_VPS_V16_STATUS',json.dumps({'install':v15.read_json(ROOT/'install.json'),
         'last':v15.read_json(ROOT/'last_report.json')},sort_keys=True));return 0

def rollback():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    if v15.read_unit(SERVICE)!=SERVICE_TEXT.encode() or v15.read_unit(TIMER)!=TIMER_TEXT.encode():raise v15.Refused('foreign_units_changed')
    v15.cmd('systemctl','disable','--now',TIMER.name)
    print('SC_VPS_V16_DIAGNOSTICS_DISABLED; no container changes');return 0

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    for k in ('apply','report','status','rollback'):g.add_argument('--'+k,action='store_true')
    a=p.parse_args()
    return install() if a.apply else report() if a.report else status() if a.status else rollback()
if __name__=='__main__':
    try:raise SystemExit(main())
    except (v15.Refused,OSError,ValueError,BlockingIOError) as e:
        print('SC_VPS_V16_SAFE_ABORT',type(e).__name__,str(e)[:100]);raise SystemExit(3)
