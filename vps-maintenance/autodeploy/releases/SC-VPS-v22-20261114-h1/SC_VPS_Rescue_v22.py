#!/usr/bin/env python3
"""Signed low-impact CPU attribution and background uploader prioritization.

Never stops or restarts protected processes, changes browser policies, or touches media.
Only renices an exact allowlisted host-side background uploader when measured busy.
"""
from __future__ import annotations
import argparse, base64, json, os, re, stat, subprocess, tempfile, time
import urllib.request, urllib.error
from pathlib import Path
import SC_VPS_Rescue_v15 as telemetry
from SC_VPS_Rescue_v17 import PUBLIC_KEY

ROOT = Path('/var/lib/sc-vps-cpu-guard-v22')
SOURCE = Path('/root/sc-vps-rescue-v22/SC_VPS_Rescue_v22.py')
SERVICE = Path('/etc/systemd/system/sc-vps-cpu-guard-v22.service')
TIMER = Path('/etc/systemd/system/sc-vps-cpu-guard-v22.timer')
UNIT = 'sc-vps-cpu-guard-v22'
HZ = os.sysconf('SC_CLK_TCK')
# Exact trusted background *host* tasks, not recording/streaming services.
ALLOWED = {'/root/strip_2g_integrity.py': 'backup_integrity',
           '/root/auto_upload.py': 'backup_upload',
           '/root/strip_auto_upload.py': 'backup_upload'}
SERVICE_TEXT = '''# SC-VPS-CPU-GUARD-v22
[Unit]
Description=SC VPS bounded CPU attribution and safe backup scheduling
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 -B /root/sc-vps-rescue-v22/SC_VPS_Rescue_v22.py --sample
CPUQuota=3%
MemoryMax=48M
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=70s
NoNewPrivileges=yes
PrivateTmp=yes
'''
TIMER_TEXT = '''# SC-VPS-CPU-GUARD-v22
[Unit]
Description=SC VPS bounded read-only CPU attribution every ten minutes
[Timer]
OnActiveSec=30s
OnUnitInactiveSec=600s
AccuracySec=20s
RandomizedDelaySec=10s
Unit=sc-vps-cpu-guard-v22.service
[Install]
WantedBy=timers.target
'''

class Refused(RuntimeError): pass

def execute(*args,timeout=18):
    try:
        p=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as e:
        raise Refused('command_unavailable') from e
    if p.returncode:raise Refused('systemd_operation_failed')
    return p.stdout.strip()

def proc_stat(raw):
    before, end, after=raw.rpartition(')')
    pid, sep, name=before.partition(' (')
    fields=after.split()
    if not end or not sep or len(fields)<20:raise ValueError('invalid_proc_stat')
    return int(pid),int(fields[19]),name,int(fields[11])+int(fields[12]),int(fields[16])

def identify(argv,cgroup):
    if b'/docker' in cgroup or b'docker-' in cgroup or b'/kubepods' in cgroup or b'/containerd' in cgroup:
        return 'container',False
    if b'stripchat-' in cgroup or b'livevpn-' in cgroup:return 'protected_unit',False
    parts=[part.decode('utf8','replace') for part in argv.split(b'\0') if part]
    if not parts:return 'unknown',False
    executable=Path(parts[0]).name.lower()
    if executable.startswith(('python','pypy')):
        scripts=[p for p in parts[1:3] if p.startswith('/') and p.endswith('.py')]
        if scripts and scripts[0] in ALLOWED:
            return ALLOWED[scripts[0]],True
        if scripts:
            basename=Path(scripts[0]).name
            safe_name=re.sub(r'[^A-Za-z0-9_.-]', '_', basename)[:36]
            return 'python:'+safe_name,False
        if '-m' in parts[1:3]:
            module=parts[parts.index('-m')+1] if parts.index('-m')+1<len(parts) else ''
            safe_name=re.sub(r'[^A-Za-z0-9_.-]', '_', module)[:28]
            return 'python_module:'+safe_name,False
        return 'python_other',False
    return (executable if executable in ('rclone','ffmpeg','node','chromium','dockerd') else 'other'),False

