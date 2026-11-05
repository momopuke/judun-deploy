#!/usr/bin/env python3
"""SC VPS v13: authenticated signed-release installer and outbound encrypted telemetry.

Creates only its two scoped systemd units; no inbound listener, no recorder,
Gateway, Caddy or browser restarts, and no secret/video/config/log read.
Reports contain only bounded cgroup/PSI and signed-agent acceptance metadata.
The open relay sees RSA-OAEP-encrypted zlib JSON, never plaintext metrics.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zlib

VERSION = '13.0.0'
ROOT = Path('/var/lib/sc-vps-rescue-v13')
SOURCE = Path('/root/sc-vps-rescue-v13/SC_VPS_Rescue_v13.py')
SERVICE_NAME = 'sc-vps-telemetry.service'
TIMER_NAME = 'sc-vps-telemetry.timer'
SERVICE = Path('/etc/systemd/system') / SERVICE_NAME
TIMER = Path('/etc/systemd/system') / TIMER_NAME
UPLINK = 'https://ntfy.sh/scvps-rpt-652c87a58df9966126491eb9c37281f2da81c7f7'
PUBLIC_KEY = '''-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAysqXvfOjCZNnCo9l53EF
DEbcAxiIiV1UOdk/xVXEmRiyY76QcgCmcm9JCBWzxv6jQtyPw868PNZsD18D3Pde
rszy5T+hj0TSJfbqLeLaQOYzixPuFhNHkbrxWkWkTVzDm847sVMh/2YYj0pa6nxc
JRwEe1vdv5c3zuQCmHjGTnYFwiYy5tL+Fyk4nteup3+y5vFkXA2qa9lBoPkpMru3
ezPlyddHVAY7iq5UlXah+t0dUIJhoHYL/QAc9wZCXow7erEd4PUVkm0+s7YjeEX2
DChD+7ihOwnrmTCO5qOZQbiC9U14As0guv4DtqvjQ0syl2rGx3nAy3JnHzYKhBVC
6XBgaJRXxu45Smj+P4l3zmBzBs6PdgMN0TgJcaERiUxD0z4n2H1LMdcQy6VwoZWC
Hgog1m60SUYCIpRrh8MDdKhhnnXOdRzA5Mm8DZ0b0A3HLXo03MzrfsptDYNgj8u3
jLPJPmKrKwcJMNL6EQuCg23mmC8eB0GMSpEZovZj0YwVW+j2zfQrmn3E9h8nDysG
Aspaj6Sgy3biW8oRn4JvVsbgNH8vdDpKqXXCu6RZmLKIiTUg5M6VJUslIqnExSVD
D9SKPhlKG0bn+oySmxgDe4GB/TLZieAia1+lNuv2WuUPEc8Ydr4unpcSFOOLd+hN
iCnEcF7w4tCASUvd0bTYj4ECAwEAAQ==
-----END PUBLIC KEY-----
'''

SERVICE_TEXT = '''# SC-VPS-TELEMETRY-MANAGED-v13
[Unit]
Description=SC VPS minimal encrypted outbound health report
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v13/SC_VPS_Rescue_v13.py --report
CPUQuota=25%
MemoryMax=110M
Nice=18
IOSchedulingClass=idle
TimeoutStartSec=60s
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
'''
TIMER_TEXT = '''# SC-VPS-TELEMETRY-MANAGED-v13
[Unit]
Description=SC VPS send encrypted diagnostics every ten minutes
[Timer]
OnBootSec=180s
OnUnitInactiveSec=600s
AccuracySec=15s
RandomizedDelaySec=10s
Persistent=false
Unit=sc-vps-telemetry.service
[Install]
WantedBy=timers.target
'''

class Stop(RuntimeError): pass

def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def safe_read(path,maxbytes=9000):
    if path.is_symlink():raise Stop('unsafe_symlink')
    if not path.exists():return None
    if not path.is_file() or path.stat().st_size>maxbytes:raise Stop('unsafe_file')
    return path.read_bytes()

def command(*a,timeout=15):
    try:r=subprocess.run(a,check=False,capture_output=True,text=True,timeout=timeout)
    except (OSError,subprocess.TimeoutExpired):raise Stop('command_failed_'+a[0])
    if r.returncode!=0:raise Stop('command_failed_'+a[0])
    return r.stdout.strip()

def write_atomic(path,obj):
    path.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
    if path.is_symlink():raise Stop('state_symlink')
    fd,tmp=tempfile.mkstemp(prefix='.telemetry-',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as fp:
            os.fchmod(fp.fileno(),0o600)
            json.dump(obj,fp,sort_keys=True,separators=(',',':'),ensure_ascii=True)
            fp.write('\n');fp.flush();os.fsync(fp.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def json_status(path,keys):
    try:
        b=safe_read(path,maxbytes=50000)
        obj=json.loads(b) if b is not None else {}
        if not isinstance(obj,dict):return {}
        return {k:obj.get(k) for k in keys}
    except (Stop,OSError,ValueError,UnicodeError):return {}

def latest_v12():
    p=Path('/var/lib/sc-vps-rescue-v12/runs')
    try:files=sorted(p.glob('*/state.json'),reverse=True)[:3]
    except OSError:return {}
    for f in files:
        d=json_status(f,('status','reason','utc','baseline','windows'))
        if d:return d
    return {}

def sanitize(s):
    if not isinstance(s,str):return ''
    return s[:55] if re.fullmatch(r'[a-zA-Z0-9_.-]{1,55}',s[:55]) else 'other'

def psi(path,label):
    try:
        for line in path.read_text().splitlines():
            if line.startswith(label+' '):
                m=re.search(r'avg10=([0-9]+(?:\.[0-9]+)?)',line)
                return round(float(m.group(1)),2) if m else None
    except (OSError,ValueError):pass
    return None

def meminfo():
    d={}
    try:
        for row in Path('/proc/meminfo').read_text().splitlines():
            k,_,v=row.partition(':')
            if k in ('MemAvailable','SwapFree','SwapTotal'):
                d[k]=round(int(v.split()[0])/1024)
    except (OSError,ValueError,IndexError):pass
    return d

def cgroup():
    cg=command('systemctl','show','-p','ControlGroup','--value','stripchat-browser-desktop.service',timeout=8)
    if not re.fullmatch(r'/system\.slice/stripchat-browser-desktop\.service',cg):raise Stop('unexpected_browser_cgroup')
    p=Path('/sys/fs/cgroup')/cg.lstrip('/')
    if p.is_symlink() or not p.is_dir():raise Stop('unsafe_cgroup')
    return p

def kv(path):
    d={}
    try:
        for line in path.read_text().splitlines():
            z=line.split()
            if len(z)==2 and z[1].isdigit():d[z[0]]=int(z[1])
    except OSError:pass
    return d

def cgroup_counters(p):
    try:
        high=int((p/'memory.high').read_text().strip());current=int((p/'memory.current').read_text().strip())
    except (ValueError,OSError):return None
    events=kv(p/'memory.events.local');stats=kv(p/'memory.stat')
    if events.get('high') is None or stats.get('pgmajfault') is None:return None
    return {'mh':round(high/1048576,1),'mc':round(current/1048576,1),
            'high':events['high'],'pf':stats['pgmajfault'],'ok':events.get('oom_kill')}

def protected():
    def run(*a):
        try:r=subprocess.run(a,check=False,capture_output=True,text=True,timeout=8)
        except (OSError,subprocess.TimeoutExpired):return None
        return r.stdout.strip() if r.returncode==0 else None
    b=run('systemctl','show','--value','-p','MainPID','stripchat-browser-desktop.service')
    ids=[]
    for name in ('stripchat-recorder','stripchat-gateway'):
        s=run('docker','inspect','--format','{{.Id}}|{{.State.Running}}',name)
        ids.append(s if s and s.endswith('|true') else None)
    return b if b and b!='0' else None,ids

def build_report(delay=4):
    t0=time.monotonic()
    before=protected()
    try:
        p=cgroup();a=cgroup_counters(p)
    except (Stop,OSError,ValueError):
        p=None;a=None
    time.sleep(delay)
    b=cgroup_counters(p) if p is not None else None
    after=protected()
    secs=max(.1,time.monotonic()-t0)
    valid=bool(a and b and b['high']>=a['high'] and b['pf']>=a['pf'])
    mem=meminfo();v12=latest_v12()
    agent=json_status(Path('/var/lib/sc-vps-autodeploy/state.json'),('last_sequence','status','operation'))
    timer=subprocess.run(['systemctl','is-active','sc-vps-browser-autotune.timer'],check=False,
                         capture_output=True,text=True,timeout=8).stdout.strip()
    report={'v':13,'ts':int(time.time()),'seq':agent.get('last_sequence'),
      'ag':sanitize(agent.get('status')),'op':sanitize(agent.get('operation')),
      'v12':sanitize(v12.get('status')),'why':sanitize(v12.get('reason')),
      'tm':timer=='active','mh':b['mh'] if valid else None,
      'mc':b['mc'] if valid else None,
      'av':mem.get('MemAvailable'),'sf':mem.get('SwapFree'),
      'cp':psi(Path('/proc/pressure/cpu'),'some'),
      'mf':psi(Path('/proc/pressure/memory'),'full'),
      'hi':round((b['high']-a['high'])/secs,1) if valid else None,
      'pf':round((b['pf']-a['pf'])/secs,1) if valid else None,
      'ok':b['ok'] if valid else None,
      'pr':bool(before[0] and before==after and all(after[1])),
      'r':bool(after[1][0]),'g':bool(after[1][1])}
    return report

def encrypt(data):
    plain=zlib.compress(json.dumps(data,sort_keys=True,separators=(',',':')).encode(),9)
    if len(plain)>430:raise Stop('report_size_exceeds_RSA_OAEP')
    with tempfile.TemporaryDirectory(prefix='scvps-rsa-',dir='/tmp') as td:
        folder=Path(td);key=folder/'pub.pem';src=folder/'plain';dst=folder/'cipher'
        key.write_text(PUBLIC_KEY);src.write_bytes(plain)
        command('openssl','pkeyutl','-encrypt','-pubin','-inkey',str(key),
            '-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256',
            '-pkeyopt','rsa_mgf1_md:sha256','-in',str(src),'-out',str(dst),timeout=12)
        out=dst.read_bytes()
        if len(out)!=512:raise Stop('bad_cipher_length')
        return base64.b64encode(out)

def send(enc):
    req=urllib.request.Request(UPLINK,data=enc,method='POST',headers={
        'Content-Type':'text/plain','Title':'SC VPS encrypted telemetry','Priority':'1',
        'User-Agent':'SCVPS-v13-telemetry/1'})
    try:
        with urllib.request.urlopen(req,timeout=14) as resp:
            if resp.status not in (200,201):raise Stop('relay_bad_http_status')
            resp.read(2048)
    except (urllib.error.URLError,TimeoutError) as e:raise Stop('relay_unreachable') from e

def publish():
    if os.geteuid()!=0:raise Stop('root_required')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(ROOT/'lock','a+') as lk:
        try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('report_already_running')
        data=build_report()
        # Plaintext never leaves the server; root-only snapshot is safe for local recovery.
        write_atomic(ROOT/'last_report.json',data)
        ciphertext=encrypt(data)
        send(ciphertext)
        print('SC_VPS_TELEMETRY_ENCRYPTED_UPLOAD_PASS ts='+str(data['ts']),flush=True)
        return 0

def install():
    if os.geteuid()!=0:raise Stop('root_required')
    if not SOURCE.is_file() or SOURCE.is_symlink():raise Stop('v13_source_not_installed')
    wanted={SERVICE:SERVICE_TEXT.encode(),TIMER:TIMER_TEXT.encode()}
    for path,data in wanted.items():
        old=safe_read(path)
        if old is not None and old!=data:raise Stop('foreign_unit_conflict_'+path.name)
    installed=[]
    try:
        for path,data in wanted.items():
            if not path.exists():
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
                with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
                installed.append(path)
        command('systemctl','daemon-reload')
        command('systemctl','enable','--now',TIMER_NAME,timeout=30)
        if command('systemctl','is-active',TIMER_NAME)!='active':raise Stop('timer_not_active')
        ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
        write_atomic(ROOT/'install.json',{'at':utc(),'status':'encrypted_telemetry_timer_installed',
            'timer':TIMER_NAME,'browser_modified':False,'docker_modified':False})
        print('SC_VPS_V13_TIMER_INSTALLED; protected services unchanged')
    except Exception:
        if installed:
            subprocess.run(['systemctl','disable','--now',TIMER_NAME],capture_output=True,timeout=15)
            for p in installed:
                if safe_read(p)==wanted[p]:p.unlink()
            subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=15)
        raise
    try:return publish()
    except Stop as exc:
        # The ten-minute timer stays installed for transient networking failures.
        print('SC_VPS_V13_INSTALL_PASS_UPLOAD_PENDING reason='+str(exc))
        return 0

def status():
    inst=json_status(ROOT/'install.json',('at','status','timer'))
    last=json_status(ROOT/'last_report.json',('v','ts','seq','ag','v12','why','mh','av','sf','mf','hi','pf'))
    print('SC_VPS_V13_INSTALL',json.dumps(inst,sort_keys=True))
    print('SC_VPS_V13_LATEST',json.dumps(last,sort_keys=True))
    return 0

def rollback():
    if os.geteuid()!=0:raise Stop('root_required')
    if safe_read(SERVICE)!=SERVICE_TEXT.encode() or safe_read(TIMER)!=TIMER_TEXT.encode():raise Stop('managed_unit_changed')
    command('systemctl','disable','--now',TIMER_NAME,timeout=30)
    print('SC_VPS_V13_TELEMETRY_DISABLED; old rescue timers untouched')
    return 0

def main():
    ap=argparse.ArgumentParser()
    group=ap.add_mutually_exclusive_group(required=True)
    for name in ('apply','report','status','rollback'):group.add_argument('--'+name,action='store_true')
    a=ap.parse_args()
    if a.apply:return install()
    if a.report:return publish()
    if a.status:return status()
    return rollback()

if __name__=='__main__':
    try:raise SystemExit(main())
    except (Stop,OSError,ValueError,subprocess.TimeoutExpired) as e:
        print('SC_VPS_V13_SAFE_ABORT:',type(e).__name__,str(e)[:120],flush=True)
        raise SystemExit(3)
