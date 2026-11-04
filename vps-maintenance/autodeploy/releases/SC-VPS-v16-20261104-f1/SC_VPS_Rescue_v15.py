#!/usr/bin/env python3
"""SC VPS v15: outbound encrypted host-acceptance receipts, no inbound port.

Read-only collection: CPU/memory/io PSI, browser memory.high/current/events,
root-disk space, signed deploy state, v14 cleanup receipt and protected state.
Never lists videos, usernames, logs or credentials. No video/container restarts.
V15 uses an owner-held RSA receiver key: HTTPS relay sees ciphertext only.
"""
from __future__ import annotations
import argparse,base64,datetime as dt,fcntl,json,os,re,stat,subprocess,tempfile,time,urllib.request,urllib.error,zlib
from pathlib import Path

VERSION='15.0.0'
ROOT=Path('/var/lib/sc-vps-telemetry-v15')
SOURCE=Path('/root/sc-vps-rescue-v15/SC_VPS_Rescue_v15.py')
SERVICE=Path('/etc/systemd/system/sc-vps-telemetry-v15.service')
TIMER=Path('/etc/systemd/system/sc-vps-telemetry-v15.timer')
UPLINK='https://ntfy.sh/scvps-rpt-652c87a58df9966126491eb9c37281f2da81c7f7'
PUBLIC_KEY='''-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAwo5En5+nvmjWduNzo9KM
4vM4VKs+wPlJvhSTXkrl6IkD6cXKnkBZIC96OW3Dsfn8DjS7N4EZGQuSNtf7kZEV
nF/mwH1rWR805R3d5xaGG48c45xN0/ge1ZWCCo7EhzTsrIwrpaRm/GZG99Lsxk1K
k6jZDBJLg/v5m+vFXeipuYkRpk4BzBr3lCHkUVJBPOZQQ9GF0x3vR5NjjYHnIQF4
RrIsjG04OjtvgEWqV5hSVCVNfJrnxb1j8aBgQZlSXiY5QNCBT/pr4d/KqH8PUidH
T3YxRDgL20uaGE0hZdQU2GiFK2fVrwgS+Y6maExvJ3rorYdDzftumJH7pJhudujW
lP35A2Ad0a+MZ8HXDJ5QqmJPNDvbR2UaR7v32Pd/m4LOo5FBmnhBiXjT61sRQknC
Jl75BNenpUvNFryKRn/MLW0xxAaa09QWDwDU2FqiVXdO/RduYA8QQk9BWZX9R7/5
pCY+d2GXFyziFHb+NMb14dDxo/Oyh/HYtHiz5c/jMuYIqGTZxtAlUe3z1TA2qvqn
Ojn+CRaeVD1BWjjjaJAw3dqXxirtYj183vEGo8T6aOBpjW0Ch85fxrcPtkvZw9Jf
k0WTCaIbhMK4StVCxue8P96uKqpT08vnjCGqfdWYskuRnUd15MyUG4QbiHoJqss3
gEtid+snu6spRvavHDG3evkCAwEAAQ==
-----END PUBLIC KEY-----
'''
SERVICE_TEXT='''# SC-VPS-TELEMETRY-MANAGED-v15
[Unit]
Description=SC VPS encrypted health and cleanup receipt
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v15/SC_VPS_Rescue_v15.py --report
CPUQuota=15%
MemoryMax=96M
Nice=19
IOSchedulingClass=idle
TimeoutStartSec=60s
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
'''
TIMER_TEXT='''# SC-VPS-TELEMETRY-MANAGED-v15
[Unit]
Description=SC VPS encrypted host receipt every ten minutes
[Timer]
OnBootSec=120s
OnUnitInactiveSec=600s
AccuracySec=15s
RandomizedDelaySec=15s
Persistent=false
Unit=sc-vps-telemetry-v15.service
[Install]
WantedBy=timers.target
'''
class Refused(RuntimeError):pass

def cmd(*args,timeout=12):
    try:r=subprocess.run(args,capture_output=True,text=True,timeout=timeout,check=False)
    except (OSError,subprocess.TimeoutExpired) as e:raise Refused('command_error:'+args[0]) from e
    if r.returncode:raise Refused('command_failure:'+args[0]+':'+str(r.returncode))
    return r.stdout.strip()

def read_json(path,maxbytes=16000):
    try:
        if path.is_symlink() or not path.is_file():return {}
        st=path.stat()
        if st.st_size>maxbytes or st.st_uid!=0:return {}
        data=json.loads(path.read_bytes())
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError,UnicodeError):return {}