def snapshot():
    epoch=time.monotonic()
    with open('/proc/stat',encoding='ascii') as f:
        fields=list(map(int,f.readline().split()[1:9]))
    total=sum(fields);idle=fields[3]+fields[4]
    processes={}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():continue
        try:
            pid,start,name,ticks,nice=proc_stat((entry/'stat').read_text(errors='replace'))
            cmd=(entry/'cmdline').read_bytes()[:512]
            cg=(entry/'cgroup').read_bytes()[:1024]
            tag,allow=identify(cmd,cg)
            if name.startswith('python') and tag in ('other','unknown'):tag='python_other'
            processes[(pid,start)]=(ticks,tag,allow,nice)
        except (OSError,ValueError):continue
    return epoch,total,idle,processes

def compare(a,b):
    sec=b[0]-a[0];diff=b[1]-a[1];idle=b[2]-a[2]
    if sec<=0 or diff<=0 or not 0<=idle<=diff:raise Refused('cpu_window_invalid')
    rows=[]
    for ident,(ticks,tag,allow,nice) in b[3].items():
        old=a[3].get(ident)
        if old and ticks>=old[0]:
            cpu=round(100*(ticks-old[0])/HZ/sec,1)
            if cpu>0:rows.append((cpu,ident,tag,allow,nice))
    rows.sort(reverse=True,key=lambda x:x[0])
    return round(100*(diff-idle)/diff,1),rows

def still_allowed(identity,expected_tag):
    pid,start=identity
    entry=Path('/proc')/str(pid)
    try:
        actual_pid,actual_start,name,ticks,nice=proc_stat((entry/'stat').read_text(errors='replace'))
        info=(entry/'status').read_text()
        uid_line=next(x for x in info.splitlines() if x.startswith('Uid:')).split()
        cmd=(entry/'cmdline').read_bytes()[:512]
        cg=(entry/'cgroup').read_bytes()[:1024]
        tag,allow=identify(cmd,cg)
        return (pid==actual_pid and start==actual_start and allow and tag==expected_tag
                and int(uid_line[1])==0 and nice<10)
    except (OSError,ValueError,StopIteration):return False

def sample(duration=8,adjust=True):
    before=snapshot();time.sleep(duration);after=snapshot()
    busy,rows=compare(before,after)
    changed=[]
    if adjust and busy>=90:
        for cpu,identity,tag,allow,nice in rows:
            if cpu<25:break
            if allow and still_allowed(identity,tag):
                try:
                    os.setpriority(os.PRIO_PROCESS,identity[0],10)
                    changed.append([tag,round(cpu,1),nice,10])
                except (OSError,PermissionError):pass
    output={'busy':busy,'n':len(rows),'top':[[tag,cpu] for cpu,_,tag,_,_ in rows[:5]],
            'low_priority':changed,'s':round(after[0]-before[0],1)}
    return output

def deliver(result):
    telemetry.PUBLIC_KEY=PUBLIC_KEY  # Correct rotated RSA receiver key (v17+), not v15 legacy
    payload={'v':22,'k':'cpu_diag','seq':22,'ts':int(time.time()),**result}
    packet=telemetry.encrypt(payload)
    for address in (telemetry.UPLINK.replace('https://ntfy.sh/','https://ntfy.envs.net/'),telemetry.UPLINK):
        req=urllib.request.Request(address,data=packet,method='POST',headers={
            'Content-Type':'text/plain','Title':'SC VPS encrypted CPU diagnosis v22',
            'Priority':'1','User-Agent':'SCVPS-cpu-guard-v22/1'})
        try:
            with urllib.request.urlopen(req,timeout=9) as response:
                if response.status in (200,201):return
        except (OSError,urllib.error.URLError,TimeoutError):pass
    raise Refused('relay_unavailable')

def unit_body(path):
    if path.is_symlink():raise Refused('unit_symlink_refused')
    try:
        st=path.stat()
    except FileNotFoundError:return None
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode & 0o022:
        raise Refused('untrusted_unit_preserved')
    return path.read_bytes()

