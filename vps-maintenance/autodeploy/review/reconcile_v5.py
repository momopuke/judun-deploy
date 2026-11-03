#!/usr/bin/env python3
"""Idempotent SC-VPS enrollment reconciliation v4.
Handles an independently verified legacy signed STATUS or early safety-refused APPLY.
A refused apply can be adopted ONLY when v10's persisted report conclusively
shows diagnosis-only (no commit) and no active rollback watchdog.
Never resets the consumed signed release sequence or re-executes v10.
Repairs only the exact old timeout and known agent. Unknowns fail closed.
Does not deploy releases, lower quotas, stop browser/recorder, or read private logs.
"""
from __future__ import annotations
import datetime as dt, hashlib, json, os, pathlib, re, stat, subprocess, sys, tempfile, time, urllib.request

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

def effective_timeout_seconds(text:str)->float|None:
    """Parse bounded systemd pretty time (e.g. 900s, 15min, 15min 0s)."""
    value=text.replace(' ','')
    if not value or len(value)>64:return None
    pieces=list(re.finditer(r'(\d+)(min|ms|us|h|s)',value))
    if not pieces or ''.join(x.group(0) for x in pieces)!=value:return None
    factor={'h':3600,'min':60,'s':1,'ms':.001,'us':.000001}
    total=sum(int(x.group(1))*factor[x.group(2)] for x in pieces)
    return total if 0<=total<=31536000 else None


