#!/usr/bin/env python3
"""Idempotent SC-VPS enrollment reconciliation v3.
Safely repairs the exact known 260s -> 900s timeout mismatch, optionally migrates
a verified old agent to the signed read-only-first version. Unknowns fail closed.
Does not deploy releases, lower quotas, stop browser/recorder, or read private logs.
"""
from __future__ import annotations
import hashlib, json, os, pathlib, re, stat, subprocess, sys, tempfile, time, urllib.request

BASE=pathlib.Path('/opt/sc-vps-autodeploy')
AGENT=BASE/'pull_agent.py'
PUB=BASE/'release-signing-public.pem'
STATE=pathlib.Path('/var/lib/sc-vps-autodeploy/state.json')
SERVICE=pathlib.Path('/etc/systemd/system/sc-vps-autodeploy.service')
TIMER=pathlib.Path('/etc/systemd/system/sc-vps-autodeploy.timer')
BOOTSTRAP_URL='https://raw.githubusercontent.com/momopuke/judun-deploy/9cdc4a724ed36fa0f2c5534c6d3327e554be03be/vps-maintenance/autodeploy/review/bootstrap_v5.sh'
BOOTSTRAP_SHA256='1102d5c0f3b8a2145ce0073df3b62b969dbc6b9243a2b7289e3ceeb8b4f3fef2'
AGENT_SHA256='9113ce881789bad728cb8015f4f94d3cb685a1245d4b6bec8f271ebae5ff7c89'
PUB_SHA256='5af7e7c13f1db31b0ce72f87a9e67765ca237a2cb8cdc318a0709b44c8e80418'
LEGACY_AGENT_SHA256='f9578b6af10667556649bcd1b7f7b79ba14d145432b4ccabe80d1a2cab0b6ce5'
AGENT_URL='https://raw.githubusercontent.com/momopuke/judun-deploy/7219554c0c21ed4031e0856b3749e7fca5b8cd23/vps-maintenance/autodeploy/review/pull_agent_v5.py'
BACKUP=pathlib.Path('/var/backups/sc-vps-autodeploy')
ENROLL_LOCK=pathlib.Path('/run/sc-vps-autodeploy-enroll.lock')

UNIT_SERVICE='''# SC-VPS-AUTODEPLOY-MANAGED v1
[Unit]
Description=SC VPS signed release pull and guarded acceptance
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/sc-vps-autodeploy/pull_agent.py
CPUQuota=15%
MemoryMax=180M
Nice=15
IOSchedulingClass=idle
TimeoutStartSec=900s
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
'''
UNIT_TIMER_300='''# SC-VPS-AUTODEPLOY-MANAGED v1
[Unit]
Description=Check signed SC VPS maintenance releases
[Timer]
OnBootSec=300s
OnActiveSec=20s
OnUnitActiveSec=300s
AccuracySec=10s
RandomizedDelaySec=30s
Unit=sc-vps-autodeploy.service
[Install]
WantedBy=timers.target
'''
UNIT_TIMER_180=UNIT_TIMER_300.replace('OnBootSec=300s','OnBootSec=180s')
UNIT_SERVICE_260=UNIT_SERVICE.replace('TimeoutStartSec=900s','TimeoutStartSec=260s')

class Stop(Exception): pass

def digest(data: bytes)->str: return hashlib.sha256(data).hexdigest()
def safe_read(p:pathlib.Path, limit=32768):
    if p.is_symlink(): raise Stop(f'SYMLINK_NOT_ALLOWED:{p}')
    if not p.exists():return None
    if not p.is_file():raise Stop(f'UNEXPECTED_NON_FILE:{p}')
    if p.stat().st_size>limit:raise Stop(f'FILE_TOO_LARGE:{p}')
    return p.read_bytes()

def proc(*args,timeout=25):
    x=subprocess.run(args,text=True,capture_output=True,timeout=timeout,check=False)
    if x.returncode:raise Stop(f'COMMAND_FAILED:{args[0]}:{x.returncode}')
    return x.stdout.strip()

def systemd_state(unit):
    x=subprocess.run(['systemctl','is-active',unit],capture_output=True,text=True,timeout=6)
    return x.stdout.strip()

def valid_state(raw):
    if raw is None:return 'MISSING'
    try:d=json.loads(raw)
    except (ValueError,UnicodeError):return 'UNKNOWN'
    if not isinstance(d,dict):return 'UNKNOWN'
    if (d.get('last_sequence')==1 and d.get('operation')=='status' and d.get('status')=='applied'
        and d.get('code_installed') is False and d.get('release_id')=='SC-VPS-v10-20261104-a1'):
        return 'STATUS_PASS'
    # Agent may omit code_installed in older released status: reject unknown even if apparently success.
    return 'UNRESOLVED'

