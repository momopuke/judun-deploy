#!/usr/bin/env python3
"""SC VPS Rescue v10: one-shot guarded acceptance and persistence of v9 browser memory fix.

Owner: browser memory.high only. No browser, Docker, Guard, Recorder or webapp
restart/stop; no credentials, video files, service environment or stream keys read.
If kernel pressure/major faults remain bad, refuse persistence and give precise diagnosis.
Persistent systemctl set-property is backed up with independent systemd rollback.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, InvalidOperation
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time

import SC_VPS_Base_ReadOnly as base
import SC_VPS_Rescue_v9 as v9

VERSION='10.0.0'
ROOT=Path('/var/lib/sc-vps-rescue-v10')
SOURCE=Path('/root/sc-vps-rescue-v10/SC_VPS_Rescue_v10.py')
PERSIST_FILE=Path('/etc/systemd/system.control/stripchat-browser-desktop.service.d/50-MemoryHigh.conf')
TIME_WINDOW=15
SAMPLES=4
MiB=v9.MiB

class SafetyError(Exception): pass

def now():return dt.datetime.now(dt.timezone.utc).isoformat()
def write(path,obj):base.write_json(path,obj)
def state_file_ok(path):
    p=Path(path)
    return p.is_absolute() and ROOT in p.parents and p.name=='state.json' and p.parent.parent.name=='runs'

def saved_v9():
    files=sorted((v9.ROOT/'runs').glob('*/state.json'),reverse=True)
    for f in files:
        try: j=json.loads(f.read_text(encoding='utf8'))
        except (OSError, ValueError):continue
        if j.get('version')==v9.VERSION and j.get('status')=='trial_kept_runtime':return j
    return None

def persistent_contents_valid(data,target):
    if len(data)>8192:return False
    try:s=data.decode('utf8')
    except UnicodeDecodeError:return False
    values=re.findall(r'(?m)^\s*MemoryHigh=([0-9]+(?:\.[0-9]+)?)([KMGT]?)\s*$',s)
    if len(values)!=1:return False
    n,unit=values[0]
    try:val=Decimal(n)*Decimal(1024**({'':0,'K':1,'M':2,'G':3,'T':4}[unit]))
    except (InvalidOperation,OverflowError):return False
    return val==target

def file_bytes():
    if PERSIST_FILE.is_symlink():raise SafetyError('persistent control file is symlink')
    if not PERSIST_FILE.exists():return None
    if not PERSIST_FILE.is_file() or PERSIST_FILE.stat().st_size>8192:raise SafetyError('unexpected persistent control file')
    return PERSIST_FILE.read_bytes()

def steady(win):
    sec=win['seconds']
    maj=win['browser_major_faults']; high=win['browser_high_events']
    return {'seconds':sec, 'memory_full_pct':win['mem_full_pct'], 'io_full_pct':win['io_full_pct'],
        'major_faults_per_s':round(maj/sec,1) if sec>0 and maj is not None else None,
        'high_events_per_s':round(high/sec,1) if sec>0 and high is not None else None,
        'oom_kill':win['browser_oom_kill'],
        'ram_available_mib':win['available_mib'],'swap_free_mib':win['swap_free_mib'],
        'current_mib':win['used_mib'],'high_mib':win['high_mib']}

def assess(windows):
    if len(windows)!=SAMPLES:return False,'incomplete_sample'
    for w in windows:
        fields=('memory_full_pct','io_full_pct','major_faults_per_s','high_events_per_s','ram_available_mib','swap_free_mib','oom_kill')
        if any(w.get(k) is None for k in fields):return False,'missing_kernel_counter'
        if w['seconds']<8:return False,'short_sample'
        if w['oom_kill']!=0:return False,'browser_oom_event'
        if w['ram_available_mib']<450 or w['swap_free_mib']<200:return False,'ram_or_swap_margin_low'
        if w['io_full_pct']>6:return False,'io_pressure_high'
    good_memory=sum(w['memory_full_pct']<=20 for w in windows)
    good_major=sum(w['major_faults_per_s']<=200 for w in windows)
    if good_memory<3:return False,'memory_full_still_high'
    if good_major<3 or max(w['major_faults_per_s'] for w in windows)>450:
        return False,'major_page_faults_still_excessive'
    if max(w['high_events_per_s'] for w in windows)>1500:return False,'memory_high_throttling_excessive'
    return True,'memory_reclaim_stable_after_v9'

def identity(pre,p,target):
    if not v9.protected(pre):return False,'Docker_ID_or_running_changed'
    u=base.unit_state(base.BROWSER)
    if u['ActiveState']!='active' or u['MainPID']!=pre['units'][base.BROWSER]['MainPID'] or u['MainPID'] in ('','0'):
        return False,'browser_service_changed'
    try:q=v9.browser_group()
    except v9.SafetyError:return False,'browser_cgroup_unavailable'
    if str(q)!=str(p):return False,'browser_cgroup_changed'
    if v9.asnum(v9.r(p/'memory.high'))!=target:return False,'browser_memory_high_changed'
    if v9.asnum(base.get_prop(base.BROWSER,'MemoryHigh'))!=target:return False,'systemd_memory_high_changed'
    return True,'stable_identity'

def run_cmd(*args):
    rc,out,err=base.run(*args,timeout=35)
    if rc!=0:raise SafetyError('command failed '+args[0]+' '+(err or out)[:120])

def restore_backup(st, path, restore_runtime=True):
    old=st.get('old_high');target=st.get('target_high')
    if not isinstance(old,int) or not isinstance(target,int):raise SafetyError('bad backup state')
    before=st.get('config_before')
    if before not in ('missing','present'):raise SafetyError('missing backup state')
    current=file_bytes()
    b=None
    if before=='present':
        backup=(path.parent/'previous-config.bin')
        if not backup.exists():raise SafetyError('missing saved persistent file')
        b=backup.read_bytes()
        if len(b)>8192:raise SafetyError('invalid backup size')
    # set-property can report a transport error before changing anything.
    # In that case leave the successful v9 runtime limit untouched.
    if (before=='present' and current==b) or (before=='missing' and current is None):
        st['status']='persistent_unmodified';st['rollback_at']=now();write(path,st)
        return
    if current is not None and not persistent_contents_valid(current,target):
        raise SafetyError('persistent file modified since trial; refuse overwriting newer change')
    if before=='present':
        tmp=PERSIST_FILE.with_name(PERSIST_FILE.name+'.v10-rollback')
        fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as o:o.write(b);o.flush();os.fsync(o.fileno())
        os.replace(tmp,PERSIST_FILE)
    elif current is not None:PERSIST_FILE.unlink()
    run_cmd('systemctl','daemon-reload')
    if restore_runtime:
        # v9 was originally ephemeral. Preserve the previous persistent policy,
        # and return runtime to v9's original 450 MiB when asked to rollback.
        run_cmd('systemctl','set-property','--runtime',base.BROWSER,f'MemoryHigh={old}')
    st['status']='persistent_rolled_back'
    st['rollback_at']=now()
    write(path,st)

def start_watchdog(path):
    if not SOURCE.exists():raise SafetyError('missing watchdog source on VPS')
    suffix=str(os.getpid())
    unit='sc-vps-v10-rollback-'+suffix
    run_cmd('systemd-run','--quiet','--unit='+unit,'--on-active=150s',
            '--timer-property=AccuracySec=1s','/usr/bin/python3',str(SOURCE),'--watchdog',str(path))
    rc,out,_=base.run('systemctl','is-active',unit+'.timer')
    if rc!=0 or out.strip()!='active':raise SafetyError('rollback timer not active')
    return unit+'.timer'

def stop_watchdog(timer):
    if not re.fullmatch(r'sc-vps-v10-rollback-\d+\.timer',timer):return False
    rc,_,_=base.run('systemctl','stop',timer)
    return rc==0

def watchdog(path):
    base.require_root()
    if not state_file_ok(path):raise SafetyError('watchdog path not accepted')
    st=json.loads(Path(path).read_text())
    if st.get('version')!=VERSION or st.get('status') not in ('commit_pending','commit_applied'):
        print('WATCHDOG: no active pending commit');return 0
    if str(v9.browser_group())!=st.get('cgroup'):raise SafetyError('cgroup changed; do not clobber')
    restore_backup(st,Path(path))
    print('WATCHDOG: restored prior persistent config and runtime MemoryHigh; no service restarted')
    return 0

def check_only(pre,p,target,stats):
    ok,reason=identity(pre,p,target)
    if not ok:return False,reason
    good,reason=assess(stats)
    return good,reason

def execute():
    base.require_root();os.umask(0o077);ROOT.mkdir(parents=True,mode=0o700,exist_ok=True)
    with open(ROOT/'lock','a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
        pre=base.snapshot()
        if not all(pre['containers'][x]['running'] for x in base.REQUIRED_CONTAINERS):
            print('ABORT: protected Recorder or Gateway not running');return 2
        p=v9.browser_group(); rec=saved_v9()
        runid=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid())
        folder=ROOT/'runs'/runid;folder.mkdir(parents=True,mode=0o700)
        outfile=folder/'state.json'
        st={'version':VERSION,'utc':now(),'status':'diagnosis_only','reason':'',
            'changes':[], 'cgroup':str(p),'windows':[], 'source_v9_found':bool(rec),
            'old_high':rec.get('old_high') if rec else None,'target_high':rec.get('target_high') if rec else None}
        write(outfile,st)
        if not rec or not isinstance(rec.get('old_high'),int) or not isinstance(rec.get('target_high'),int):
            st['reason']='v9_accepted_trial_not_found';return finish(st,outfile,3)
        old=rec['old_high'];target=rec['target_high']
        if not(300*MiB<=old<=608*MiB and target==old+96*MiB and target<=704*MiB):
            st['reason']='unexpected_v9_memory_high_values';return finish(st,outfile,3)
        valid,reason=identity(pre,p,target)
        if not valid:st['reason']=reason;return finish(st,outfile,3)
        try:previous=file_bytes()
        except SafetyError as ex:st['reason']=str(ex);return finish(st,outfile,3)
        already_persistent=previous is not None and persistent_contents_valid(previous,target)
        # Periodic snapshots over one minute. Unequal wall intervals normalized to rates.
        a=v9.inspect(p)
        for i in range(SAMPLES):
            time.sleep(TIME_WINDOW)
            b=v9.inspect(p)
            w=steady(v9.interval(a,b));st['windows'].append(w);write(outfile,st)
            ok,reason=identity(pre,p,target)
            if not ok:st['reason']=reason;return finish(st,outfile,3)
            a=b
        eligible,reason=check_only(pre,p,target,st['windows']);st['reason']=reason
        if not eligible:return finish(st,outfile,3)
        if already_persistent:
            st['status']='already_persistent_verified';st['reason']='persistent_file_verified_and_steady_memory';return finish(st,outfile,0)
        if not all(w['ram_available_mib']>=450 and w['swap_free_mib']>=200 for w in st['windows']):
            st['reason']='insufficient_reserve';return finish(st,outfile,3)
        # Verify no other process modified this drop-in during monitoring.
        if file_bytes()!=previous:st['reason']='concurrent_persistent_config_change';return finish(st,outfile,3)
        if previous is not None:
            f=folder/'previous-config.bin';fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as o:o.write(previous);o.flush();os.fsync(o.fileno())
        st['config_before']='present' if previous is not None else 'missing'
        st['status']='commit_pending';write(outfile,st)
        timer=None;commit_started=False
        try:
            timer=start_watchdog(outfile);st['timer']=timer;write(outfile,st)
            valid,reason=identity(pre,p,target)
            if not valid:
                st['reason']=reason;st['status']='diagnosis_only'
                st['timer_cancelled']=stop_watchdog(timer)
                return finish(st,outfile,3)
            commit_started=True
            run_cmd('systemctl','set-property',base.BROWSER,f'MemoryHigh={target}')
            st['status']='commit_applied';write(outfile,st)
            pers=file_bytes()
            if pers is None or not persistent_contents_valid(pers,target):raise SafetyError('persistent file not verified')
            valid,reason=identity(pre,p,target)
            if not valid:raise SafetyError(reason)
            before=v9.inspect(p);time.sleep(12);after=v9.inspect(p)
            w=steady(v9.interval(before,after));st['post_commit']=w
            if not v9.protected(pre) or w['oom_kill']!=0 or w['ram_available_mib'] is None or w['ram_available_mib']<400:
                raise SafetyError('postcommit safety guard')
            if w['memory_full_pct'] is None or w['memory_full_pct']>35 or w['major_faults_per_s'] is None or w['major_faults_per_s']>500:
                raise SafetyError('postcommit memory pressure regressed')
            valid,reason=identity(pre,p,target)
            if not valid:raise SafetyError('postcommit '+reason)
            # Cannot claim success if timed rollback remains armed.
            if not stop_watchdog(timer):raise SafetyError('rollback watchdog could not be cancelled')
            st['timer_cancelled']=True;st['status']='persistent_verified';st['changes']=['browser_MemoryHigh_persistent'];st['reason']='stable_memory_pressure_and_page_faults';return finish(st,outfile,0)
        except Exception as ex:
            st['reason']='persistence_failed_'+type(ex).__name__+': '+str(ex)[:120]
            # If set-property may have run, never cancel safety timer before verified rollback.
            if commit_started:
                try:
                    restore_backup(st,outfile)
                    st['status']='rollback_completed'
                except Exception as rollback_ex:
                    st['rollback_error']=str(rollback_ex)
                    st['status']='commit_pending'  # independent watchdog still owns the rollback
            else:st['status']='diagnosis_only'
            if timer and not st.get('rollback_error'):
                st['timer_cancelled']=stop_watchdog(timer)
                if not st['timer_cancelled']:
                    st['status']='commit_pending' if commit_started else 'diagnosis_only'
            return finish(st,outfile,2 if st.get('rollback_error') else 3)

def finish(st,path,rc):
    write(path,st)
    print(f'SC VPS Rescue v{VERSION} | {st["status"]}')
    print('UTC:',st['utc']);print('Protected Recorder/Gateway: checked without restart')
    print('Decision:',st.get('reason'));print('Actions:',st.get('changes') or 'none')
    print('Browser memory.high previously: %.1f MiB | v9 target: %.1f MiB'%(
         (st['old_high'] or 0)/MiB,(st['target_high'] or 0)/MiB))
    for idx,w in enumerate(st.get('windows',[]),1):
        print('SAMPLE %d: memory.full=%s%% major_faults/s=%s high_events/s=%s RAM_available=%sMiB swap_free=%sMiB OOM_kills=%s'%(
            idx,w['memory_full_pct'],w['major_faults_per_s'],w['high_events_per_s'],
            w['ram_available_mib'],w['swap_free_mib'],w['oom_kill']))
    if st.get('post_commit'):
        w=st['post_commit'];print('POST-COMMIT: memory.full=%s%% major_faults/s=%s'%(w['memory_full_pct'],w['major_faults_per_s']))
    if st.get('timer'):print('Safety timer:',st['timer'],'cancelled='+str(st.get('timer_cancelled')))
    if st.get('rollback_error'):print('ROLLBACK REVIEW:',st['rollback_error'])
    print('Recorder file continuity, stream success and Guard actions are NOT verified by this tool.')
    print('Machine state:',path)
    return rc

def rollback():
    base.require_root()
    files=sorted((ROOT/'runs').glob('*/state.json'),reverse=True)
    for path in files:
        try:st=json.loads(path.read_text())
        except (OSError,ValueError):continue
        if st.get('version')==VERSION and st.get('status')=='persistent_verified':
            restore_backup(st,path)
            print('v10 rollback: restored prior persistent browser policy (only); no services restarted')
            return 0
    print('No verified persistent v10 change found');return 3

def status():
    base.require_root()
    print('SC VPS Rescue v'+VERSION+' - read-only current status')
    try:
        p=v9.browser_group()
        current=v9.asnum(v9.r(p/'memory.high'))
        print('Browser MemoryHigh: '+(str(round(current/MiB,1))+' MiB' if current is not None else 'unknown'))
        print('Current browser memory: '+str(round(int(v9.r(p/'memory.current'))/MiB,1))+' MiB')
        conf=file_bytes()
        print('Persistent MemoryHigh drop-in: '+('present' if conf is not None else 'absent'))
    except (v9.SafetyError,OSError,ValueError) as ex:print('Browser metrics unavailable:',str(ex)[:100])
    for name in base.REQUIRED_CONTAINERS:
        st=base.docker_state(name)
        print(name+': '+('UP' if st['running'] else 'NOT RUNNING'))
    print('Global CPU PSI avg10:',base.cpu_pressure())
    last=sorted((ROOT/'runs').glob('*/state.json'),reverse=True) if ROOT.exists() else []
    if last:
        try:
            st=json.loads(last[0].read_text(encoding='utf8'))
            print('Latest v10 action:',st.get('status'),'decision:',st.get('reason'))
        except (OSError,ValueError):print('Latest v10 state unreadable')
    print('This status is NOT proof of real stream, moderation or recording continuity.')
    return 0

def main():
    ap=argparse.ArgumentParser()
    x=ap.add_mutually_exclusive_group(required=True)
    x.add_argument('--apply',action='store_true');x.add_argument('--rollback',action='store_true');x.add_argument('--status',action='store_true');x.add_argument('--watchdog')
    args=ap.parse_args()
    if args.rollback:return rollback()
    if args.status:return status()
    if args.watchdog:return watchdog(Path(args.watchdog))
    return execute()

if __name__=='__main__':
    try:sys.exit(main())
    except (SafetyError,v9.SafetyError,base.RescueError,OSError,ValueError,BlockingIOError) as ex:
        print('SAFE ABORT:',str(ex),file=sys.stderr,flush=True);sys.exit(1)