def verify_effective_timeout():
    value=proc('systemctl','show','sc-vps-autodeploy.service','-p','TimeoutStartUSec','--value')
    seconds=effective_timeout_seconds(value)
    if seconds!=900:raise Stop('EFFECTIVE_SYSTEMD_TIMEOUT_NOT_900_SECONDS')
    print('SC_VPS_EFFECTIVE_TIMEOUT_VERIFIED_900s',flush=True)


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
    req=urllib.request.Request(AGENT_URL,headers={'User-Agent':'SC-VPS-Reconcile/4'})
    with urllib.request.urlopen(req,timeout=35) as resp:
        data=resp.read(30001)
    if not data or len(data)>30000 or digest(data)!=AGENT_SHA256:
        raise Stop('PINNED_AGENT_SHA256_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='sc-vps-v4-agent-check-') as tmp:
        t=pathlib.Path(tmp)/'pull_agent.py';t.write_bytes(data)
        proc('python3','-m','py_compile',str(t))
        proc('python3',str(t),'--check')
    return data


def make_backup(path:pathlib.Path,raw:bytes)->pathlib.Path:
    """Durable original bytes; never delete backups automatically."""
    if BACKUP.is_symlink() or (BACKUP.exists() and not BACKUP.is_dir()):raise Stop('BACKUP_DIRECTORY_UNSAFE')
    BACKUP.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(BACKUP,0o700)
    name=path.name+'.pre-reconcile-v4.'+str(time.time_ns())+'.bak'
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
    fd,temp=tempfile.mkstemp(prefix='.sc-vps-reconcile-v4-',dir=str(path.parent))
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


# Immutable version-10 payload hashes from the independently signed sequence-1
# release. The old agent can write this payload during its "status" action.
SIGNED_V10_FILES = {
    'SC_VPS_Base_ReadOnly.py': '20dd09582838f06c608ec8f678763668e89fa728217d5abfb3de3d750ac3591c',
    'SC_VPS_Metrics_ReadOnly.py': '8c57e40ba7c6c66215fd3087beb9810eb24a0bd1833c97bafa1a5e79112078d3',
    'SC_VPS_Rescue_v8.py': '754071bc73fe97b87225963eaf4c56db27b25a6a6abac6d9d7172632ea25e99e',
    'SC_VPS_Rescue_v9.py': '95a489fa93f757ad64c34aef254dcfeba2192cd84e2ffba98ca0147b3b3207c9',
    'SC_VPS_Rescue_v10.py': '2c19c689126ea6db76186fad26dd5b7f553000d335ad208aab17191f7c89c040',
    'SHA256SUMS': 'd4e01550b31c4199a1a0f1de6ce019da6a29945f02f34b598541c9107292b890',
    'tests/test_v10.py': '025ee8a504913fb9dfc38ac6615b8999b29a11e9195d861f6538584759c69a89',
}
LEGACY_RELEASE = 'SC-VPS-v10-20261104-a1'
LEGACY_TARGET = pathlib.Path('/root/sc-vps-rescue-v10')

# The refusal receipt does not prove non-mutation by itself. Only v10's durable
# diagnostics and absence of a pending watchdog can provide that evidence.
V10_RUNS = pathlib.Path('/var/lib/sc-vps-rescue-v10/runs')


def legacy_refusal_receipt(raw:bytes|None)->bool:
    """Pin the exact legacy agent's signed, refused sequence-1 APPLY result."""
    if raw is None or len(raw)>12000:return False
    try:d=json.loads(raw)
    except (ValueError,UnicodeError,TypeError):return False
    if not isinstance(d,dict):return False
    if (type(d.get('last_sequence')) is not int or d['last_sequence']!=1 or
        d.get('release_id')!=LEGACY_RELEASE or d.get('operation')!='apply' or
        d.get('status')!='safety_refused' or d.get('code_restored') is not True or
        'code_installed' in d):return False
    res=d.get('result')
    if not isinstance(res,dict) or type(res.get('exit_code')) is not int or res['exit_code']!=3:return False
    # The output tail from the exact signed v10 source is a second fail-closed
    # check, but is NEVER printed (it could contain unrelated sensitive data).
    out=res.get('output_tail')
    if type(out) is not str or 'SC VPS Rescue v10 | diagnosis_only' not in out:return False
    b=d.get('protected_before');a=d.get('protected_after')
    if not isinstance(b,dict) or b!=a:return False
    if b.get('stripchat-browser-desktop.service')!='active' or b.get('stripchat-recorder')!='true':return False
    if b.get('line-openchat-guard.service') not in ('active','unknown'):return False
    if type(d.get('utc')) is not str:return False
    try:
        stamp=dt.datetime.fromisoformat(d['utc'])
        if stamp.tzinfo is None:return False
    except ValueError:return False
    return True


def v10_diagnosis_only_verified(runs: pathlib.Path = V10_RUNS, receipt: bytes|None = None)->bool:
    """Ensure every durable v10 run is noncommitting and latest run is diagnosis-only.

    Do not read or expose private videos/cookies/service logs. The bounded
    report schema originates exclusively from signed v10 source.
    """
    try:
        if runs.is_symlink() or not runs.is_dir():return False
        states=list(runs.glob('*/state.json'))
        if not (1 <= len(states) <= 256):return False
        highest=None
        for p in states:
            if p.parent.is_symlink() or p.is_symlink() or not p.is_file() or p.stat().st_size>100000:
                return False
            obj=json.loads(p.read_text(encoding='utf-8'))
            if not isinstance(obj,dict) or obj.get('version')!='10.0.0':return False
            status=obj.get('status')
            # A prior successful persistent application, in-progress commit or
            # non-completed rollback must NEVER be silently treated as safe.
            if status not in ('diagnosis_only','rollback_completed','already_persistent_verified'):
                return False
            if status=='already_persistent_verified':return False
            if highest is None or p.parent.name>highest[0]:highest=(p.parent.name,obj)
        if highest is None:return False
        last=highest[1]
        # The observed sequence-1 refusal was a diagnosis-only exit 3. Refuse
        # any ambiguous prior commit (including a canceled watchdog failure).
        if last.get('status')!='diagnosis_only' or last.get('changes')!=[]:return False
        if any(k in last for k in ('config_before','timer','rollback_error','post_commit')):
            return False
        # Bind the durable v10 diagnosis to the signed release receipt.
        # Otherwise a *different* later manual run could make a rejected old
        # APPLY look safe. 205s child timeout; allow up to 10m wall skew.
        if receipt is not None:
            if not legacy_refusal_receipt(receipt):return False
            rcpt=json.loads(receipt)
            if type(last.get('utc')) is not str:return False
            start=dt.datetime.fromisoformat(last['utc'])
            done=dt.datetime.fromisoformat(rcpt['utc'])
            if start.tzinfo is None or done.tzinfo is None:return False
            delta=(done-start).total_seconds()
            if not 0<=delta<=600:return False
        return True
    except (OSError,UnicodeError,ValueError,TypeError):return False


def rollback_watchdogs_clear()->bool:
    """No pending v10 rollback timer or executing watchdog process.

    This is intentionally conservative. If systemd cannot be queried, refuse.
    """
    try:
        q=subprocess.run(['systemctl','list-units','--all','--type=timer','--no-legend','--no-pager'],
                         capture_output=True,text=True,timeout=9,check=False)
        if q.returncode!=0:return False
        names=set(re.findall(r'sc-vps-v10-rollback-[0-9]+\.timer',q.stdout))
        q2=subprocess.run(['systemctl','list-unit-files','--type=timer','--no-legend','--no-pager'],
                          capture_output=True,text=True,timeout=9,check=False)
        if q2.returncode!=0:return False
        names.update(re.findall(r'sc-vps-v10-rollback-[0-9]+\.timer',q2.stdout))
        for n in names:
            state=systemd_state(n)
            if state not in ('inactive','failed','unknown'):return False
        for p in pathlib.Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                cmd=(p/'cmdline').read_bytes()[:4096]
                if b'SC_VPS_Rescue_v10.py' in cmd and b'--watchdog' in cmd:return False
            except (OSError,PermissionError,ProcessLookupError):continue
        return True
    except (OSError,subprocess.TimeoutExpired,UnicodeError):return False


def verified_refused_legacy(raw:bytes|None)->bool:
    return (legacy_refusal_receipt(raw) and v10_diagnosis_only_verified(receipt=raw)
            and rollback_watchdogs_clear())

def redacted_state(raw):
    """Diagnostic metadata only, never expose raw output, private logs, or paths."""
    result={'present': raw is not None,'legacy_receipt':False}
    if raw is None:return result
    try:
        obj=json.loads(raw)
        if not isinstance(obj,dict):raise ValueError()
        meta=obj.get('result') if isinstance(obj.get('result'),dict) else {}
        result.update({
            'sequence':obj.get('last_sequence') if type(obj.get('last_sequence')) is int else 'invalid',
            'operation':obj.get('operation') if obj.get('operation') in ('status','apply','rollback') else 'unknown',
            'status':obj.get('status') if obj.get('status') in ('applied','needs_review','safety_refused','in_progress','protected_service_changed') else 'unknown',
            'exit_code':meta.get('exit_code') if type(meta.get('exit_code')) is int else 'unknown',
            'code_restored':obj.get('code_restored') if type(obj.get('code_restored')) is bool else 'unknown',
            'protected_match':obj.get('protected_before')==obj.get('protected_after') and isinstance(obj.get('protected_before'),dict),
        })
        result['legacy_receipt']=trusted_legacy_receipt(raw)
    except (ValueError,TypeError):result['parse_valid']=False
    return result

def trusted_legacy_receipt(raw):
    """Only exact old signed sequence-1 STATUS success; never infer an apply is safe.

    Old signed agent's status operation writes the signed code files and emits
    `code_restored=False` instead of `code_installed=False`. It must *not* be
    rerun or silently rewritten as a modern read-only receipt.
    """
    if not raw or len(raw)>12000:return False
    try:d=json.loads(raw)
    except (UnicodeError,ValueError,TypeError):return False
    if not isinstance(d,dict):return False
    if not (type(d.get('last_sequence')) is int and d['last_sequence']==1
            and d.get('release_id')==LEGACY_RELEASE
            and d.get('operation')=='status' and d.get('status')=='applied'
            and d.get('code_restored') is False and 'code_installed' not in d):return False
    x=d.get('result')
    if not isinstance(x,dict) or type(x.get('exit_code')) is not int or x['exit_code']!=0:return False
    before=d.get('protected_before');after=d.get('protected_after')
    if not isinstance(before,dict) or before!=after:return False
    if before.get('stripchat-browser-desktop.service')!='active':return False
    if before.get('stripchat-recorder')!='true':return False
    if before.get('line-openchat-guard.service') not in ('active','unknown'):return False
    # Legacy agent wrote the signed payload before creating this receipt.
    # We additionally verify all installed files on disk below.
    return True

def signed_v10_installed(target=LEGACY_TARGET):
    """No recursion, symlinks, or foreign target paths. Validate only pinned files."""
    try:
        if target.is_symlink() or not target.is_dir():return False
        for name,expected in SIGNED_V10_FILES.items():
            path=target/name
            if path.parent.is_symlink() or path.is_symlink() or not path.is_file():return False
            if path.stat().st_size>85000:return False
            if digest(path.read_bytes())!=expected:return False
        return True
    except OSError:return False

def reconcile_verified_legacy(sv,a,p,tm,st,timer_active,service_active):
    """Single guarded migration of a completed old signed STATUS receipt.

    Does NOT run any v10 operation or rewrite the release receipt. Only this
    dedicated update service and its timer are touched. Never touch recorder.
    """
    import fcntl
    if service_active:raise Stop('LEGACY_SERVICE_CURRENTLY_RUNNING')
    if service_variant(sv) not in ('SAFE_260_TIMEOUT_ONLY','CURRENT'):
        raise Stop('LEGACY_SERVICE_NOT_PINNED')
    if agent_variant(a) not in ('KNOWN_LEGACY','CURRENT'):
        raise Stop('LEGACY_AGENT_NOT_PINNED')
    if p is None or digest(p)!=PUB_SHA256:raise Stop('LEGACY_TRUST_ROOT_NOT_PINNED')
    if tm is None:raise Stop('LEGACY_TIMER_UNIT_MISSING')
    ensure_known_unit(TIMER,tm,{UNIT_TIMER_180.encode(),UNIT_TIMER_300.encode()})
    status_receipt=trusted_legacy_receipt(st)
    refused_receipt=verified_refused_legacy(st) if not status_receipt else False
    if not (status_receipt or refused_receipt):raise Stop('LEGACY_RECEIPT_UNVERIFIED')
    # The legacy agent restored its v10 Python files after exit 3. Thus,
    # *absence* of the signed v10 installed files is expected for refusal.
    # Status receipts wrote code permanently and MUST verify those seven files.
    if status_receipt and not signed_v10_installed():raise Stop('LEGACY_INSTALLED_V10_HASHES_MISMATCH')
    # The existing pull agent locks this same fd. No concurrent update is allowed.
    lock_file=STATE.parent/'lock'
    if lock_file.is_symlink():raise Stop('LEGACY_AGENT_LOCK_SYMLINK')
    lock_flags=os.O_CREAT|os.O_RDWR
    if hasattr(os,'O_NOFOLLOW'):lock_flags|=os.O_NOFOLLOW
    lock_fd=os.open(lock_file,lock_flags,0o600)
    with os.fdopen(lock_fd,'r+') as guard:
        try:fcntl.flock(guard.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Stop('LEGACY_AGENT_BUSY')
        if safe_read(STATE,12000)!=st:raise Stop('LEGACY_RECEIPT_CHANGED')
        if safe_read(AGENT,30000)!=a or safe_read(SERVICE,8192)!=sv or safe_read(PUB,4096)!=p or safe_read(TIMER,8192)!=tm:
            raise Stop('LEGACY_FILES_CHANGED')
        if systemd_state('sc-vps-autodeploy.service') in ('active','activating','reloading'):
            raise Stop('LEGACY_SERVICE_STARTED_CONCURRENTLY')
        protected_ok()
        if agent_variant(a)=='CURRENT' and service_variant(sv)=='CURRENT' and timer_active:
            verify_effective_timeout()
            if safe_read(STATE,12000)!=st or (status_receipt and not signed_v10_installed()) or (refused_receipt and not verified_refused_legacy(st)):
                raise Stop('LEGACY_RECEIPT_CHANGED_ON_RECHECK')
            print('ENROLLMENT_ALREADY_COMPLETE_LEGACY_RECEIPT_VERIFIED',flush=True)
            return 0
        changed=[];was_timer_active=timer_active
        try:
            if was_timer_active:
                proc('systemctl','stop','sc-vps-autodeploy.timer')
                if systemd_state('sc-vps-autodeploy.timer')=='active':raise Stop('LEGACY_TIMER_STILL_ACTIVE')
            if agent_variant(a)=='KNOWN_LEGACY':
                upgraded=fetch_trusted_agent()
                make_backup(AGENT,a)
                atomic_update_existing(AGENT,a,upgraded)
                changed.append((AGENT,a,upgraded))
                print('SC_VPS_KNOWN_LEGACY_AGENT_UPGRADED',flush=True)
            if service_variant(sv)=='SAFE_260_TIMEOUT_ONLY':
                make_backup(SERVICE,sv)
                new=sv.replace(b'TimeoutStartSec=260s',b'TimeoutStartSec=900s')
                if service_variant(new)!='CURRENT':raise Stop('LEGACY_REWRITE_UNEXPECTED')
                atomic_update_existing(SERVICE,sv,new)
                changed.append((SERVICE,sv,new))
                print('SC_VPS_TIMEOUT_FIXED_260s_TO_900s',flush=True)
            proc('systemctl','daemon-reload')
            verify_effective_timeout()
            if status_receipt and not signed_v10_installed():raise Stop('LEGACY_V10_CHANGED_DURING_MIGRATION')
            if refused_receipt and not verified_refused_legacy(st):raise Stop('LEGACY_REFUSAL_SAFETY_CHANGED_DURING_MIGRATION')
            if safe_read(STATE,12000)!=st:raise Stop('LEGACY_RECEIPT_MODIFIED_DURING_MIGRATION')
            if digest(safe_read(AGENT,30000))!=AGENT_SHA256:raise Stop('LEGACY_AGENT_MIGRATION_SHA_MISMATCH')
            protected_ok()
            proc('systemctl','enable','--now','sc-vps-autodeploy.timer',timeout=45)
            if systemd_state('sc-vps-autodeploy.timer')!='active':raise Stop('LEGACY_TIMER_NOT_ACTIVE')
            if refused_receipt:
                print('SC_VPS_MIGRATED_VERIFIED_DIAGNOSIS_ONLY_REFUSAL',flush=True)
                print('NEXT_SIGNED_RELEASE_MUST_BE_STATUS_NOT_APPLY',flush=True)
            else:
                print('ENROLLMENT_RECOVERED_WITH_VERIFIED_LEGACY_STATUS',flush=True)
                print('NOTE_LEGACY_STATUS_INSTALLED_V10_CODE_NO_NEW_APPLY_EXECUTED',flush=True)
            return 0
        except BaseException:
            # Atomic rollback only when bytes still match what we wrote.
            try:proc('systemctl','stop','sc-vps-autodeploy.timer')
            except Exception:pass
            for path,old,new in reversed(changed):
                try:
                    atomic_update_existing(path,new,old)
                    print('SC_VPS_LOCAL_ROLLBACK_OK',path.name,flush=True)
                except Exception as exc:
                    print('SC_VPS_LOCAL_ROLLBACK_NEEDS_REVIEW',path.name,type(exc).__name__,flush=True)
            try:proc('systemctl','daemon-reload')
            except Exception:pass
            if was_timer_active:
                try:proc('systemctl','start','sc-vps-autodeploy.timer')
                except Exception:print('SC_VPS_TIMER_RESTORE_NEEDS_REVIEW',flush=True)
            raise

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
        assert trusted_legacy_receipt(None) is False
        assert legacy_refusal_receipt(None) is False
        assert signed_v10_installed(pathlib.Path('/does-not-exist')) is False
        print('RECONCILE_V5_SELF_TEST_PASS');return 0
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
        print('SC_VPS_RECONCILE_V5_CLASSIFICATION',json.dumps({
            'agent':agent_variant(a),'service_unit':v,
            'timer_unit':'present' if tm is not None else 'missing',
            'state':valid_state(st),'timer':'active' if timer_active else 'inactive',
            'action':mode},sort_keys=True),flush=True)
        if mode.startswith('BLOCK_'):
            print('SC_VPS_STATE_SUMMARY',json.dumps(redacted_state(st),sort_keys=True),flush=True)
            if mode=='BLOCK_UNRESOLVED_STATE':
                if trusted_legacy_receipt(st) or verified_refused_legacy(st):
                    return reconcile_verified_legacy(sv,a,p,tm,st,timer_active,service_active)
                print('SC_VPS_REFUSED_APPLY_REVIEW',json.dumps({
                    'receipt_fields_valid':legacy_refusal_receipt(st),
                    'diagnosis_only_report_valid':v10_diagnosis_only_verified(receipt=st),
                    'rollback_watchdogs_clear':rollback_watchdogs_clear()},sort_keys=True),flush=True)
            raise Stop(mode)
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
                verify_effective_timeout()
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
            verify_effective_timeout()
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
        print('SC_VPS_RECONCILE_V5_BLOCKED',str(e),file=sys.stderr)
        sys.exit(9)