def decide(has_agent, has_pub, srv, timer, state, timer_active, service_active):
    if service_active:return 'BLOCK_SERVICE_RUNNING'
    if not any([has_agent,has_pub,srv,timer]) and state=='MISSING':return 'INSTALL_FRESH'
    if not all([has_agent,has_pub]):return 'BLOCK_UNTRUSTED_PARTIAL_CODE'
    if state not in ('MISSING','STATUS_PASS'):return 'BLOCK_UNRESOLVED_STATE'
    if timer_active and state!='STATUS_PASS':return 'BLOCK_UNVERIFIED_ACTIVE_TIMER'
    if srv and timer:
        if state=='STATUS_PASS':return 'ALREADY_HEALTHY' if timer_active else 'ENABLE_TIMER'
        return 'FIRST_STATUS'
    if state=='STATUS_PASS':return 'BLOCK_MISSING_UNIT_AFTER_SUCCESS'
    return 'RESTORE_MISSING_MANAGED_UNITS'

def protected_ok():
    browser=proc('systemctl','show','stripchat-browser-desktop.service','-p','ActiveState','--value')
    recorder=proc('docker','inspect','-f','{{.State.Running}}','stripchat-recorder')
    if browser!='active' or recorder!='true':raise Stop('PROTECTED_PRECHECK_NOT_READY')

def normalized_unit(raw: bytes):
    """Strict systemd unit normalization for comment/space-only differences.

    Not a full systemd interpreter. Any unknown directive, changed value,
    duplicate or reordering remains different and cannot be silently accepted.
    """
    text = raw.decode('utf-8', errors='strict')
    if '\x00' in text or '\ufeff' in text:
        raise ValueError('unsafe encoding')
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('#', ';')):
            continue
        if line.startswith('[') and line.endswith(']'):
            out.append(line)
            continue
        m = re.fullmatch(r'([A-Za-z][A-Za-z0-9]*)\s*=\s*(.*)', line)
        if not m or '\\' in line:
            raise ValueError('noncanonical or continuation directive')
        out.append(m.group(1) + '=' + m.group(2))
    return tuple(out)


def unit_diagnostic(path, raw, allowed):
    """No raw values or commands in log: credentials could be in a foreign unit."""
    expected = next(iter(allowed))
    try:
        actual_norm = normalized_unit(raw)
        expected_norm = normalized_unit(expected)
    except (ValueError, UnicodeError):
        actual_norm, expected_norm = (), ()
    actual_keys = [x.split('=', 1)[0] for x in actual_norm if '=' in x]
    expected_keys = [x.split('=', 1)[0] for x in expected_norm if '=' in x]
    safe_values = {}
    safe_names = {'CPUQuota','MemoryMax','TimeoutStartSec','OnBootSec','OnActiveSec','OnUnitActiveSec','AccuracySec','RandomizedDelaySec'}
    expected_values = dict(x.split('=', 1) for x in expected_norm if '=' in x)
    changed_safe_keys = []
    for row in actual_norm:
        if '=' not in row: continue
        key, value = row.split('=', 1)
        if key in safe_names and re.fullmatch(r'[0-9]+(?:%|M|G|ms|s|min|h)?', value):
            safe_values[key] = value
            if expected_values.get(key) != value: changed_safe_keys.append(key)
    return {
        'path':path.name,
        'sha256':digest(raw), 'bytes':len(raw),
        'known_variants':len(allowed),
        'directives_actual':len(actual_keys),
        'directives_expected':len(expected_keys),
        'extra_directives_count':len(set(actual_keys)-set(expected_keys)),
        'missing_directives_count':len(set(expected_keys)-set(actual_keys)),
        'safe_timing_limits':safe_values,
        'changed_safe_setting_keys':sorted(set(changed_safe_keys)),
        'canonical_exec_start': 'ExecStart=/usr/bin/python3 /opt/sc-vps-autodeploy/pull_agent.py' in actual_norm,
        'canonical_user': 'User=root' in actual_norm,
        'canonical_service_type': 'Type=oneshot' in actual_norm,
        'unit_marker_present':b'# SC-VPS-AUTODEPLOY-MANAGED v1' in raw,
        'root_exec_path_present':b'/opt/sc-vps-autodeploy/pull_agent.py' in raw,
    }


