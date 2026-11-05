#!/usr/bin/env python3
"""SC VPS Rescue v8: identify memory reclaim / swap churn / runnable thread owners.

Read-only, service-scoped operations. Never reads media contents, app profiles,
credentials or network destinations. Never restarts/stops/changes any service.
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

import SC_VPS_Base_ReadOnly as v5
import SC_VPS_Metrics_ReadOnly as v7

VERSION = '8.0.0'
STATE = Path('/var/lib/sc-vps-rescue-v8')
KEYS = ('pswpin','pswpout','pgmajfault','pgfault','pgscan_direct','pgscan_kswapd',
        'pgsteal_direct','pgsteal_kswapd','oom_kill','allocstall')
CGKEYS = ('anon','file','shmem','slab','pgmajfault','pgfault',
          'pgscan','pgsteal','workingset_refault_anon','workingset_refault_file')
MAX_THREADS = 12000
MAX_PIDS = 2500


def system_vmstat():
    d = v7.int_kv(v7.read_file('/proc/vmstat'))
    return {key:sum(value for k,value in d.items() if k.startswith(key))
            for key in KEYS}


def mem_values(path):
    return v7.int_kv(v7.read_file(path/'memory.stat'))


def to_int(txt):
    try: return int(txt.strip())
    except (ValueError, TypeError, AttributeError): return None


def group_more(groups):
    out={}
    for name,root in groups.items():
        if not v7.safe_cgroup_path('/'+str(root).split('/sys/fs/cgroup/')[-1]):
            continue
        d = mem_values(root)
        out[name]={
            'memory_bytes': to_int(v7.read_file(root/'memory.current')),
            'memory_swap_bytes': to_int(v7.read_file(root/'memory.swap.current')),
            'memory_high': v7.read_file(root/'memory.high').strip()[:30],
            'memory_max': v7.read_file(root/'memory.max').strip()[:30],
            'pids_current': to_int(v7.read_file(root/'pids.current')),
            'memory_events': v7.int_kv(v7.read_file(root/'memory.events')),
            'memory_stat': {k:d.get(k) for k in CGKEYS if k in d},
            'memory_pressure':v7.psi_info(v7.read_file(root/'memory.pressure')),
        }
    return out


def diff_count(first, second):
    if first is None or second is None or second<first:
        return None
    return second-first


def mapping_threads(groups):
    """Count actual kernel task states in known cgroups; avoid cmdline/env exposure.

    Enumerates /proc/*/task/* stat, bounded for one-core low-memory host.
    Does not change or signal tasks.
    """
    reverse=sorted(((str(path).removeprefix('/sys/fs/cgroup'),name)
                    for name,path in groups.items()),key=lambda x:len(x[0]),reverse=True)
    result={name:{'R':0,'D':0,'S':0,'other':0,'pids':0,'threads':0} for name in groups}
    result['[other]']={'R':0,'D':0,'S':0,'other':0,'pids':0,'threads':0}
    nthreads=0; npids=0
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal(): continue
        npids+=1
        if npids>MAX_PIDS: break
        cg=v7.read_file(entry/'cgroup')
        cgline=next((x[3:] for x in cg.splitlines() if x.startswith('0::')),None)
        if cgline is None: continue
        category=next((name for path,name in reverse if cgline==path or cgline.startswith(path.rstrip('/')+'/')),'[other]')
        b=result[category];b['pids']+=1
        try: tasks=(entry/'task').iterdir()
        except OSError:continue
        try:
            for task in tasks:
                if nthreads>=MAX_THREADS:break
                content=v7.read_file(task/'stat')
                # /proc/PID/task/TID/stat contains a parenthesized comm which may have spaces.
                idx=content.rfind(') ')
                if idx<0:continue
                fields=content[idx+2:].split()
                if not fields:continue
                st=fields[0]
                b[st if st in ('R','D','S') else 'other']+=1
                b['threads']+=1
                nthreads+=1
        except OSError:pass
        if nthreads>=MAX_THREADS:break
    return {'groups':result,'scan_pids':npids,'scan_threads':nthreads,
            'capped':npids>MAX_PIDS or nthreads>=MAX_THREADS}


def grab(groups):
    return {'at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'host':v7.host_snapshot(), 'vmstat':system_vmstat(),
            'groups':group_more(groups), 'tasks':mapping_threads(groups)}


def signals(v7samples,frames):
    out=[]
    if len(v7samples)>=2:
        for x in v7samples:
            if x['pressure']['cpu']['some_interval_pct'] is None:
                out.append('cpu_psi_measurement_unavailable');break
        if all(x['pressure']['cpu']['some_interval_pct'] is not None and x['pressure']['cpu']['some_interval_pct']>=85 for x in v7samples):
            out.append('persistent_cpu_scheduler_contention')
        if any(x['pressure']['memory']['full_interval_pct'] is not None and x['pressure']['memory']['full_interval_pct']>=15 for x in v7samples):
            out.append('serious_memory_full_stall')
        if any(x['usage'].get('steal_pct',0)>15 for x in v7samples):
            out.append('significant_hypervisor_steal')
        if all(x['usage'].get('idle_pct') is not None and x['usage']['idle_pct']<3 for x in v7samples):
            out.append('no_host_idle_cpu')
    if len(frames)>=2:
        d={k:diff_count(frames[0]['vmstat'].get(k),frames[1]['vmstat'].get(k)) for k in KEYS}
        if (d.get('pswpin') or 0)+(d.get('pswpout') or 0)>=100:
            out.append('swap_churn_measured')
        if (d.get('pgmajfault') or 0)>=25:out.append('major_page_faults_measured')
        if (d.get('pgscan_direct') or 0)>=100:out.append('direct_memory_reclaim_measured')
        if (d.get('oom_kill') or 0)>0:out.append('oom_kill_during_sampling')
        for name,stat in frames[1]['groups'].items():
            if stat.get('memory_bytes') is not None and stat['memory_bytes']>=512*1024**2:
                out.append('high_memory_cgroup:'+name)
        t=frames[1]['tasks']['groups']
        for name,val in t.items():
            if val.get('R',0)>=10:out.append('many_runnable_threads:'+name)
    return sorted(set(out)) or ['insufficient_evidence_of_single_owner']


def recommendation(flags,v7samples,frames):
    """No unsafe alteration; prioritize one verifiable intervention, not another blind quota tweak."""
    if 'oom_kill_during_sampling' in flags:
        return 'EMERGENCY: OOM during sampling; maintain services, back up, reduce workload or approve capacity increase; no blind browser quota change.'
    if 'significant_hypervisor_steal' in flags:
        return 'Cloud CPU steal is high; review provider host contention; changing cgroup quotas will not resolve host steal.'
    if 'serious_memory_full_stall' in flags or 'swap_churn_measured' in flags:
        return ('Host resource contention confirmed. Determine which browser/other unit owns memory and runnable tasks; '
                'only retire a verified-unused browser session after protection/login is independently confirmed, '
                'or approve capacity upgrade. Keep recorder and guards untouched.')
    if 'persistent_cpu_scheduler_contention' in flags:
        return ('CPU is oversubscribed; identify high runnable-task service. '
                'Do not raise browser quota while host idle is near zero.')
    return 'Insufficient conclusive cause; no mutation performed; compare host PSI and cgroup task ownership.'


def write_report(folder, state):
    frames=state['frames'];ss=state['cpu_samples']
    lines=[f"SC VPS Rescue v{VERSION} | {state['status']}",
        f"UTC: {state['utc']}",
        'Protected Docker: '+', '.join(f"{n}={'UP' if info['running'] else 'DOWN'}" for n,info in state['protected'].items()),
        'Actions: NONE (read-only by design; no guessing with live streams/guards)',
        'Root causes: '+', '.join(state['signals']),
        'Decision: '+state['recommendation']]
    for i,s in enumerate(ss,1):
        cp=s['pressure']['cpu'];mem=s['pressure']['memory'];io=s['pressure']['io']
        lines.append(f"INTERVAL {i}: CPU busy={s['usage'].get('productive_pct')}% idle={s['usage'].get('idle_pct')}% "
            f"iowait={s['usage'].get('iowait_pct')}% steal={s['usage'].get('steal_pct')}% "
            f"CPU_wait={cp.get('some_interval_pct')}% memory_full={mem.get('full_interval_pct')}% "
            f"io_full={io.get('full_interval_pct')}% load1={s['load1']} runqueue={s['runqueue']}")
    delta={key:diff_count(frames[0]['vmstat'].get(key),frames[-1]['vmstat'].get(key)) for key in KEYS}
    lines.append('VMSTAT delta: '+', '.join(f'{k}={v}' for k,v in delta.items()))
    last=frames[-1]
    lines.append('RUNNABLE THREADS BY OWNER (R=ready/running D=uninterruptible sleep):')
    for name,v in sorted(last['tasks']['groups'].items(),key=lambda item:(-item[1]['R'],-item[1]['D'])):
        if v['threads']:
            lines.append(f"  {name}: R={v['R']} D={v['D']} S={v['S']} other={v['other']} total={v['threads']} procs={v['pids']}")
    lines.append('CGROUP MEMORY (MiB, exact cgroup accounting not a unique-process sum):')
    for name,v in sorted(last['groups'].items(),key=lambda item:-(item[1].get('memory_bytes') or 0)):
        m=v['memory_bytes'];sw=v['memory_swap_bytes'];events=v['memory_events']
        first=frames[0]['groups'].get(name,{})
        old=first.get('memory_stat',{});new=v['memory_stat']
        page_d=diff_count(old.get('pgmajfault'),new.get('pgmajfault'))
        psi=v['memory_pressure'].get('full',{}).get('avg10')
        lines.append(f"  {name}: current={round(m/1048576,1) if m is not None else '?'} "
            f"swap={round(sw/1048576,1) if sw is not None else '?'} "
            f"anon={round(new.get('anon',0)/1048576,1)} "
            f"pids={v['pids_current']} pgmajfault_delta={page_d} "
            f"memory_full_avg10={psi} events={events}")
    lines.append('NOTE: do not treat throttled periods as proof of spare CPU; saturated host and memory reclaim require workload-level changes.')
    lines.append('Recorder file continuity, live stream and Guard moderation NOT proven by this diagnostic.')
    lines.append('Machine report: '+str(folder/'state.json'))
    body='\n'.join(lines)+'\n'
    (folder/'REPORT.txt').write_text(body,encoding='utf-8')
    print(body,flush=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnose',action='store_true',required=True)
    args=parser.parse_args(argv)
    v5.require_root();os.umask(0o077)
    STATE.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (STATE/'lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another v8 run active')
        pre=v5.snapshot()
        if not all(pre['containers'][k]['running'] for k in v5.REQUIRED_CONTAINERS):
            print('Protected recorder/gateway not running; cannot interpret safe repair; no changes.',flush=True)
            return 2
        groups=v7.observed_cgroups()
        if not groups:
            print('No cgroup metrics available; no changes.',flush=True)
            return 1
        # v7.sample adds host/cgroup interval observations. Each frame is paired
        # with a bounded task-state and memory snapshot.
        f0=grab(groups)
        ss=[v7.sample(groups,3),v7.sample(groups,3)]
        f1=grab(groups)
        fl=signals(ss,[f0,f1])
        folder=STATE/'runs'/(dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+f'-{os.getpid()}')
        folder.mkdir(mode=0o700,parents=True,exist_ok=False)
        protected={n:v5.docker_state(n) for n in v5.REQUIRED_CONTAINERS}
        same=v5.docker_protected(pre,{'containers':protected})
        state={'version':VERSION,'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
               'status':'protected_containers_changed' if not same else 'diagnosis_only',
               'protected':protected,'cpu_samples':ss,'frames':[f0,f1],
               'signals':fl,'recommendation':recommendation(fl,ss,[f0,f1]),'actions':[]}
        v5.write_json(folder/'state.json',state)
        write_report(folder,state)
        return 2 if not same else 3

if __name__=='__main__':
    try:sys.exit(main())
    except (RuntimeError, OSError, ValueError, v5.RescueError) as e:
        print('[ERROR]',type(e).__name__,str(e)[:240],file=sys.stderr,flush=True)
        sys.exit(1)
