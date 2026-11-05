#!/usr/bin/env python3
"""Guarded browser pressure repair and exact-remote-size verified merge cleanup.

Application services/containers are never restarted. Resource trials are runtime
only, independently rolled back after interruption, and monitored after acceptance.
Only settled upload_ready merges with an unambiguous existing uploader route and
a matching remote object may be removed. Live recordings and source files remain.
"""
from __future__ import annotations
import argparse,ast,fcntl,json,os,re,stat,subprocess,time,urllib.request,urllib.error
from pathlib import Path
from statistics import median
import SC_VPS_Rescue_v15 as v15
import SC_VPS_Rescue_v16 as v16
import SC_VPS_Rescue_v17 as v17
import SC_VPS_Rescue_v13 as v13

VERSION='18.1.1'
BUILD=4
ROOT=Path('/var/lib/sc-vps-maintenance-v18')
SOURCE=Path('/root/sc-vps-rescue-v18/SC_VPS_Rescue_v18.py')
SERVICE=Path('/etc/systemd/system/sc-vps-maintenance-v18.service')
TIMER=Path('/etc/systemd/system/sc-vps-maintenance-v18.timer')
CG=v17.CG
UNIT='stripchat-browser-desktop.service'
MiB=1048576
OLD_HIGH=546*MiB
NEW_HIGH=674*MiB
OLD_CPU=20
NEW_CPU=50
NEW_MAX=768*MiB
REMOTE='pikpak:/Stripchat備份'
UPLINK=v15.UPLINK.replace('https://ntfy.sh/','https://ntfy.envs.net/')
READY=Path('/root/upload_ready')
SERVICE_TEXT='''# SC-VPS-MAINTENANCE-MANAGED-v18
[Unit]
Description=SC VPS guarded contention repair and verified merge cleanup
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v18/SC_VPS_Rescue_v18.py --run
CPUQuota=20%
MemoryMax=160M
Nice=15
IOSchedulingClass=idle
TimeoutStartSec=250s
NoNewPrivileges=yes
PrivateTmp=yes
'''
TIMER_TEXT='''# SC-VPS-MAINTENANCE-MANAGED-v18
[Unit]
Description=SC VPS accepted runtime policy safety check and cleanup
[Timer]
OnActiveSec=10s
OnUnitInactiveSec=600s
AccuracySec=15s
RandomizedDelaySec=10s
Unit=sc-vps-maintenance-v18.service
[Install]
WantedBy=timers.target
'''

def state():return v15.read_json(ROOT/'state.json',maxbytes=30000)
def save(s):v15.safe_write(ROOT/'state.json',s)
def number(path):
    x=(v17.read(path) or '').strip()
    return int(x) if x.isdecimal() else None

def quota():
    a=(v17.read(CG/'cpu.max') or '').split()
    if len(a)!=2 or not all(x.isdecimal() for x in a) or int(a[1])==0:return None
    return round(100*int(a[0])/int(a[1]),3)

def identity():
    out=[]
    for name in ('stripchat-recorder','stripchat-gateway'):
        raw=v15.cmd('docker','inspect','--format','{{.Id}} {{.State.Running}} {{.State.StartedAt}}',name,timeout=8).split()
        if len(raw)!=3 or raw[1]!='true' or not re.fullmatch('[0-9a-f]{64}',raw[0]):raise v15.Refused('protected_unavailable')
        out.append(raw)
    raw=v15.cmd('systemctl','show',UNIT,'-p','ActiveState','-p','MainPID','-p','ControlGroup',timeout=8)
    u=dict(x.split('=',1) for x in raw.splitlines() if '=' in x)
    if u.get('ActiveState')!='active' or not u.get('MainPID','').isdigit() or int(u['MainPID'])<1 or u.get('ControlGroup')!='/system.slice/'+UNIT:
        raise v15.Refused('browser_identity_invalid')
    out.append(u['MainPID']);return out

def matching(high,cpu):return number(CG/'memory.high')==high and quota()==cpu

def set_policy(old_high,old_cpu,new_high,new_cpu):
    if not matching(old_high,old_cpu):raise v15.Refused('concurrent_policy_change')
    v15.cmd('systemctl','set-property','--runtime',UNIT,'MemoryHigh='+str(new_high),'CPUQuota='+str(new_cpu)+'%',timeout=15)
    if not matching(new_high,new_cpu):raise v15.Refused('policy_write_unverified')