def ensure_known_unit(path,raw,allowed):
    if raw is None or raw in allowed:
        return
    try:
        candidate = normalized_unit(raw)
        if any(candidate == normalized_unit(v) for v in allowed):
            print('SC_VPS_UNIT_COMMENT_WHITESPACE_VARIANT_ACCEPTED', path.name, flush=True)
            return
    except (UnicodeError, ValueError):
        pass
    print('SC_VPS_UNKNOWN_UNIT_FINGERPRINT',json.dumps(unit_diagnostic(path,raw,allowed),sort_keys=True),flush=True)
    raise Stop(f'UNKNOWN_UNIT_CONTENTS:{path.name}')

def service_variant(raw:bytes|None)->str:
    """Classify exact effective directives; never normalize unknown keys/commands."""
    if raw is None:
        return 'MISSING'
    try:
        norm=normalized_unit(raw)
        if norm==normalized_unit(UNIT_SERVICE.encode()):
            return 'CURRENT'
        if raw==UNIT_SERVICE_260.encode():
            # Upgrade only the byte-exact published legacy unit, not an assumed equivalent.
            return 'SAFE_260_TIMEOUT_ONLY'
    except (ValueError,UnicodeError):
        pass
    return 'UNKNOWN'


def agent_variant(raw:bytes|None)->str:
    if raw is None:return 'MISSING'
    d=digest(raw)
    if d==AGENT_SHA256:return 'CURRENT'
    if d==LEGACY_AGENT_SHA256:return 'KNOWN_LEGACY'
    return 'UNKNOWN'


def fetch_trusted_agent()->bytes:
    req=urllib.request.Request(AGENT_URL,headers={'User-Agent':'SC-VPS-Reconcile/3'})
    with urllib.request.urlopen(req,timeout=35) as resp:
        data=resp.read(30001)
    if not data or len(data)>30000 or digest(data)!=AGENT_SHA256:
        raise Stop('PINNED_AGENT_SHA256_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='sc-vps-v3-agent-check-') as tmp:
        t=pathlib.Path(tmp)/'pull_agent.py';t.write_bytes(data)
        proc('python3','-m','py_compile',str(t))
        proc('python3',str(t),'--check')
    return data


def make_backup(path:pathlib.Path,raw:bytes)->pathlib.Path:
    """Durable original bytes; never delete backups automatically."""
    if BACKUP.is_symlink() or (BACKUP.exists() and not BACKUP.is_dir()):raise Stop('BACKUP_DIRECTORY_UNSAFE')
    BACKUP.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BACKUP,0o700)
    name=path.name+'.pre-reconcile-v3.'+str(time.time_ns())+'.bak'
    dest=BACKUP/name
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
    fd=os.open(dest,flags,0o600)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
    except BaseException:
        dest.unlink(missing_ok=True);raise
    if dest.read_bytes()!=raw:raise Stop('BACKUP_VERIFICATION_FAILED')
    print('SC_VPS_BACKUP_CREATED',str(dest),flush=True)
    return dest


def atomic_update_existing(path:pathlib.Path, old:bytes, new:bytes):
    if safe_read(path,32768)!=old:raise Stop('CONCURRENT_FILE_CHANGE:'+path.name)
    st=path.stat()
    fd,temp=tempfile.mkstemp(prefix='.sc-vps-reconcile-v3-',dir=str(path.parent))
    temp_path=pathlib.Path(temp)
    try:
        with os.fdopen(fd,'wb') as f:
            os.fchmod(f.fileno(),stat.S_IMODE(st.st_mode))
            os.fchown(f.fileno(),st.st_uid,st.st_gid)
            f.write(new);f.flush();os.fsync(f.fileno())
        if safe_read(path,32768)!=old:raise Stop('CONCURRENT_FILE_CHANGE:'+path.name)
        os.replace(temp_path,path)
        if safe_read(path,32768)!=new:raise Stop('POST_UPDATE_BYTES_MISMATCH:'+path.name)
    finally:
        temp_path.unlink(missing_ok=True)


def reconcile_prechecked(sv:bytes|None,agent:bytes|None,pub:bytes|None,timer:bytes|None,state:bytes|None,timer_active:bool,service_active:bool):
    """Pure decision on observed files; any unrecognized material is a hard stop."""
    v=service_variant(sv)
    if v=='UNKNOWN':return 'BLOCK_UNKNOWN_SERVICE_UNIT'
    if timer is not None:
        try: ensure_known_unit(TIMER,timer,{UNIT_TIMER_180.encode(),UNIT_TIMER_300.encode()})
        except Stop:return 'BLOCK_UNKNOWN_TIMER_UNIT'
    a=agent_variant(agent)
    if a=='UNKNOWN':return 'BLOCK_UNKNOWN_AGENT'
    if pub is not None and digest(pub)!=PUB_SHA256:return 'BLOCK_UNKNOWN_TRUST_ROOT'
    if service_active:return 'BLOCK_SERVICE_RUNNING'
    st_class=valid_state(state)
    mode=decide(agent is not None,pub is not None,sv is not None,timer is not None,st_class,timer_active,service_active)
    if mode.startswith('BLOCK_'):return mode
    if a=='KNOWN_LEGACY' and (st_class!='MISSING' or timer_active):return 'BLOCK_LEGACY_AGENT_HAS_HISTORY'
    if a=='KNOWN_LEGACY' and mode not in ('FIRST_STATUS','RESTORE_MISSING_MANAGED_UNITS'):
        return 'BLOCK_LEGACY_AGENT_NONINITIAL'
    return mode


