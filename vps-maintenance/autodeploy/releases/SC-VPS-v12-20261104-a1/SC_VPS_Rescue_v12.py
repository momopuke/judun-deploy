#!/usr/bin/env python3
"""SC VPS Rescue v12 - unattended browser-only guarded pressure remediation.

Design: signed release installs ONE isolated systemd timer. The timer samples live
pressure and may temporarily raise Chromium's runtime-only memory.high by 32 MiB
when host reserves and protected service identities permit. It does NOT change
Docker, browser processes, persistent browser policy, files, media, credentials,
or services outside its own scoped timer and runtime MemoryHigh.

V12 remains autonomous after the signed-release pull has finished, including
rollback watchdog, cooldown, regression monitoring and durable status reports.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time
import hashlib

import SC_VPS_Base_ReadOnly as base
import SC_VPS_Rescue_v9 as v9

VERSION = '12.0.0'
ROOT = Path('/var/lib/sc-vps-rescue-v12')
SOURCE = Path('/root/sc-vps-rescue-v12/SC_VPS_Rescue_v12.py')
SERVICE = Path('/etc/systemd/system/sc-vps-browser-autotune.service')
TIMER = Path('/etc/systemd/system/sc-vps-browser-autotune.timer')
SERVICE_NAME = 'sc-vps-browser-autotune.service'
TIMER_NAME = 'sc-vps-browser-autotune.timer'
MiB = 1024 * 1024
OLD = 546 * MiB
NEW = 578 * MiB
WINDOW = 12
N = 4
WATCHDOG_DELAY = 180
COOLDOWN = 6 * 3600

SERVICE_TEXT = '''# SC-VPS-BROWSER-AUTOTUNE-MANAGED-v12
[Unit]
Description=SC VPS browser-only safe pressure monitor and runtime rollback
After=multi-user.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v12/SC_VPS_Rescue_v12.py --run
CPUQuota=20%
MemoryMax=160M
Nice=15
IOSchedulingClass=idle
TimeoutStartSec=150s
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
'''
TIMER_TEXT = '''# SC-VPS-BROWSER-AUTOTUNE-MANAGED-v12
[Unit]
Description=SC VPS automatic browser memory stall check
[Timer]
OnBootSec=120s
OnUnitInactiveSec=600s
AccuracySec=10s
RandomizedDelaySec=20s
Persistent=false
Unit=sc-vps-browser-autotune.service
[Install]
WantedBy=timers.target
'''

class Stop(RuntimeError): pass

def stamp():return dt.datetime.now(dt.timezone.utc).isoformat()
def sec_now():return time.time()
def jwrite(path,obj):base.write_json(path,obj)
def sha(data):return hashlib.sha256(data).hexdigest()

def safe_read(path,maxbytes=10000):
    if path.is_symlink():raise Stop('symlink_not_allowed')
    if not path.exists():return None
    if not path.is_file() or path.stat().st_size>maxbytes:raise Stop('unexpected_file')
    return path.read_bytes()

def cmd(*parts, timeout=30):
    rc,out,err=base.run(*parts,timeout=timeout)
    if rc!=0:raise Stop('system_operation_failed:'+parts[0]+':'+str(rc))
    return out

def container_ids():
    out={name:base.docker_state(name) for name in base.REQUIRED_CONTAINERS}
    if not all(x.get('running') and x.get('id') for x in out.values()):raise Stop('protected_container_unavailable')
    return {name:x['id'] for name,x in out.items()}

def browser_id():
    u=base.unit_state(base.BROWSER)
    if u.get('ActiveState')!='active' or u.get('MainPID') in ('0','',None):raise Stop('browser_not_active')
    return str(u['MainPID'])

def identities():
    p=v9.browser_group()
    return p, browser_id(), container_ids()

def stable(p,bid,dids,expected):
    try:
        q,b,c=identities()
        return str(p)==str(q) and b==bid and c==dids and limit_ok(p,expected)
    except (Stop,v9.SafetyError,OSError,ValueError):return False

def limit_ok(p,expected):
    return (v9.asnum(v9.r(p/'memory.high'))==expected and
        v9.asnum(base.get_prop(base.BROWSER,'MemoryHigh'))==expected)

def set_high(p,old,new):
    if not limit_ok(p,old):raise Stop('concurrent_memory_high_change')
    cmd('systemctl','set-property','--runtime',base.BROWSER,'MemoryHigh='+str(new),timeout=25)
    if not limit_ok(p,new):raise Stop('runtime_memory_high_not_verified')

def sample(a,b):
    x=v9.interval(a,b)
    secs=x['seconds']
    return {
        'seconds':secs,
        'memory_full_pct':x['mem_full_pct'],
        'io_full_pct':x['io_full_pct'],
        'high_events_per_s':round(x['browser_high_events']/secs,1) if x['browser_high_events'] is not None and secs>0 else None,
        'major_faults_per_s':round(x['browser_major_faults']/secs,1) if x['browser_major_faults'] is not None and secs>0 else None,
        'oom_kill':x['browser_oom_kill'],
        'available_mib':x['available_mib'],
        'swap_free_mib':x['swap_free_mib'],
        'browser_current_mib':x['used_mib'],
    }

def counters_ok(w):
    keys=['seconds','memory_full_pct','io_full_pct','high_events_per_s',
          'major_faults_per_s','oom_kill','available_mib','swap_free_mib']
    return all(w.get(k) is not None for k in keys) and w['seconds']>=8

def eligible(w):
    if not counters_ok(w):return 'counters_missing'
    if w['oom_kill']!=0:return 'oom_event'
    if w['memory_full_pct']<17 or w['high_events_per_s']<80:return 'no_causal_memory_stall'
    if w['major_faults_per_s']>250:return 'heavy_disk_faults'
    if w['io_full_pct']>5:return 'io_full_unsafe'
    # Conservative dynamic margin: +32MiB leaves at least ~390MiB free.
    if w['available_mib']<430 or w['swap_free_mib']<350:return 'insufficient_host_reserve'
    return None

def danger(w):
    if not counters_ok(w):return 'counters_missing_after_change'
    if w['oom_kill']!=0:return 'oom_event_after_change'
    if w['available_mib']<370 or w['swap_free_mib']<280:return 'reserve_too_low_after_change'
    if w['memory_full_pct']>55 or w['io_full_pct']>8:return 'pressure_unsafe_after_change'
    if w['major_faults_per_s']>280:return 'major_faults_unsafe_after_change'
    return None

def improved(pre,windows):
    if len(windows)!=N or any(danger(w) for w in windows):return False
    p=pre['memory_full_pct']; h=pre['high_events_per_s']
    return (sum(w['memory_full_pct']<=p*.80 and p-w['memory_full_pct']>=5 for w in windows)>=3
            and sum(w['high_events_per_s']<=h*.60 for w in windows)>=3)

def pending_path_ok(path):
    return path.is_absolute() and ROOT in path.parents and path.name=='state.json' and path.parent.parent.name=='runs'

def read_pending(path):
    if not pending_path_ok(path) or path.is_symlink() or path.stat().st_size>35000:raise Stop('watchdog_state_invalid')
    return json.loads(path.read_text('utf8'))

def watchdog(path):
    base.require_root()
    st=read_pending(path)
    if st.get('version')!=VERSION or st.get('status') not in ('trial_pending','trial_running','needs_review'):
        print('V12_WATCHDOG_NO_ACTION');return 0
    if st.get('old_high')!=OLD or st.get('target_high')!=NEW:raise Stop('watchdog_values_invalid')
    p=v9.browser_group()
    if str(p)!=st.get('browser_cgroup'):raise Stop('watchdog_group_changed')
    if limit_ok(p,NEW):
        set_high(p,NEW,OLD)
        st['status']='watchdog_rolled_back';st['finished_at']=stamp();jwrite(path,st)
        print('V12_WATCHDOG_ROLLBACK_PASS');return 0
    if limit_ok(p,OLD):
        st['status']='watchdog_limit_already_old';st['finished_at']=stamp();jwrite(path,st)
        print('V12_WATCHDOG_NO_CHANGE');return 0
    raise Stop('watchdog_external_limit_changed')

def start_watchdog(path):
    if not SOURCE.is_file() or SOURCE.is_symlink():raise Stop('watchdog_source_invalid')
    name='sc-vps-v12-rollback-'+str(os.getpid())
    cmd('systemd-run','--quiet','--unit='+name,'--on-active='+str(WATCHDOG_DELAY)+'s',
        '--timer-property=AccuracySec=1s','/usr/bin/python3',str(SOURCE),'--watchdog',str(path),timeout=20)
    timer=name+'.timer'
    if cmd('systemctl','is-active',timer,timeout=7).strip()!='active':raise Stop('watchdog_not_armed')
    return timer

def cancel_watchdog(timer):
    if not re.fullmatch(r'sc-vps-v12-rollback-\d+\.timer',timer):return False
    rc,_,_=base.run('systemctl','stop',timer,timeout=15)
    return rc==0

def latest_runs():
    return sorted((ROOT/'runs').glob('*/state.json'),reverse=True)[:30]

def last_change():
    for f in latest_runs():
        try:
            s=json.loads(f.read_text())
            if s.get('status') in ('trial_rolled_back','runtime_verified','regression_rolled_back','watchdog_rolled_back'):
                return s
        except (OSError,ValueError):pass
    return None

def safe_cooldown():
    last=last_change()
    if last is None:return False
    if last.get('status')=='runtime_verified':return False
    try:return sec_now()-dt.datetime.fromisoformat(last['utc']).timestamp()<COOLDOWN
    except (KeyError,ValueError,TypeError):return True

def report(st,path,rc):
    st['finished_at']=stamp();jwrite(path,st)
    print('SC VPS Rescue v12.0.0 |',st['status'])
    print('Decision:',st['reason'],'| exit',rc)
    print('Browser limit before/after:',st['old_high'],st['target_high'])
    print('Baseline:',st.get('baseline'))
    print('Samples:',len(st.get('windows',[])))
    print('Recorder/Gateway protected identity:',st.get('identities_checked'))
    return rc

def monitor():
    base.require_root();os.umask(0o077);ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(ROOT/'lock','a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        folder=ROOT/'runs'/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+str(os.getpid()))
        folder.mkdir(parents=True,mode=0o700)
        path=folder/'state.json'
        st={'version':VERSION,'utc':stamp(),'status':'diagnosis_only','reason':'',
            'browser_cgroup':None,'old_high':None,'target_high':None,
            'baseline':None,'windows':[],'changes':[],'identities_checked':False}
        jwrite(path,st)
        p,bid,dids=identities();st['browser_cgroup']=str(p);st['identities_checked']=True
        high=v9.asnum(v9.r(p/'memory.high'));st['old_high']=high
        if high not in (OLD,NEW) or not limit_ok(p,high):
            st['reason']='unknown_browser_memory_policy';return report(st,path,3)
        a=v9.inspect(p);time.sleep(WINDOW);b=v9.inspect(p)
        w=sample(a,b);st['baseline']=w;jwrite(path,st)
        if not stable(p,bid,dids,high):
            st['reason']='identity_changed';return report(st,path,3)
        if high==NEW:
            prior=last_change()
            if not(prior and prior.get('status')=='runtime_verified'
                   and prior.get('browser_cgroup')==str(p)):
                st['reason']='runtime_578MiB_has_no_verified_v12_trial'
                return report(st,path,3)
            bad=danger(w)
            if bad:
                # Independently roll back if accepted browser limit loses its safety margin.
                set_high(p,NEW,OLD)
                st['status']='regression_rolled_back';st['changes']=['browser_runtime_MemoryHigh_restored']
                st['reason']='accepted_limit_pressure_regression_'+bad
                return report(st,path,0)
            st['status']='monitoring_accepted';st['reason']='accepted_limit_still_safe'
            return report(st,path,0)
        if safe_cooldown():
            st['reason']='cooldown_after_unhelpful_trial';return report(st,path,0)
        why=eligible(w)
        if why:
            st['reason']=why;return report(st,path,0)
        # Confirm cgroup usage is close enough for memory.high pressure to be causal.
        if b['current_bytes'] is None or not OLD-24*MiB<=b['current_bytes']<=OLD+128*MiB:
            st['reason']='browser_usage_outside_safe_envelope';return report(st,path,0)
        if b['max_bytes'] is not None and b['max_bytes']<=NEW+32*MiB:
            st['reason']='memory_max_close_to_target';return report(st,path,0)
        if not stable(p,bid,dids,OLD):
            st['reason']='pretrial_identity_changed';return report(st,path,0)
        timer=None;changed=False
        st['target_high']=NEW
        try:
            st['status']='trial_pending';jwrite(path,st)
            timer=start_watchdog(path);st['watchdog']=timer;jwrite(path,st)
            if not stable(p,bid,dids,OLD):raise Stop('identity_changed_before_mutation')
            set_high(p,OLD,NEW);changed=True
            st['status']='trial_running';st['changes']=['browser_MemoryHigh_runtime_trial'];jwrite(path,st)
            a=v9.inspect(p)
            for _ in range(N):
                time.sleep(WINDOW);b=v9.inspect(p);q=sample(a,b)
                st['windows'].append(q);jwrite(path,st)
                if not stable(p,bid,dids,NEW):raise Stop('protected_identity_or_memory_limit_changed')
                bad=danger(q)
                if bad:raise Stop(bad)
                a=b
            if improved(w,st['windows']):
                # Recorded measured acceptance before disarming timer; old limit can still be restored later.
                st['status']='runtime_verified';st['reason']='repeatable_pressure_and_high_event_improvement'
                st['changes']=['browser_MemoryHigh_runtime_578MiB'];jwrite(path,st)
                if not cancel_watchdog(timer):
                    st['status']='needs_review';jwrite(path,st)
                    raise Stop('watchdog_cancel_failed')
                st['watchdog_cancelled']=True
                return report(st,path,0)
            st['reason']='no_repeatable_pressure_improvement'
            set_high(p,NEW,OLD);changed=False
            st['status']='trial_rolled_back';st['changes']=['browser_MemoryHigh_restored'];jwrite(path,st)
            if not cancel_watchdog(timer):raise Stop('watchdog_cancel_failed')
            st['watchdog_cancelled']=True
            return report(st,path,0)
        except (Exception,KeyboardInterrupt) as err:
            st['reason']='trial_error_'+type(err).__name__+':'+str(err)[:90]
            if changed and limit_ok(p,NEW):
                try:set_high(p,NEW,OLD);changed=False
                except Exception:st['rollback_error']='runtime_rollback_failed'
            if not changed and limit_ok(p,OLD):
                st['status']='trial_rolled_back';st['changes']=['browser_MemoryHigh_restored']
                if timer and cancel_watchdog(timer):st['watchdog_cancelled']=True
                return report(st,path,0)
            st['status']='needs_review';return report(st,path,2)

def pre_install_ok():
    # Check latest signed V11 refusal without modifying old state or timers.
    files=sorted(Path('/var/lib/sc-vps-rescue-v11/runs').glob('*/state.json'),reverse=True)
    if not files:raise Stop('v11_state_missing')
    x=json.loads(files[0].read_text('utf8'))
    if not(x.get('version')=='11.0.0' and x.get('status')=='diagnosis_only' and
           x.get('reason')=='reserve_too_low_before_trial' and x.get('changes')==[]):
        raise Stop('v11_previous_safe_refusal_not_verified')
    p,b,c=identities()
    if not limit_ok(p,OLD):raise Stop('browser_memory_limit_not_at_546MiB')
    return True

def install():
    base.require_root();os.umask(0o077)
    pre_install_ok()
    if not SOURCE.is_file() or SOURCE.is_symlink():raise Stop('installed_v12_source_missing')
    expected={SERVICE:SERVICE_TEXT.encode(),TIMER:TIMER_TEXT.encode()}
    previous={path:safe_read(path) for path in expected}
    for path,data in expected.items():
        if previous[path] is not None and previous[path]!=data:
            raise Stop('foreign_unit_conflict_'+path.name)
    # Never overwrite a foreign service. After success own timer is the only persistent mutation.
    installed=[]
    try:
        for path,data in expected.items():
            if previous[path] is None:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
                with os.fdopen(fd,'wb') as fp:fp.write(data);fp.flush();os.fsync(fp.fileno())
                installed.append(path)
        cmd('systemctl','daemon-reload')
        cmd('systemctl','enable','--now',TIMER_NAME,timeout=30)
        if cmd('systemctl','is-active',TIMER_NAME).strip()!='active':raise Stop('timer_not_active_after_install')
        # No inline long-running operation inside the signed pull; timer runs unattended.
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        status={'version':VERSION,'utc':stamp(),'status':'autonomous_timer_installed',
                'reason':'signed_guarded_monitor_enabled','service':SERVICE_NAME,
                'timer':TIMER_NAME,'unit_hashes':{x.name:sha(data) for x,data in expected.items()},
                'recorder_restarted':False,'gateway_restarted':False}
        jwrite(ROOT/'install.json',status)
        print('SC VPS Rescue v12.0.0 | autonomous_timer_installed')
        print('Scoped timer:',TIMER_NAME)
        print('No protected service restarted. No browser memory change in installer.')
        return 0
    except Exception:
        # Fail-closed cleanup of newly created files only; do not disable pre-existing timer.
        if installed:
            base.run('systemctl','disable','--now',TIMER_NAME,timeout=15)
            for path in installed:
                if safe_read(path)==expected[path]:path.unlink()
            base.run('systemctl','daemon-reload',timeout=15)
        raise

def status():
    print('SC VPS Rescue v12 | read-only status')
    p=v9.browser_group();print('browser MemoryHigh MiB:',v9.asnum(v9.r(p/'memory.high'))/MiB)
    print('timer:',base.run('systemctl','is-active',TIMER_NAME)[1])
    files=latest_runs()
    if files:
        st=read_pending(files[0])
        print('latest:',st.get('status'),st.get('reason'))
        print('baseline:',st.get('baseline'))
    return 0

def rollback():
    base.require_root()
    if safe_read(SERVICE)!=SERVICE_TEXT.encode() or safe_read(TIMER)!=TIMER_TEXT.encode():
        raise Stop('managed_unit_changed_refuse_rollback')
    # First deactivate V12's future autonomous work; then restore ONLY our runtime change.
    cmd('systemctl','disable','--now',TIMER_NAME)
    p=v9.browser_group()
    if limit_ok(p,NEW):set_high(p,NEW,OLD)
    elif not limit_ok(p,OLD):raise Stop('foreign_runtime_policy_refuse_rollback')
    print('SC VPS v12 rollback: timer disabled; browser runtime restored; containers untouched')
    return 0

def main():
    ap=argparse.ArgumentParser()
    opt=ap.add_mutually_exclusive_group(required=True)
    opt.add_argument('--apply',action='store_true')
    opt.add_argument('--run',action='store_true')
    opt.add_argument('--status',action='store_true')
    opt.add_argument('--rollback',action='store_true')
    opt.add_argument('--watchdog')
    a=ap.parse_args()
    if a.apply:return install()
    if a.run:return monitor()
    if a.status:return status()
    if a.rollback:return rollback()
    return watchdog(Path(a.watchdog))

if __name__=='__main__':
    try:sys.exit(main())
    except (Stop,v9.SafetyError,base.RescueError,ValueError,OSError,BlockingIOError) as e:
        print('SC_VPS_V12_SAFE_ABORT:',type(e).__name__,str(e)[:110],file=sys.stderr)
        sys.exit(2)