def set_max(old,new):
    if number(CG/'memory.max')!=old:raise v15.Refused('concurrent_memory_max_change')
    v15.cmd('systemctl','set-property','--runtime',UNIT,'MemoryMax='+str(new),timeout=15)
    if number(CG/'memory.max')!=new:raise v15.Refused('memory_max_write_unverified')

def measure(delay=10):
    a=v15.browser();ca=v16.cpu_stat();start=time.monotonic();bc=v16.browser_cpu()
    time.sleep(delay)
    b=v15.browser();cb=v16.cpu_stat();end=v16.browser_cpu();elapsed=max(.1,time.monotonic()-start)
    if not a or not b or a['g']!=b['g'] or b['h']<a['h'] or b['o']<a['o']:raise v15.Refused('browser_counters_unavailable')
    use=None
    if ca and cb:
        d=cb['total']-ca['total'];idle=cb['idle']-ca['idle']
        if d>0 and 0<=idle<=d:use=round(100*(d-idle)/d,1)
    mem=v15.meminfo()
    return {'cpu':v15.psi('cpu','some'),'mf':v15.psi('memory','full'),'io':v15.psi('io','full'),
            'av':mem.get('MemAvailable'),'sf':mem.get('SwapFree'),
            'hi':round((b['h']-a['h'])/elapsed,1),'oom':b['o'],'mc':b['mc'],
            'bp':round((end-bc)/10000/elapsed,1) if bc is not None and end is not None and end>=bc else None,
            'use':use,'cf':v17.pressure(CG/'cpu.pressure')[1],
            'mh':b['mh'],'q':quota(),'mx':number(CG/'memory.max')}

def safe(s,oom):
    keys=('av','sf','mf','io','use','hi','cf','bp','mc','cpu','oom')
    return all(type(s.get(k)) in (int,float) for k in keys) and s['oom']==oom and s['av']>=370 and s['sf']>=300 and s['mf']<=55 and s['io']<=5

def memory_helped(pre,windows):
    if len(windows)!=3 or not all(safe(w,pre['oom']) for w in windows):return False
    tail=windows[-2:]
    return median(w['hi'] for w in tail)<=max(20,pre['hi']*.25) and median(w['mf'] for w in tail)<=max(5,pre['mf']*.5)

def cpu_helped(pre,windows):
    if len(windows)!=3 or not all(safe(w,pre['oom']) and w['use']<=90 for w in windows):return False
    tail=windows[-2:]
    return median(w['cf'] for w in tail)<=max(5,pre['cf']-15)

def watchdog_name(n):return isinstance(n,str) and re.fullmatch(r'sc-vps-v18-rollback-[0-9]+\.timer',n) is not None

def arm(s):
    name='sc-vps-v18-rollback-'+str(os.getpid())
    v15.cmd('systemd-run','--quiet','--unit='+name,'--on-active=300s','--timer-property=AccuracySec=1s',
            '/usr/bin/python3',str(SOURCE),'--watchdog',timeout=15)
    if v15.cmd('systemctl','is-active',name+'.timer',timeout=6)!='active':raise v15.Refused('watchdog_unavailable')
    s['watchdog']=name+'.timer';save(s)

def disarm(s):
    n=s.get('watchdog')
    if not watchdog_name(n):raise v15.Refused('watchdog_name_invalid')
    v15.cmd('systemctl','stop',n,timeout=10)

def restore(s):
    # Only roll back values this version can have written; a third-party policy
    # is preserved and explicitly reported for review.
    h=number(CG/'memory.high');q=quota()
    if h not in (OLD_HIGH,NEW_HIGH) or q not in (OLD_CPU,NEW_CPU):raise v15.Refused('foreign_policy_preserved')
    if h!=OLD_HIGH or q!=OLD_CPU:set_policy(h,q,OLD_HIGH,OLD_CPU)
    if s.get('max_raised'):
        old=s.get('original_max');current=number(CG/'memory.current')
        if type(old)!=int or number(CG/'memory.max')!=NEW_MAX:raise v15.Refused('foreign_memory_max_preserved')
        # Lowering a hard cap below resident use can kill the browser. Restore
        # the soft policy first and defer the hard cap until resident use drains.
        if current is None or current>old-16*MiB:
            s['status']='rolled_back_max_pending';s['finished']=int(time.time());save(s);return
        set_max(NEW_MAX,old);s['max_raised']=False
    s['status']='rolled_back';s['finished']=int(time.time());save(s)

def watchdog():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    s=state()
    if s.get('v')!=18 or s.get('status') not in ('trial','needs_review','rolled_back_max_pending'):return 0
    restore(s);return 0

