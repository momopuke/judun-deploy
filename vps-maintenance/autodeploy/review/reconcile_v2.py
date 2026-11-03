#!/usr/bin/env python3
"""Idempotent SC-VPS enrollment reconciliation v2.
Accepts comment/space-only unit variants; unknown semantics fail closed with redacted fingerprints.
Does not deploy releases, lower quotas, stop browser/recorder, or read private logs.
"""
from __future__ import annotations
import hashlib, json, os, pathlib, re, subprocess, sys, tempfile, urllib.request

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
        assert normalized_unit(UNIT_SERVICE.encode()) == normalized_unit((UNIT_SERVICE+'\n# comment\n').encode())
        assert decide(False,False,False,False,'MISSING',False,False)=='INSTALL_FRESH'
        assert decide(True,True,True,True,'STATUS_PASS',True,False)=='ALREADY_HEALTHY'
        assert decide(True,True,True,True,'STATUS_PASS',False,False)=='ENABLE_TIMER'
        assert decide(True,True,True,True,'MISSING',False,False)=='FIRST_STATUS'
        assert decide(True,True,True,False,'MISSING',False,False)=='RESTORE_MISSING_MANAGED_UNITS'
        assert decide(True,True,True,True,'UNRESOLVED',False,False)=='BLOCK_UNRESOLVED_STATE'
        assert decide(True,True,True,True,'MISSING',True,False)=='BLOCK_UNVERIFIED_ACTIVE_TIMER'
        assert decide(True,True,True,True,'STATUS_PASS',True,True)=='BLOCK_SERVICE_RUNNING'
        assert decide(False,True,True,True,'MISSING',False,False)=='BLOCK_UNTRUSTED_PARTIAL_CODE'
        print('RECONCILE_SELF_TEST_PASS');return 0
    if os.geteuid()!=0:raise Stop('ROOT_REQUIRED')
    import fcntl
    lock_path=pathlib.Path('/run/sc-vps-autodeploy-enroll.lock')
    if lock_path.is_symlink(): raise Stop('ENROLL_LOCK_SYMLINK')
    flags=os.O_CREAT|os.O_RDWR
    if hasattr(os,'O_NOFOLLOW'): flags|=os.O_NOFOLLOW
    fd=os.open(lock_path,flags,0o600)
    with os.fdopen(fd,'r+') as lk:
        try:fcntl.flock(lk.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('ENROLLMENT_BUSY')
        for parent in (BASE,STATE.parent,SERVICE.parent,TIMER.parent):
            if parent.is_symlink(): raise Stop('UNSAFE_PARENT_SYMLINK:'+str(parent))
        a=safe_read(AGENT,30000);p=safe_read(PUB,4096)
        sv=safe_read(SERVICE,8192);tm=safe_read(TIMER,8192)
        st=safe_read(STATE,12000)
        ensure_known_unit(SERVICE,sv,{UNIT_SERVICE.encode()})
        ensure_known_unit(TIMER,tm,{UNIT_TIMER_180.encode(),UNIT_TIMER_300.encode()})
        if a is not None and digest(a)!=AGENT_SHA256:raise Stop('UNKNOWN_OR_LEGACY_AGENT_DO_NOT_OVERWRITE')
        if p is not None and digest(p)!=PUB_SHA256:raise Stop('UNKNOWN_PUBLIC_KEY_DO_NOT_OVERWRITE')
        service_running=systemd_state('sc-vps-autodeploy.service')=='activating'
        timer_running=systemd_state('sc-vps-autodeploy.timer')=='active'
        st_class=valid_state(st)
        mode=decide(a is not None,p is not None,sv is not None,tm is not None,st_class,timer_running,service_running)
        print('SC_VPS_RECONCILE_CLASSIFICATION',json.dumps({'agent':'trusted' if a else 'missing','public_key':'trusted' if p else 'missing','service_unit':'known' if sv else 'missing','timer_unit':'known' if tm else 'missing','state':st_class,'timer':('active' if timer_running else 'inactive'),'action':mode},ensure_ascii=False),flush=True)
        if mode.startswith('BLOCK_'):raise Stop(mode)
        if mode=='ALREADY_HEALTHY':print('ENROLLMENT_ALREADY_COMPLETE_NO_CHANGE');return 0
        protected_ok()
        if mode=='INSTALL_FRESH':
            if BASE.exists() and any(BASE.iterdir()):raise Stop('FRESH_UNKNOWN_BASE_CONTENTS')
            if STATE.parent.exists() and any(x.name not in ('lock',) for x in STATE.parent.iterdir()):
                raise Stop('FRESH_UNKNOWN_STATE_CONTENTS')
            # The immutable official bootstrap acquires this same installation
            # lock; release our inspection lock before handing it over.
            fcntl.flock(lk.fileno(),fcntl.LOCK_UN)
            install_fresh()
        else:
            if mode=='RESTORE_MISSING_MANAGED_UNITS':
                if sv is None:install_missing_unit(SERVICE,UNIT_SERVICE)
                if tm is None:install_missing_unit(TIMER,UNIT_TIMER_300)
            if mode!='ENABLE_TIMER':run_first_status()
            enable_timer()
        print('ENROLLMENT_RECOVERED_AND_VERIFIED')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Stop as e:
        print('SC_VPS_RECONCILE_BLOCKED',str(e),file=sys.stderr)
        sys.exit(9)