def install_missing_unit(path,text):
    if path.exists() or path.is_symlink():raise Stop('UNIT_APPEARED_CONCURRENTLY')
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o644)
    try:
        with os.fdopen(fd,'wb') as f:f.write(text.encode());f.flush();os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True);raise

def run_first_status():
    proc('systemctl','daemon-reload')
    # Service is a one-shot and must not already be running; no protected service restarts.
    proc('systemctl','start','sc-vps-autodeploy.service',timeout=910)
    outcome=valid_state(safe_read(STATE,12000))
    if outcome!='STATUS_PASS':raise Stop('FIRST_SIGNED_STATUS_NOT_PASS')
    print('SIGNED_READ_ONLY_STATUS_PASS')

def enable_timer():
    proc('systemctl','enable','--now','sc-vps-autodeploy.timer',timeout=45)
    if systemd_state('sc-vps-autodeploy.timer')!='active':raise Stop('TIMER_NOT_ACTIVE')
    print('TIMER_ACTIVE')

def install_fresh():
    req=urllib.request.Request(BOOTSTRAP_URL,headers={'User-Agent':'SC-VPS-Reconcile/1'})
    with urllib.request.urlopen(req,timeout=30) as response:
        src=response.read(16000)
    if digest(src)!=BOOTSTRAP_SHA256:raise Stop('PINNED_BOOTSTRAP_SHA_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='sc-vps-enroll-repair-') as td:
        sh=pathlib.Path(td)/'bootstrap.sh';sh.write_bytes(src)
        proc('bash','-n',str(sh))
        # This is the strictly pinned, self-checking immutable signed read-only installer.
        proc('bash',str(sh),timeout=1100)
    if valid_state(safe_read(STATE,12000))!='STATUS_PASS' or systemd_state('sc-vps-autodeploy.timer')!='active':
        raise Stop('FRESH_INSTALL_VERIFICATION_FAILED')
    print('SIGNED_READ_ONLY_STATUS_PASS\nTIMER_ACTIVE')

def main():
    if '--self-test' in sys.argv:
        assert service_variant(UNIT_SERVICE.encode())=='CURRENT'
        assert service_variant(UNIT_SERVICE_260.encode())=='SAFE_260_TIMEOUT_ONLY'
        assert service_variant(UNIT_SERVICE_260.replace('ExecStart=/usr/bin/python3','ExecStart=/bin/bash').encode())=='UNKNOWN'
        assert agent_variant(b'unknown')=='UNKNOWN'
        assert normalized_unit(UNIT_SERVICE.encode())==normalized_unit((UNIT_SERVICE+'\n# comment\n').encode())
        assert reconcile_prechecked(UNIT_SERVICE_260.encode(),b'x',b'k',None,None,False,False)=='BLOCK_UNKNOWN_AGENT'
        print('RECONCILE_V3_SELF_TEST_PASS');return 0
    if os.geteuid()!=0:raise Stop('ROOT_REQUIRED')
    import fcntl
    lock_path=ENROLL_LOCK
    if lock_path.is_symlink():raise Stop('ENROLL_LOCK_SYMLINK')
    flags=os.O_CREAT|os.O_RDWR
    if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
    fd=os.open(lock_path,flags,0o600)
    with os.fdopen(fd,'r+') as lk:
        try:fcntl.flock(lk.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('ENROLLMENT_BUSY')
        for parent in (BASE,STATE.parent,SERVICE.parent,TIMER.parent):
            if parent.is_symlink():raise Stop('UNSAFE_PARENT_SYMLINK:'+str(parent))
        a=safe_read(AGENT,30000);p=safe_read(PUB,4096)
        sv=safe_read(SERVICE,8192);tm=safe_read(TIMER,8192)
        st=safe_read(STATE,12000)
        # Distinguish the only permitted in-place edit from arbitrary service changes.
        v=service_variant(sv)
        if v=='UNKNOWN':
            print('SC_VPS_UNKNOWN_UNIT_FINGERPRINT',json.dumps(unit_diagnostic(SERVICE,sv,{UNIT_SERVICE.encode()}),sort_keys=True),flush=True)
        service_active=systemd_state('sc-vps-autodeploy.service') in ('active','activating','reloading')
        timer_active=systemd_state('sc-vps-autodeploy.timer')=='active'
        mode=reconcile_prechecked(sv,a,p,tm,st,timer_active,service_active)
        print('SC_VPS_RECONCILE_V3_CLASSIFICATION',json.dumps({
            'agent':agent_variant(a),'service_unit':v,
            'timer_unit':'present' if tm is not None else 'missing',
            'state':valid_state(st),'timer':'active' if timer_active else 'inactive',
            'action':mode},sort_keys=True),flush=True)
        if mode.startswith('BLOCK_'):raise Stop(mode)
        if mode=='INSTALL_FRESH':
            protected_ok()
            if BASE.exists() and any(BASE.iterdir()):raise Stop('FRESH_UNKNOWN_BASE_CONTENTS')
            if STATE.parent.exists() and any(x.name!='lock' for x in STATE.parent.iterdir()):
                raise Stop('FRESH_UNKNOWN_STATE_CONTENTS')
            fcntl.flock(lk.fileno(),fcntl.LOCK_UN)
            install_fresh()
            print('ENROLLMENT_RECOVERED_AND_VERIFIED');return 0
        protected_ok()
        changed=[]
        pre_status_done=(mode in ('ALREADY_HEALTHY','ENABLE_TIMER'))
        try:
            if agent_variant(a)=='KNOWN_LEGACY':
                upgraded=fetch_trusted_agent()
                make_backup(AGENT,a)
                atomic_update_existing(AGENT,a,upgraded)
                changed.append((AGENT,a,upgraded))
                print('KNOWN_LEGACY_AGENT_UPGRADED_FOR_SIGNED_READONLY_FIRST_RUN',flush=True)
            if v=='SAFE_260_TIMEOUT_ONLY':
                make_backup(SERVICE,sv)
                # Keep all comments and other directives byte-for-byte intact.
                new=sv.replace(b'TimeoutStartSec=260s',b'TimeoutStartSec=900s')
                if new==sv or service_variant(new)!='CURRENT':raise Stop('SAFE_TIMEOUT_REWRITE_DID_NOT_MATCH')
                atomic_update_existing(SERVICE,sv,new)
                changed.append((SERVICE,sv,new))
                proc('systemctl','daemon-reload')
                print('SC_VPS_TIMEOUT_FIXED_260s_TO_900s',flush=True)
            if mode=='RESTORE_MISSING_MANAGED_UNITS':
                if sv is None:install_missing_unit(SERVICE,UNIT_SERVICE)
                if tm is None:install_missing_unit(TIMER,UNIT_TIMER_300)
            if mode not in ('ALREADY_HEALTHY','ENABLE_TIMER'):
                run_first_status()
                pre_status_done=True
            if mode!='ALREADY_HEALTHY':enable_timer()
            if systemd_state('sc-vps-autodeploy.timer')!='active':raise Stop('TIMER_INACTIVE_POSTCHECK')
            if valid_state(safe_read(STATE,12000))!='STATUS_PASS':raise Stop('READ_ONLY_STATUS_INCOMPLETE')
            if service_variant(safe_read(SERVICE,8192))!='CURRENT':raise Stop('TIMEOUT_NOT_UPDATED')
            if digest(safe_read(AGENT,30000))!=AGENT_SHA256:raise Stop('AGENT_NOT_CURRENT')
            print('ENROLLMENT_RECOVERED_AND_VERIFIED',flush=True)
            return 0
        except BaseException:
            # Before signed read-only acceptance, revert only files changed here.
            # On a successful first status, preserve trusted agent and new safer
            # timeout so a retry can finish timer activation without migration.
            if not pre_status_done:
                for path,old,new in reversed(changed):
                    try:
                        atomic_update_existing(path,new,old)
                        if path==SERVICE:proc('systemctl','daemon-reload')
                        print('SC_VPS_LOCAL_ROLLBACK_OK',path.name,flush=True)
                    except Exception as e:
                        print('SC_VPS_LOCAL_ROLLBACK_NEEDS_REVIEW',path.name,type(e).__name__,flush=True)
            raise

if __name__=='__main__':
    try:sys.exit(main())
    except Stop as e:
        print('SC_VPS_RECONCILE_BLOCKED',str(e),file=sys.stderr)
        sys.exit(9)