def safe_write(path,obj):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.is_symlink():raise Refused('state_symlink')
    fd,name=tempfile.mkstemp(dir=path.parent,prefix='.v15-')
    try:
        with os.fdopen(fd,'w',encoding='ascii') as f:
            os.fchmod(f.fileno(),0o600)
            json.dump(obj,f,sort_keys=True,separators=(',',':'),ensure_ascii=True)
            f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)

def psi(kind,name):
    try:
        for line in (Path('/proc/pressure')/kind).read_text().splitlines():
            if line.startswith(name+' '):
                m=re.search(r'avg10=([0-9]+(?:\.[0-9]+)?)',line)
                return round(float(m.group(1)),2) if m else None
    except (OSError,ValueError):pass
    return None

def meminfo():
    out={}
    try:
        for line in Path('/proc/meminfo').read_text().splitlines():
            key,_,v=line.partition(':')
            if key in ('MemAvailable','SwapFree'):
                out[key]=round(int(v.split()[0])/1024)
    except (OSError,ValueError,IndexError):pass
    return out

def browser():
    try:
        group=cmd('systemctl','show','-p','ControlGroup','--value','stripchat-browser-desktop.service',timeout=8)
        if group!='/system.slice/stripchat-browser-desktop.service':return None
        root=Path('/sys/fs/cgroup')/group.lstrip('/')
        if root.is_symlink() or not root.is_dir():return None
        high=int((root/'memory.high').read_text().strip())
        cur=int((root/'memory.current').read_text().strip())
        d={}
        for line in (root/'memory.events.local').read_text().splitlines():
            a=line.split()
            if len(a)==2 and a[1].isdigit():d[a[0]]=int(a[1])
        if 'high' not in d or 'oom_kill' not in d:return None
        return {'g':root,'h':d['high'],'o':d['oom_kill'],'mh':round(high/1048576),'mc':round(cur/1048576)}
    except (Refused,OSError,ValueError):return None

def protected():
    statuses=[]
    for name in ('stripchat-recorder','stripchat-gateway'):
        try:
            state=cmd('docker','inspect','--format','{{.State.Running}}',name,timeout=8)
            statuses.append(state=='true')
        except Refused:statuses.append(False)
    return statuses

def clean_result():
    d=read_json(Path('/var/lib/sc-vps-cleanup-v14/last_cleanup.json'))
    t=d.get('at')
    good=(d.get('status')=='cleanup_pass' and isinstance(t,str) and
          all(type(d.get(k))==int and 0<=d[k]<=1000000000 for k in ('removed','freed_bytes','errors')))
    if not good:return None
    return {'n':d['removed'],'b':d['freed_bytes'],'err':d['errors'],'at':t[:19]}

def safe_short(value):
    return str(value)[:40] if isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,40}',value) else None

def report_data(delay=3):
    b=browser();start=time.monotonic();time.sleep(delay);c=browser();elapsed=max(.1,time.monotonic()-start)
    valid=bool(b and c and b['g']==c['g'] and c['h']>=b['h'] and c['o']>=b['o'])
    mem=meminfo();agent=read_json(Path('/var/lib/sc-vps-autodeploy/state.json'))
    cleanup=clean_result();dstat=os.statvfs('/')
    try:load=round(os.getloadavg()[0],2)
    except OSError:load=None
    try:v14=cmd('systemctl','is-active','sc-vps-diagnostics-retention.timer',timeout=5)=='active'
    except Refused:v14=False
    return {'v':15,'ts':int(time.time()),'seq':agent.get('last_sequence') if type(agent.get('last_sequence'))==int else None,
            'ag':safe_short(agent.get('status')),'cpu':psi('cpu','some'),'mf':psi('memory','full'),
            'io':psi('io','full'),'av':mem.get('MemAvailable'),'sf':mem.get('SwapFree'),
            'mh':c['mh'] if valid else None,'mc':c['mc'] if valid else None,
            'hi':round((c['h']-b['h'])/elapsed,1) if valid else None,
            'om':c['o']-b['o'] if valid else None,'ld':load,
            'fd':round(dstat.f_bavail*dstat.f_frsize/1048576),
            'pr':protected(),'timer14':v14,'cl':cleanup}

