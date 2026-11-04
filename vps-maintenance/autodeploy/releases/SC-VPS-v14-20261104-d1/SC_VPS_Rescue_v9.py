#!/usr/bin/env python3
"""v9: guarded one-time browser memory.high experiment with an independent rollback timer.

Never reads profiles, tokens, video, stream data or secrets. Never stops/restarts
containers, guard or websites. Changes only browser MemoryHigh, runtime-only, and
only when *live* cgroup memory.high throttling is causally proven.
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

import SC_VPS_Base_ReadOnly as base
import SC_VPS_Metrics_ReadOnly as metrics
import SC_VPS_Rescue_v8 as v8

VERSION = '9.0.0'
BROWSER = base.BROWSER
ROOT = Path('/var/lib/sc-vps-rescue-v9')
SOURCE = Path('/root/sc-vps-rescue-v9/SC_VPS_Rescue_v9.py')
MiB = 1024*1024
TARGET_INC = 96*MiB
MAX_HIGH = 704*MiB
MIN_HIGH = 256*MiB
MAX_BELOW_CURRENT = 128*MiB
MIN_AVAIL = 480  # MiB
MIN_SWAP = 200  # MiB
TRIAL_SECS = 7

class SafetyError(RuntimeError): pass

def tnow(): return dt.datetime.now(dt.timezone.utc).isoformat()

def r(path): return metrics.read_file(path).strip()

def asnum(txt):
    try:return int(txt)
    except (TypeError,ValueError):return None

def browser_group():
    groups=metrics.observed_cgroups()
    p=groups.get(BROWSER)
    if p is None or not str(p).startswith('/sys/fs/cgroup/system.slice/'):
        raise SafetyError('browser ControlGroup missing or outside system.slice; no mutation')
    if not (p/'memory.high').exists(): raise SafetyError('memory.high unavailable')
    return p

def protected(pre):
    now={'containers':{name:base.docker_state(name) for name in base.REQUIRED_CONTAINERS}}
    return base.docker_protected(pre,now)

def inspect(p):
    g=metrics.group_snapshot({'browser':p})['browser']
    h=metrics.host_snapshot()
    events=metrics.int_kv(r(p/'memory.events.local') or r(p/'memory.events'))
    ms=metrics.int_kv(r(p/'memory.stat'))
    return {'time':tnow(), 'path':str(p), 'high_bytes':asnum(r(p/'memory.high')),
        'max_bytes':asnum(r(p/'memory.max')),'current_bytes':asnum(r(p/'memory.current')),
        'swap_bytes':asnum(r(p/'memory.swap.current')),'events':events,
        'majfault':ms.get('pgmajfault'), 'host':h,
        'cpu_usage':g['cpu_stat'].get('usage_usec'),
        'memory_psi':metrics.psi_info(r(p/'memory.pressure'))}

def delta(a,b,key):
    x=a.get(key);y=b.get(key)
    return None if x is None or y is None or y<x else y-x

def psi_pct(a,b,kind='memory',which='full'):
    x=a['host']['psi'].get(kind,{}).get(which,{}).get('total')
    y=b['host']['psi'].get(kind,{}).get(which,{}).get('total')
    dt0=dt.datetime.fromisoformat(a['time']);dt1=dt.datetime.fromisoformat(b['time'])
    secs=(dt1-dt0).total_seconds()
    return None if x is None or y is None or secs<=0 or y<x else round((y-x)/(secs*10000),2)

def interval(a,b):
    return {'seconds':round((dt.datetime.fromisoformat(b['time'])-dt.datetime.fromisoformat(a['time'])).total_seconds(),2),
        'mem_full_pct':psi_pct(a,b), 'io_full_pct':psi_pct(a,b,'io'),
        'browser_high_events':delta(a['events'],b['events'],'high'),
        'browser_oom_kill':delta(a['events'],b['events'],'oom_kill'),
        'browser_major_faults':delta(a,b,'majfault'),
        'available_mib':round(b['host']['mem_available_kib']/1024,1) if b['host']['mem_available_kib'] is not None else None,
        'swap_free_mib':round(b['host']['swap_free_kib']/1024,1) if b['host']['swap_free_kib'] is not None else None,
        'high_mib':round(b['high_bytes']/MiB,1) if b['high_bytes'] is not None else None,
        'used_mib':round(b['current_bytes']/MiB,1) if b['current_bytes'] is not None else None}

def candidate(a,b,pre,now,basewin):
    if not protected(pre):return None,'protected_Docker_changed'
    u=pre['units'].get(BROWSER,{})
    if u.get('ActiveState')!='active' or u.get('MainPID') in ('','0'):return None,'browser_not_active'
    if base.unit_state(BROWSER).get('MainPID')!=u['MainPID']:return None,'browser_PID_changed'
    if a['path']!=b['path']:return None,'browser_group_changed'
    high=now['high_bytes'];current=now['current_bytes'];mx=now['max_bytes']
    if high is None or current is None:return None,'browser_high_unbounded_or_unreadable'
    if not MIN_HIGH<=high<=MAX_HIGH-TARGET_INC:return None,'browser_high_out_of_safe_range'
    if current<=high+16*MiB:return None,'memory_high_not_currently_binding'
    if current>high+MAX_BELOW_CURRENT:return None,'overshoot_too_large_for_96MiB_trial'
    if mx is not None and mx<=high+TARGET_INC+32*MiB:return None,'memory_max_too_close_to_target'
    if basewin['browser_high_events'] is None or basewin['browser_high_events']<20:return None,'no_live_memory_high_throttling'
    if basewin['mem_full_pct'] is None or basewin['mem_full_pct']<15:return None,'host_memory_full_not_confirmed'
    if basewin['io_full_pct'] is None or basewin['io_full_pct']>5:return None,'host_IO_stall_not_low'
    if basewin['browser_oom_kill'] is None or basewin['browser_oom_kill']>0:return None,'OOM_risk_or_unknown'
    if basewin['available_mib'] is None or basewin['available_mib']<MIN_AVAIL:return None,'available_RAM_insufficient'
    if basewin['swap_free_mib'] is None or basewin['swap_free_mib']<MIN_SWAP:return None,'available_swap_insufficient'
    # Do not relax a limit if systemd disagrees with kernel; cannot safely restore.
    systemd_high=asnum(base.get_prop(BROWSER,'MemoryHigh'))
    if systemd_high is None or abs(systemd_high-high)>4096:return None,'MemoryHigh_systemd_cgroup_mismatch'
    if not SOURCE.exists():return None,'watchdog_program_missing'
    return high+TARGET_INC,'eligible_for_runtime_memory_high_trial'

def set_high(p,expected,new):
    # Stop at any concurrent modification; systemd must be the sole owner.
    cur=asnum(r(p/'memory.high'))
    if cur is None or abs(cur-expected)>4096:raise SafetyError('memory.high changed concurrently; refusal')
    rc,_,err=base.run('systemctl','set-property','--runtime',BROWSER,f'MemoryHigh={new}',timeout=25)
    if rc!=0:raise SafetyError('set-property failed: '+err[:150])
    actual=asnum(r(p/'memory.high'))
    if actual is None or abs(actual-new)>4096:raise SafetyError(f'set-property verification failed: observed {actual}')

def journal(path,state):
    base.write_json(path,state)

def watchdog(jfile):
    base.require_root()
    # Called separately from systemd timer after 2 minutes; never touches Docker.
    jfile=Path(jfile)
    if not jfile.is_absolute() or ROOT not in jfile.parents or jfile.name!='state.json':
        raise SafetyError('invalid watchdog state path')
    st=json.loads(jfile.read_text(encoding='utf-8'))
    if st.get('version')!=VERSION or st.get('status') not in ('trial_scheduled','trial_applied','trial_running'):
        print('WATCHDOG: no pending trial');return 0
    try:p=browser_group()
    except SafetyError as e:
        print('WATCHDOG: browser cgroup not found',e);return 1
    if str(p)!=st.get('browser_cgroup'):
        print('WATCHDOG: browser cgroup changed; manual review required');return 1
    old=st.get('old_high');target=st.get('target_high')
    if not isinstance(old,int) or not isinstance(target,int):raise SafetyError('bad watchdog state')
    current=asnum(r(p/'memory.high'))
    if current == target:
        set_high(p,target,old)
        st['status']='watchdog_reverted';st['watchdog_at']=tnow();journal(jfile,st)
        print('WATCHDOG: runtime browser MemoryHigh restored to original, other services untouched')
    else:
        print('WATCHDOG: observed high different, no overwrite')
    return 0

def timer_start(jfile,pid):
    unit=f'sc-vps-v9-revert-{pid}'
    rc,out,err=base.run('systemd-run','--quiet','--unit='+unit,'--on-active=120s',
        '--timer-property=AccuracySec=1s','/usr/bin/python3',str(SOURCE),'--watchdog',str(jfile),timeout=20)
    if rc!=0:raise SafetyError('independent watchdog scheduling failed: '+err[:160])
    rc2,out2,_=base.run('systemctl','is-active',unit+'.timer',timeout=10)
    if rc2!=0 or out2.strip()!='active':
        raise SafetyError('independent watchdog timer not active; no mutation')
    return unit+'.timer'

def timer_cancel(timer):
    if not re.fullmatch(r'sc-vps-v9-revert-\d+\.timer',timer):raise SafetyError('invalid watchdog timer')
    rc,_,err=base.run('systemctl','stop',timer,timeout=15)
    return rc==0

def restore_if_expected(p,old,target):
    cur=asnum(r(p/'memory.high'))
    if cur is not None and abs(cur-target)<=4096:
        set_high(p,target,old)
        return True
    return cur is not None and abs(cur-old)<=4096

def run():
    base.require_root();os.umask(0o077);ROOT.mkdir(parents=True,mode=0o700,exist_ok=True)
    with open(ROOT/'lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        pre=base.snapshot()
        if not all(pre['containers'][x]['running'] for x in base.REQUIRED_CONTAINERS):
            print('STOP: protected Recorder/Gateway not healthy at preflight; no changes');return 2
        p=browser_group()
        runid=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+f'-{os.getpid()}'
        folder=ROOT/'runs'/runid;folder.mkdir(parents=True,mode=0o700)
        jfile=folder/'state.json'
        st={'version':VERSION,'utc':tnow(),'status':'diagnosis_only','changes':[],
            'browser_cgroup':str(p),'protected':pre['containers'],'old_high':None,'target_high':None}
        journal(jfile,st)
        a=inspect(p);time.sleep(6);b=inspect(p)
        win=interval(a,b);st['baseline']=win
        target,reason=candidate(a,b,pre,b,win)
        st['reason']=reason
        st['old_high']=b['high_bytes'];st['target_high']=target
        if target is not None:
            now=inspect(p)
            # No change if memory high, unit identity, or protected containers changed since sampling.
            target2,reason2=candidate(b,now,pre,now,win)
            if target2 != target or reason2 != reason:
                st['reason']='pre_mutation_conditions_changed';target=None
        if target is not None:
            timer=None;applied=False
            try:
                # Set pending state BEFORE independent timer; timer can undo even if SSH hangs.
                st['status']='trial_scheduled';journal(jfile,st)
                timer=timer_start(jfile,os.getpid());st['timer']=timer;journal(jfile,st)
                set_high(p,b['high_bytes'],target);applied=True
                st['status']='trial_applied';st['changes']=['browser_MemoryHigh_runtime_trial'];journal(jfile,st)
                c=inspect(p);time.sleep(TRIAL_SECS);d=inspect(p)
                aft=interval(c,d);st['after']=aft
                alive=protected(pre)
                stable=(alive and str(browser_group())==str(p) and base.unit_state(BROWSER).get('MainPID')==pre['units'][BROWSER]['MainPID'])
                oldfull=win['mem_full_pct'];newfull=aft['mem_full_pct']
                oldhigh=win['browser_high_events'];newhigh=aft['browser_high_events']
                improved=(stable and newfull is not None and oldfull is not None and
                    newfull<=oldfull*0.65 and oldfull-newfull>=10 and
                    newhigh is not None and oldhigh is not None and newhigh<=oldhigh*0.5 and
                    aft['available_mib'] is not None and aft['available_mib']>=350 and
                    aft['browser_oom_kill']==0 and
                    aft['io_full_pct'] is not None and aft['io_full_pct']<8)
                if improved:
                    st['status']='trial_kept_runtime';st['reason']='memory_full_and_high_events_both_improved'
                    st['changes']=['browser_MemoryHigh_runtime_increased']
                else:
                    if not restore_if_expected(p,b['high_bytes'],target):raise SafetyError('rollback not confirmed')
                    st['status']='trial_rolled_back';st['reason']='no_proven_memory_stall_improvement_or_safety_regression'
                    st['changes']=['browser_MemoryHigh_trial_restored']
            except (Exception,KeyboardInterrupt) as ex:
                st['error']=str(ex);st['status']='trial_error_requires_verification'
                if applied:
                    try:
                        if restore_if_expected(p,b['high_bytes'],target):
                            st['status']='trial_error_rolled_back';st['changes']=['browser_MemoryHigh_restored']
                    except Exception as rb:st['rollback_error']=str(rb)
            finally:
                # Never cancel watchdog unless current state is confirmed safe/old or explicitly kept.
                if timer and st['status'] in ('trial_kept_runtime','trial_rolled_back','trial_error_rolled_back'):
                    st['watchdog_cancelled']=timer_cancel(timer)
                journal(jfile,st)
        now={x:base.docker_state(x) for x in base.REQUIRED_CONTAINERS}
        st['final_docker_unchanged']=base.docker_protected(pre,{'containers':now})
        journal(jfile,st)
        lines=[f'SC VPS Rescue v{VERSION} | {st["status"]}',f'UTC={st["utc"]}',
            f'Protected Recorder/Gateway: {"UNCHANGED" if st["final_docker_unchanged"] else "CHANGED / NEEDS ATTENTION"}',
            f'Browser memory.high before: {round(b["high_bytes"]/MiB,1) if b["high_bytes"] is not None else "max"} MiB',
            f'Browser memory.current: {round(b["current_bytes"]/MiB,1) if b["current_bytes"] is not None else "unknown"} MiB',
            f'Browser memory.events.high HISTORICAL: {b["events"].get("high")}',
            f'Baseline 6s: global memory.full={win["mem_full_pct"]}%, browser high events={win["browser_high_events"]}, browser major faults={win["browser_major_faults"]}, RAM available={win["available_mib"]}MiB',
            f'Decision: {st["reason"]}',f'Actions: {st["changes"] or "none"}']
        if st.get('after'):
            x=st['after'];lines.append(f'After 7s: memory.full={x["mem_full_pct"]}%, high events={x["browser_high_events"]}, major faults={x["browser_major_faults"]}, RAM available={x["available_mib"]}MiB')
        if st.get('error'):lines.append('ERROR: '+st['error'])
        if st.get('rollback_error'):lines.append('ROLLBACK ERROR: '+st['rollback_error'])
        if st.get('timer'):lines.append('Independent timed rollback: '+st['timer']+f' (cancelled={st.get("watchdog_cancelled")})')
        lines+=['No Docker/Recorder/Guard restart; no recording deletion; no reading credentials.','Recorder file continuity and live guard verification remain separate.','Machine state: '+str(jfile)]
        report='\n'.join(lines)+'\n'; (folder/'REPORT.txt').write_text(report,encoding='utf-8');print(report,flush=True)
        if not st['final_docker_unchanged'] or st['status']=='trial_error_requires_verification':return 2
        return 4 if st['status']=='trial_kept_runtime' else 3

def rollback():
    base.require_root()
    if not ROOT.exists():print('No v9 state');return 0
    files=sorted((ROOT/'runs').glob('*/state.json'),reverse=True)
    for file in files:
        try:st=json.loads(file.read_text())
        except (ValueError,OSError):continue
        if st.get('version')!=VERSION or st.get('status')!='trial_kept_runtime':continue
        p=browser_group()
        if str(p)!=st.get('browser_cgroup'):raise SafetyError('browser identity changed; do not rollback blindly')
        old=st['old_high'];target=st['target_high']
        if not restore_if_expected(p,old,target):raise SafetyError('current high differs; manual review')
        st['status']='manually_rolled_back';st['rollback_at']=tnow();journal(file,st)
        print('v9 runtime MemoryHigh restored to pre-v9 value; no service stopped');return 0
    print('No committed v9 runtime change to rollback');return 0

def main(argv=None):
    ap=argparse.ArgumentParser()
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--apply',action='store_true');mode.add_argument('--rollback',action='store_true');mode.add_argument('--watchdog')
    opt=ap.parse_args(argv)
    if opt.watchdog:return watchdog(Path(opt.watchdog))
    if opt.rollback:return rollback()
    return run()

if __name__=='__main__':
    try:sys.exit(main())
    except (SafetyError,base.RescueError,OSError,ValueError,BlockingIOError) as exc:
        print('SAFE ABORT:',str(exc),file=sys.stderr,flush=True);sys.exit(1)