def windows(s,ids,high,cpu):
    out=[]
    for _ in range(3):
        w=measure();out.append(w)
        s['windows']=out;save(s)
        if identity()!=ids or not matching(high,cpu) or not safe(w,s['pre']['oom']):raise v15.Refused('trial_health_regression')
    return out

def repair(s):
    ids=identity();pre=measure();s.update(v=18,status='observed',pre=pre,post=pre,measured_at=int(time.time()),started=int(time.time()));save(s)
    if s.get('accepted'):
        h=number(CG/'memory.high');q=quota()
        if h not in (OLD_HIGH,NEW_HIGH) or q not in (OLD_CPU,NEW_CPU):
            s.update(status='refused',reason='unknown_existing_policy');save(s);return
        cap=number(CG/'memory.max');original=s.get('original_max')
        target_cap=max(NEW_MAX,original) if type(original)==int else None
        if cap not in (original,target_cap):
            s.update(status='refused',reason='unknown_existing_hard_cap');save(s);return
        if not safe(pre,s.get('oom',pre['oom'])) or pre['use']>95:
            restore(s);s['reason']='accepted_policy_regression';save(s)
        elif matching(NEW_HIGH,NEW_CPU) and cap==target_cap:
            s.update(status='verified',post=pre,reason='accepted_policy_still_safe',finished=int(time.time()));save(s)
        else:
            # A daemon-reload can restore an older persisted value over a
            # runtime property. Reconcile only our measured, recorded policy.
            s['status']='trial';save(s);arm(s)
            try:
                if type(cap)==int and cap<target_cap:
                    s['max_raised']=True;save(s);set_max(cap,target_cap)
                set_policy(h,q,NEW_HIGH,NEW_CPU)
                result=windows(s,ids,NEW_HIGH,NEW_CPU)
                baseline=s.get('baseline') or pre
                if not memory_helped(baseline,result) or not cpu_helped(baseline,result):raise v15.Refused('reconciliation_health_failed')
                s.update(status='verified',post=result[-1],reason='verified_policy_reconciled',finished=int(time.time()))
                save(s);disarm(s)
            except Exception as error:
                s.update(status='needs_review',reason=str(error)[:90]);save(s);restore(s)
                if s['status']=='rolled_back':disarm(s)
        return
    if not matching(OLD_HIGH,OLD_CPU):s.update(status='refused',reason='unknown_existing_policy');save(s);return
    maximum=number(CG/'memory.max')
    reserve=max((NEW_HIGH-OLD_HIGH)//MiB,max(0,(NEW_MAX-(maximum or NEW_MAX))//MiB))
    if not safe(pre,pre['oom']) or pre['av']<560 or pre['av']-reserve<400 or maximum is not None and maximum<=OLD_HIGH:
        s.update(status='refused',reason='insufficient_reserve');save(s);return
    if maximum is None and (v17.read(CG/'memory.max') or '').strip()!='max':
        s.update(status='refused',reason='memory_max_unavailable');save(s);return
    if pre['hi']<80 or pre['mf']<15 or pre['cf']<15 or pre['use']>75:
        s.update(status='refused',reason='causal_threshold_not_met');save(s);return
    s.update(status='trial',accepted=False,baseline=pre,identities=ids,old_high=OLD_HIGH,old_cpu=OLD_CPU,oom=pre['oom'],original_max=maximum,build=BUILD);save(s)
    arm(s)
    try:
        if identity()!=ids:raise v15.Refused('identity_changed_before_change')
        if maximum is not None and maximum<NEW_MAX:
            s['max_raised']=True;save(s);set_max(maximum,NEW_MAX)
        set_policy(OLD_HIGH,OLD_CPU,NEW_HIGH,OLD_CPU)
        mem=windows(s,ids,NEW_HIGH,OLD_CPU);s['memory_windows']=mem;save(s)
        before_cpu=mem[-1]
        set_policy(NEW_HIGH,OLD_CPU,NEW_HIGH,NEW_CPU)
        cpu=windows(s,ids,NEW_HIGH,NEW_CPU);s['cpu_windows']=cpu;save(s)
        if not memory_helped(pre,cpu):raise v15.Refused('combined_memory_trial_not_beneficial')
        if not cpu_helped(pre,cpu):raise v15.Refused('cpu_trial_not_beneficial')
        s.update(status='verified',accepted=True,post=cpu[-1],reason='measured_memory_and_cpu_full_stall_reduction',finished=int(time.time()))
        save(s);disarm(s)
    except BaseException as error:
        s.update(status='needs_review',reason=str(error)[:90]);save(s)
        try:restore(s);disarm(s)
        except Exception:s['rollback_pending']=True;save(s)
        if isinstance(error,(KeyboardInterrupt,SystemExit)):raise

def regular(path):
    try:
        x=path.lstat();return stat.S_ISREG(x.st_mode) and x.st_uid==0 and x.st_nlink==1
    except OSError:return False

def upload_route_known():
    p=Path('/root/strip_2g_integrity.py')
    if not regular(p) or p.stat().st_size>180000:return False
    try:
        strings=[n.value for n in ast.walk(ast.parse(p.read_text())) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
    except (OSError,SyntaxError,UnicodeError):return False
    return any(x.rstrip('/') in (REMOTE,'pikpak:Stripchat備份') for x in strings) and str(READY) in strings

def open_files():
    out=set();limit=0
    try:
        for p in Path('/proc').iterdir():
            if not p.name.isdecimal():continue
            try:
                for f in (p/'fd').iterdir():
                    limit+=1
                    if limit>30000:raise v15.Refused('fd_inventory_bound')
                    try:out.add(os.readlink(f).removesuffix(' (deleted)'))
                    except OSError:pass
            except (FileNotFoundError,PermissionError):continue
    except OSError as e:raise v15.Refused('fd_inventory_incomplete') from e
    return out

def fingerprint(path):
    x=path.lstat();return (x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)

def verified_remote(path,size):
    rel=path.relative_to(READY)
    if len(rel.parts)!=2 or any(x.startswith('.') or x in ('','..') for x in rel.parts):return False
    try:
        raw=v15.cmd('rclone','lsjson',REMOTE+'/'+rel.as_posix(),'--stat','--no-modtime','--no-mimetype',timeout=18)
        d=json.loads(raw)
    except (v15.Refused,ValueError):return False
    return isinstance(d,dict) and d.get('IsDir') is False and d.get('Name')==path.name and type(d.get('Size'))==int and d['Size']==size

def inventory(root):
    n=b=old=ob=0;bound=False
    if root.is_symlink() or not root.is_dir():return [0,0,0,0,False]
    for parent,dirs,files in os.walk(root,followlinks=False):
        dirs[:]=[x for x in dirs if not (Path(parent)/x).is_symlink()]
        if len(Path(parent).relative_to(root).parts)>=4:dirs[:]=[]
        for name in files:
            p=Path(parent)/name
            if not regular(p):continue
            try:x=p.stat()
            except OSError:continue
            n+=1;b+=x.st_size
            if time.time()-x.st_mtime>=10800:old+=1;ob+=x.st_size
            if n>=10000:bound=True;break
        if bound:break
    return [n,round(b/MiB),old,round(ob/MiB),bound]

def cleanup():
    result={'n':0,'b':0,'err':0,'reason':'no_verified_ready_merges','inventory':[]}
    route=upload_route_known()
    result['route']=route
    if route and not READY.is_symlink() and READY.is_dir():
        opened=open_files();examined=0
        for folder in READY.iterdir():
            if folder.is_symlink() or not folder.is_dir() or folder.stat().st_uid!=0:continue
            for p in folder.iterdir():
                examined+=1
                if examined>1500 or result['n']>=3:break
                if not regular(p) or not p.name.endswith('_MERGE.mkv') or str(p) in opened:continue
                try:
                    f=fingerprint(p)
                    if time.time()-p.stat().st_mtime<10800 or not 0<f[2]<=3*1024**3:continue
                    if verified_remote(p,f[2]) and regular(p) and fingerprint(p)==f and str(p) not in open_files():
                        p.unlink();result['n']+=1;result['b']+=f[2]
                        result['reason']='remote_verified_merge_copies_removed'
                except (OSError,v15.Refused):result['err']+=1
            if examined>1500 or result['n']>=3:break
    elif not route:result['reason']='uploader_route_not_verified'
    try:result['inventory']=[inventory(Path(x)) for x in ('/root/videos','/root/staging','/root/upload_ready')]
    except OSError:result['err']+=1
    log=Path('/tmp/auto_upload.log')
    if regular(log):
        with log.open('rb') as f:
            f.seek(max(0,log.stat().st_size-131072));tail=f.read(131072).decode('utf8','replace')
        result['upload']=[int(log.stat().st_mtime),tail.count('REMOTE SIZE VERIFIED'),tail.count('SOURCE DELETE AFTER REMOTE VERIFY'),tail.count('UPLOAD VERIFY FAIL')]
    v15.safe_write(ROOT/'last_cleanup.json',result);return result

def forward_errors():
    try:raw=v15.cmd('journalctl','-u','livevpn-stripchat-forward.service','-n','80','--no-pager','-o','cat',timeout=8)[-32768:].lower()
    except v15.Refused:return []
    patterns=('input/output error','connection refused','timed out','404','403','401','invalid','broken pipe','no such file')
    return [i for i,p in enumerate(patterns) if p in raw]

def compact(x):return [x.get(k) for k in ('cpu','mf','hi','av','mc','bp','use','cf','mh','q')]

def retire_legacy():
    retired=[]
    for version,module in ((13,v13),(15,v15),(16,v16),(17,v17)):
        if v15.read_unit(module.SERVICE)==module.SERVICE_TEXT.encode() and v15.read_unit(module.TIMER)==module.TIMER_TEXT.encode():
            v15.cmd('systemctl','disable','--now','--no-reload',module.TIMER.name,timeout=10)
            retired.append(version)
    legacy_service=Path('/etc/systemd/system/sc-vps-browser-autotune.service')
    legacy_timer=Path('/etc/systemd/system/sc-vps-browser-autotune.timer')
    service=v15.read_unit(legacy_service);timer=v15.read_unit(legacy_timer)
    if service and timer and __import__('hashlib').sha256(service).hexdigest()=='43ae1fd3a34bff741e804431670d8039bc546ddbccebac77367af720b2114995' and __import__('hashlib').sha256(timer).hexdigest()=='89f9105de3bd399632b3a495b9a75b4259484dac68c3f2d791f209e82c85a428':
        v15.cmd('systemctl','disable','--now','--no-reload',legacy_timer.name,timeout=10);retired.append(12)
    v15.safe_write(ROOT/'retired_diagnostics.json',{'versions':retired,'at':int(time.time())})
    return retired

def post(url,packet):
    req=urllib.request.Request(url,data=packet,method='POST',headers={'Content-Type':'text/plain','Title':'SC VPS encrypted maintenance v18','Priority':'1','User-Agent':'SCVPS-maintenance-v18/1'})
    try:
        with urllib.request.urlopen(req,timeout=12) as response:
            response.read(1024);return response.status
    except urllib.error.HTTPError as error:return error.code
    except (urllib.error.URLError,TimeoutError):return 0

def deliver(data):
    v15.PUBLIC_KEY=v17.PUBLIC_KEY
    probe=v15.read_json(ROOT/'relay_probe.json')
    if not probe:
        code=post(v15.UPLINK,v15.encrypt({'v':18,'k':'relay_probe','ts':int(time.time()),'seq':data.get('seq')}))
        probe={'code':code,'at':int(time.time())};v15.safe_write(ROOT/'relay_probe.json',probe)
    data['net']=probe.get('code')
    # Optional details yield to the core measured acceptance packet.
    while True:
        try:packet=v15.encrypt(data);break
        except v15.Refused as error:
            if str(error)!='report_payload_too_large':raise
            key=next((k for k in ('fe','up','iv') if k in data),None)
            if key is None:raise
            data.pop(key)
    v15.safe_write(ROOT/'last_receipt.json',data)
    code=post(UPLINK,packet)
    if code not in (200,201):
        if post(v15.UPLINK,packet) in (200,201):return
        raise v15.Refused('relay_status_'+str(code))

def receipt(s,cl):
    agent=v15.read_json(Path('/var/lib/sc-vps-autodeploy/state.json'))
    try:post=measure(delay=3);fresh=True
    except (v15.Refused,OSError,ValueError):post={};fresh=False
    data={'v':18,'k':'maintenance','ts':int(time.time()),'seq':agent.get('last_sequence'),'ag':agent.get('status'),
          'st':s.get('status'),'why':s.get('reason'),'pre':compact(s.get('baseline') or s.get('pre') or {}),'post':compact(post),
          'del':[cl.get('n',0),cl.get('b',0),cl.get('err',0)],'cr':cl.get('reason'),
          'iv':cl.get('inventory',[]),'up':cl.get('upload'),
          'pr':v15.protected(),'fd':round(os.statvfs('/').f_bavail*os.statvfs('/').f_frsize/MiB),
          'fwd':v16.unit_state('livevpn-stripchat-forward.service'),'fe':forward_errors()}
    data['g']=[post.get('sf'),post.get('io'),post.get('oom'),number(CG/'memory.max')]
    if not fresh:data['st']='measurement_unavailable'
    data['p']=[number(CG/'memory.high'),quota()]
    data['rt']=v15.read_json(ROOT/'retired_diagnostics.json').get('versions',[])
    deliver(data)
    print('SC_VPS_V18_RECEIPT_PASS '+str(data['ts']),flush=True)

def run():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    ROOT.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(ROOT/'lock','a+') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
        retired=retire_legacy()
        s=state()
        if s.get('build')!=BUILD and s.get('status') not in ('trial','needs_review','rolled_back_max_pending'):
            s={}
        if s.get('status') in ('trial','needs_review','rolled_back_max_pending'):
            # An interrupted run is restored before another trial can be started.
            restore(s)
        legacy_busy=12 in retired and v15.cmd('systemctl','show','sc-vps-browser-autotune.service','-p','ActiveState','--value') in ('active','activating')
        if legacy_busy:
            s.update(status='refused',reason='legacy_trial_in_progress',build=BUILD,finished=int(time.time()));save(s)
        elif s.get('status')=='rolled_back_max_pending':
            pass
        elif not s.get('accepted') and s.get('status') in ('rolled_back','refused') and time.time()-s.get('finished',s.get('started',0))<3600:
            pass
        else:
            try:repair(s)
            except (v15.Refused,OSError,ValueError) as error:
                if s.get('status')=='trial':
                    s['status']='needs_review';save(s)
                    try:restore(s)
                    except Exception:s['rollback_pending']=True
                else:s['status']='refused'
                s['reason']=str(error)[:90];s['finished']=int(time.time());save(s)
        try:cl=cleanup()
        except (v15.Refused,OSError) as e:
            cl={'n':0,'b':0,'err':1,'reason':str(e)[:60]}
        try:receipt(s,cl)
        except v15.Refused as e:print('SC_VPS_V18_RECEIPT_PENDING '+str(e)[:60],flush=True)
    return 0

def install():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    if SOURCE.is_symlink() or not SOURCE.is_file():raise v15.Refused('signed_source_absent')
    wanted={SERVICE:SERVICE_TEXT.encode(),TIMER:TIMER_TEXT.encode()}
    old={p:v15.read_unit(p) for p in wanted}
    if any(old[p] is not None and old[p]!=body for p,body in wanted.items()):raise v15.Refused('foreign_unit_conflict')
    created=[]
    try:
        for p,body in wanted.items():
            if old[p] is None:
                fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o644)
                with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
                created.append(p)
        if created:v15.cmd('systemctl','daemon-reload')
        v15.cmd('systemctl','enable','--now','--no-reload',TIMER.name)
        if v15.cmd('systemctl','is-active',TIMER.name)!='active':raise v15.Refused('timer_inactive')
        # Idempotent upgrades request an immediate run; an active trial is never restarted.
        v15.cmd('systemctl','start','--no-block',SERVICE.name)
    except Exception:
        if created:
            subprocess.run(['systemctl','disable','--now',TIMER.name],capture_output=True,timeout=15)
            for p in created:
                if v15.read_unit(p)==wanted[p]:p.unlink()
            subprocess.run(['systemctl','daemon-reload'],capture_output=True,timeout=15)
        raise
    print('SC_VPS_V18_GUARDED_CONTROLLER_INSTALLED',flush=True);return 0

def rollback():
    if os.geteuid()!=0:raise v15.Refused('root_required')
    if v15.read_unit(SERVICE)!=SERVICE_TEXT.encode() or v15.read_unit(TIMER)!=TIMER_TEXT.encode():raise v15.Refused('foreign_unit_changed')
    v15.cmd('systemctl','disable','--now',TIMER.name)
    if v15.cmd('systemctl','show',SERVICE.name,'-p','ActiveState','--value') in ('active','activating'):raise v15.Refused('maintenance_running_wait_for_watchdog')
    s=state()
    if s.get('v')==18 and s.get('accepted'):restore(s)
    return 0

def main():
    p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True)
    for k in ('apply','run','status','rollback','watchdog'):g.add_argument('--'+k,action='store_true')
    a=p.parse_args()
    if a.status:print(json.dumps(state(),sort_keys=True));return 0
    return install() if a.apply else run() if a.run else watchdog() if a.watchdog else rollback()

if __name__=='__main__':
    try:raise SystemExit(main())
    except (v15.Refused,OSError,ValueError,BlockingIOError) as e:
        print('SC_VPS_V18_SAFE_ABORT '+type(e).__name__+' '+str(e)[:90]);raise SystemExit(3)
