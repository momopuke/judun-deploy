#!/usr/bin/env python3
"""SC VPS v14: bounded, fail-closed retention of old diagnostics only.

Never removes recordings, Docker data, backup files, system journal, agent receipts,
V13 telemetry, source code or V12 verified/rollback trial evidence.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

VERSION='14.0.0'
ROOT=Path('/var/lib/sc-vps-cleanup-v14')
SOURCE=Path('/root/sc-vps-rescue-v14/SC_VPS_Rescue_v14.py')
SERVICE=Path('/etc/systemd/system/sc-vps-diagnostics-retention.service')
TIMER=Path('/etc/systemd/system/sc-vps-diagnostics-retention.timer')
SNAME=SERVICE.name
TNAME=TIMER.name
KEEP=20
MIN_AGE=7*24*3600
MAX_REMOVALS=200
MAX_READ=32768
RUNS=[Path(f'/var/lib/sc-vps-rescue-v{n}/runs') for n in range(8,13)]
SAFE_OLD={'diagnosis_only','safety_refused'}
SAFE_V12={'diagnosis_only','monitoring_accepted'}
SERVICE_TEXT='''# SC-VPS-RETENTION-MANAGED-v14
[Unit]
Description=SC VPS low-load cleanup of expired diagnostic-only reports
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v14/SC_VPS_Rescue_v14.py --clean
CPUQuota=15%
MemoryMax=100M
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=120s
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
'''
TIMER_TEXT='''# SC-VPS-RETENTION-MANAGED-v14
[Unit]
Description=SC VPS daily safe diagnostic-report retention
[Timer]
OnBootSec=300s
OnUnitInactiveSec=24h
AccuracySec=30min
RandomizedDelaySec=15min
Persistent=false
Unit=sc-vps-diagnostics-retention.service
[Install]
WantedBy=timers.target
'''
class Refuse(Exception):pass

def command(*args,timeout=25):
    try:r=subprocess.run(args,capture_output=True,text=True,check=False,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired) as e:raise Refuse('command_error_'+args[0]) from e
    if r.returncode:raise Refuse('command_status_'+args[0]+'_'+str(r.returncode))
    return r.stdout.strip()

def read_exact(path,cap=16384):
    if path.is_symlink():raise Refuse('symlink_'+path.name)
    if not path.exists():return None
    s=path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size>cap:raise Refuse('file_not_expected_'+path.name)
    return path.read_bytes()

def write_atomic(path,value):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise Refuse('state_symlink')
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.state-')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            os.fchmod(f.fileno(),0o600)
            json.dump(value,f,sort_keys=True,separators=(',',':'))
            f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def regular_dir(path):
    if path.is_symlink() or not path.is_dir():return False
    s=path.stat()
    return stat.S_ISDIR(s.st_mode) and s.st_uid==os.geteuid()

def eligible(folder,version,now):
    """Only exact run-dir shape, expired twice (file mtime AND embedded UTC)."""
    if not regular_dir(folder):return (False,0)
    try:
        children=list(folder.iterdir())
        if len(children)!=1 or children[0].name!='state.json':return (False,0)
        f=children[0]
        if f.is_symlink():return (False,0)
        fs=f.stat()
        if not stat.S_ISREG(fs.st_mode) or fs.st_uid!=os.geteuid() or fs.st_size>MAX_READ:return (False,0)
        if now-fs.st_mtime<MIN_AGE:return (False,0)
        s=json.loads(f.read_text('utf8'))
        if not isinstance(s,dict) or s.get('status') not in (SAFE_V12 if version==12 else SAFE_OLD):return (False,0)
        if s.get('changes') not in (None,[]):return (False,0)
        at=s.get('utc')
        if not isinstance(at,str):return (False,0)
        age=now-dt.datetime.fromisoformat(at.replace('Z','+00:00')).timestamp()
        if age<MIN_AGE:return (False,0)
        return (True,fs.st_size)
    except (OSError,UnicodeError,ValueError,TypeError,OverflowError):return (False,0)

def prune(now=None,roots=None,unlink=True):
    now=time.time() if now is None else float(now)
    roots=RUNS if roots is None else roots
    summary={'at':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
             'status':'cleanup_pass','examined':0,'removed':0,'freed_bytes':0,
             'kept':0,'errors':0,'scope':'expired_diagnostic_only','days':7}
    for version,base in enumerate(roots,start=8):
        if not regular_dir(base):continue
        folders=sorted((f for f in base.iterdir() if regular_dir(f)),reverse=True)
        for folder in folders[:KEEP]:summary['kept']+=1
        for folder in folders[KEEP:]:
            summary['examined']+=1
            ok,size=eligible(folder,version,now)
            if not ok:
                summary['kept']+=1
                continue
            if summary['removed']>=MAX_REMOVALS:break
            if unlink:
                try:
                    # Re-evaluate before destructive operation; only one expected regular file.
                    ok2,size2=eligible(folder,version,now)
                    if not ok2 or size!=size2:raise Refuse('candidate_changed')
                    (folder/'state.json').unlink()
                    folder.rmdir()
                except (OSError,Refuse):
                    summary['errors']+=1
                    continue
            summary['removed']+=1;summary['freed_bytes']+=size
    return summary

def clean():
    if os.geteuid()!=0:raise Refuse('root_required')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(ROOT/'lock','a+') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
        s=prune()
        write_atomic(ROOT/'last_cleanup.json',s)
        print('SC_VPS_V14_CLEANUP',json.dumps(s,sort_keys=True),flush=True)
    return 0

def install():
    if os.geteuid()!=0:raise Refuse('root_required')
    if not SOURCE.is_file() or SOURCE.is_symlink():raise Refuse('signed_source_absent')
    entries={SERVICE:SERVICE_TEXT.encode(),TIMER:TIMER_TEXT.encode()}
    olds={f:read_exact(f) for f in entries}
    if any(olds[f] is not None and olds[f]!=data for f,data in entries.items()):raise Refuse('foreign_unit_conflict')
    created=[]
    try:
        for f,data in entries.items():
            if olds[f] is None:
                fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
                with os.fdopen(fd,'wb') as fp:fp.write(data);fp.flush();os.fsync(fp.fileno())
                created.append(f)
        command('systemctl','daemon-reload')
        command('systemctl','enable','--now',TNAME)
        if command('systemctl','is-active',TNAME)!='active':raise Refuse('timer_inactive')
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        write_atomic(ROOT/'install.json',{'version':VERSION,'status':'daily_retention_enabled','timer':TNAME,
            'protected_restarts':0,'videos_deleted':0})
    except Exception:
        if created:
            subprocess.run(['systemctl','disable','--now',TNAME],capture_output=True,timeout=15)
            for f in created:
                if read_exact(f)==entries[f]:f.unlink()
            subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=15)
        raise
    result=prune()
    write_atomic(ROOT/'last_cleanup.json',result)
    print('SC_VPS_V14_APPLIED',json.dumps(result,sort_keys=True),flush=True)
    return 0

def status():
    print('SC_VPS_V14_STATUS',json.dumps({
        'install':json.loads(read_exact(ROOT/'install.json') or b'{}'),
        'cleanup':json.loads(read_exact(ROOT/'last_cleanup.json') or b'{}')},sort_keys=True))
    return 0

def rollback():
    if os.geteuid()!=0:raise Refuse('root_required')
    if read_exact(SERVICE)!=SERVICE_TEXT.encode() or read_exact(TIMER)!=TIMER_TEXT.encode():raise Refuse('foreign_unit_changed')
    command('systemctl','disable','--now',TNAME)
    print('SC_VPS_V14_RETENTION_DISABLED; existing diagnostics untouched')
    return 0

def main():
    p=argparse.ArgumentParser()
    g=p.add_mutually_exclusive_group(required=True)
    for x in ['apply','clean','status','rollback']:g.add_argument('--'+x,action='store_true')
    a=p.parse_args()
    return install() if a.apply else clean() if a.clean else status() if a.status else rollback()

if __name__=='__main__':
    try:raise SystemExit(main())
    except (Refuse,OSError,ValueError,BlockingIOError) as e:
        print('SC_VPS_V14_SAFE_ABORT',type(e).__name__,str(e)[:100],flush=True)
        raise SystemExit(3)