def encrypt(data):
    plain=zlib.compress(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode(),9)
    if len(plain)>430:raise Refused('report_payload_too_large')
    with tempfile.TemporaryDirectory(prefix='scvps-v15-') as td:
        folder=Path(td);pub=folder/'pub';src=folder/'src';enc=folder/'dst'
        pub.write_text(PUBLIC_KEY);src.write_bytes(plain)
        cmd('/usr/bin/openssl','pkeyutl','-encrypt','-pubin','-inkey',str(pub),
            '-pkeyopt','rsa_padding_mode:oaep','-pkeyopt','rsa_oaep_md:sha256',
            '-pkeyopt','rsa_mgf1_md:sha256','-in',str(src),'-out',str(enc))
        result=enc.read_bytes()
        if len(result)!=512:raise Refused('invalid_ciphertext_length')
        return base64.b64encode(result)

def send(data):
    req=urllib.request.Request(UPLINK,data=data,method='POST',headers={
        'Content-Type':'text/plain','Title':'SC VPS encrypted metrics v15',
        'Priority':'1','User-Agent':'SCVPS-telemetry-v15/1'})
    try:
        with urllib.request.urlopen(req,timeout=12) as resp:
            if resp.status not in (200,201):raise Refused('unexpected_relay_http_status')
            resp.read(1024)
    except (urllib.error.URLError,TimeoutError) as e:raise Refused('relay_unavailable') from e

def report():
    if os.geteuid()!=0:raise Refused('root_required')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(ROOT/'lock','a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        data=report_data();safe_write(ROOT/'last_report.json',data)
        send(encrypt(data))
        print('SC_VPS_V15_REPORT_PASS v=15 ts='+str(data['ts']),flush=True)
    return 0

def read_unit(path):
    if path.is_symlink():raise Refused('unit_symlink')
    if not path.exists():return None
    s=path.stat()
    if not stat.S_ISREG(s.st_mode) or s.st_size>8000:raise Refused('unexpected_unit_file')
    return path.read_bytes()

def install():
    if os.geteuid()!=0:raise Refused('root_required')
    if SOURCE.is_symlink() or not SOURCE.is_file():raise Refused('signed_source_not_installed')
    wanted={SERVICE:SERVICE_TEXT.encode(),TIMER:TIMER_TEXT.encode()}
    old={k:read_unit(k) for k in wanted}
    if any(old[k] is not None and old[k]!=v for k,v in wanted.items()):raise Refused('foreign_unit_conflict')
    added=[]
    try:
        for path,data in wanted.items():
            if old[path] is None:
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
                with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
                added.append(path)
        cmd('systemctl','daemon-reload');cmd('systemctl','enable','--now',TIMER.name)
        if cmd('systemctl','is-active',TIMER.name)!='active':raise Refused('timer_inactive')
        safe_write(ROOT/'install.json',{'status':'v15_host_receipt_timer_installed','at':dt.datetime.now(dt.timezone.utc).isoformat(),
              'protected_restarts':0,'videos_deleted':0})
    except Exception:
        if added:
            subprocess.run(['systemctl','disable','--now',TIMER.name],capture_output=True,timeout=15)
            for path in added:
                if read_unit(path)==wanted[path]:path.unlink()
            subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=15)
        raise
    try:return report()
    except Refused as e:
        print('SC_VPS_V15_INSTALLED_REPORT_PENDING',str(e)[:90]);return 0

def status():
    i=read_json(ROOT/'install.json');r=read_json(ROOT/'last_report.json')
    print('SC_VPS_V15_STATUS',json.dumps({'install':i,'report':r},sort_keys=True));return 0

def rollback():
    if os.geteuid()!=0:raise Refused('root_required')
    if read_unit(SERVICE)!=SERVICE_TEXT.encode() or read_unit(TIMER)!=TIMER_TEXT.encode():raise Refused('foreign_unit_modified')
    cmd('systemctl','disable','--now',TIMER.name)
    print('SC_VPS_V15_TIMER_DISABLED; original telemetry still active');return 0

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    for name in ('apply','report','status','rollback'):g.add_argument('--'+name,action='store_true')
    a=p.parse_args();return install() if a.apply else report() if a.report else status() if a.status else rollback()
if __name__=='__main__':
    try:raise SystemExit(main())
    except (Refused,OSError,ValueError,BlockingIOError) as e:
        print('SC_VPS_V15_SAFE_ABORT',type(e).__name__,str(e)[:120]);raise SystemExit(3)