def put_if_absent(path,body):
    old=unit_body(path)
    if old is not None:
        if old!=body:raise Refused('foreign_unit_preserved')
        return False
    fd,name=tempfile.mkstemp(prefix='.sc-vps-v22-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),0o644);f.write(body);f.flush();os.fsync(f.fileno())
        os.link(name,path)
    finally:
        os.unlink(name)
    return True

# Only the exact older CPU guard units signed and installed by us may be retired.
LEGACY_GUARDS={
  20:{'service': '26364f1bb571aabcdfc3a6dc7c448d5bd37cee1d255f13c9460414785bd1238f', 'timer': '52f530ac10abe6933c36bb31318405a4f5bebdc2246d68c322be6e6ca49a4b0f'},
  21:{'service': '5364daaa3c95c75f804cc8f24313e29297df9ac7ee05685c830e3b2617653fd7', 'timer': 'e23305f4608441d9d16bb5b9877048a6394c5148c86a70d4eb375b9bb7ab7231'},
}

def approved_legacy():
    import hashlib
    to_retire=[]
    for v,fingerprints in LEGACY_GUARDS.items():
        base=Path('/etc/systemd/system/sc-vps-cpu-guard-v'+str(v))
        service=Path(str(base)+'.service')
        timer=Path(str(base)+'.timer')
        a=unit_body(service);b=unit_body(timer)
        if a is None and b is None:continue
        if a is None or b is None or hashlib.sha256(a).hexdigest()!=fingerprints['service'] or hashlib.sha256(b).hexdigest()!=fingerprints['timer']:
            raise Refused('legacy_guard_foreign_preserved')
        to_retire.append(timer.name)
    return to_retire

def install():
    if os.geteuid()!=0 or SOURCE.is_symlink() or not SOURCE.is_file():raise Refused('signed_source_required')
    old_timers=approved_legacy()  # Preflight ALL legacy units before writing anything.
    sample(duration=.5,adjust=False)
    fresh=[];enabled=False;disabled=[]
    try:
        for path,body in ((SERVICE,SERVICE_TEXT.encode()),(TIMER,TIMER_TEXT.encode())):
            if put_if_absent(path,body):fresh.append((path,body))
        execute('systemctl','daemon-reload')
        execute('systemctl','enable','--now',TIMER.name)
        enabled=True
        if execute('systemctl','is-active',TIMER.name)!='active':raise Refused('timer_inactive')
        # First independently encrypted read-only receipt must reach the relay
        # before retiring any previous diagnostic timer.
        deliver(sample(duration=.8,adjust=False))
        for old in old_timers:
            execute('systemctl','disable','--now',old)
            disabled.append(old)
    except Exception:
        for old in reversed(disabled):
            try:execute('systemctl','enable','--now',old)
            except Refused:pass
        if enabled:
            try:execute('systemctl','disable','--now',TIMER.name)
            except Refused:pass
        for path,body in fresh:
            if unit_body(path)==body:path.unlink()
        if fresh:
            try:execute('systemctl','daemon-reload')
            except Refused:pass
        raise
    print('SC_VPS_V22_CPU_GUARD_INSTALLED legacy_retired='+str(len(disabled)))

def rollback():
    if os.geteuid()!=0:raise Refused('root_required')
    for path,body in ((SERVICE,SERVICE_TEXT.encode()),(TIMER,TIMER_TEXT.encode())):
        if unit_body(path) not in (None,body):raise Refused('foreign_unit_preserved')
    execute('systemctl','disable','--now',TIMER.name)
    for path in (SERVICE,TIMER):
        if path.exists():path.unlink()
    execute('systemctl','daemon-reload')

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    for name in ('apply','sample','status','rollback'):
        g.add_argument('--'+name,action='store_true')
    a=p.parse_args()
    if a.apply:return install()
    if a.rollback:return rollback()
    if a.status:
        print(json.dumps({'unit':unit_body(SERVICE)==SERVICE_TEXT.encode(),
                          'timer':unit_body(TIMER)==TIMER_TEXT.encode()}));return
    data=sample();deliver(data);print('SC_VPS_V22_CPU_SAMPLE_SENT')

if __name__=='__main__':
    try:main()
    except (Refused,OSError,ValueError) as e:
        print('SC_VPS_V22_SAFE_ABORT',type(e).__name__,str(e)[:64]);raise SystemExit(3)
