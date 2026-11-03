#!/usr/bin/env python3
"""SC VPS signed release pull agent. No inbound ports or server-side GitHub credential.

Runs ONLY release bundles signed by the owner's independent Ed25519 key,
anchored to a 40-hex immutable GitHub commit and exact SHA256 for every file.
Never manages JUDUN/LINE/Docker or browser start/stop. Scoped to SC rescue.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlopen, Request

REPO = 'momopuke/judun-deploy'
BRANCH = 'vps-maintenance'
CHANNEL = 'https://raw.githubusercontent.com/' + REPO + '/' + BRANCH + '/vps-maintenance/autodeploy/'
RAW = 'https://raw.githubusercontent.com/' + REPO + '/'
HOME = Path('/opt/sc-vps-autodeploy')
STATE = Path('/var/lib/sc-vps-autodeploy')
BACKUPS = Path('/var/backups/sc-vps-autodeploy')
PUBLIC_KEY = HOME / 'release-signing-public.pem'
MAX_FILES = 14
MAX_BYTES = 80000
MAX_MANIFEST = 8192

class Rejected(Exception): pass

def sha(data: bytes) -> str: return hashlib.sha256(data).hexdigest()

def now(): return dt.datetime.now(dt.timezone.utc).isoformat()

def check_name(x: str, version: int) -> bool:
    names = {'SC_VPS_Base_ReadOnly.py','SC_VPS_Metrics_ReadOnly.py','SHA256SUMS'}
    if x in names: return True
    if re.fullmatch(r'SC_VPS_Rescue_v([0-9]{1,2})\.py',x):
        n = int(re.fullmatch(r'SC_VPS_Rescue_v([0-9]{1,2})\.py',x).group(1))
        return 8 <= n <= version
    return re.fullmatch(r'tests/test_v([0-9]{1,2})\.py',x) is not None and x==f'tests/test_v{version}.py'

def strict_json(raw: bytes) -> dict:
    if not 10 < len(raw) <= MAX_MANIFEST: raise Rejected('MANIFEST_SIZE')
    def unique(pairs):
        d={}
        for key,value in pairs:
            if key in d: raise Rejected('DUPLICATE_JSON_FIELD')
            d[key]=value
        return d
    try: data = json.loads(raw,object_pairs_hook=unique)
    except (UnicodeError,ValueError) as e: raise Rejected('MANIFEST_JSON') from e
    if not isinstance(data,dict) or set(data)!= {'schema','sequence','release_id','git_commit','version','operation','files'}:raise Rejected('MANIFEST_FIELDS')
    if data['schema']!='sc-vps-signed-release/v1':raise Rejected('SCHEMA')
    if type(data['sequence'])!=int or not 1<=data['sequence']<=1000000:raise Rejected('SEQUENCE')
    if type(data['version'])!=int or not 10<=data['version']<=30:raise Rejected('VERSION')
    version=data['version']
    if type(data['release_id'])!=str or not re.fullmatch(r'SC-VPS-v'+str(version)+r'-[A-Za-z0-9_-]{6,36}',data['release_id']):raise Rejected('RELEASE_ID')
    if data['operation'] not in ('apply','status','rollback'):raise Rejected('OPERATION')
    if type(data['git_commit'])!=str or not re.fullmatch(r'[0-9a-f]{40}',data['git_commit']):raise Rejected('COMMIT_PIN')
    files=data['files']
    if type(files)!=dict or not 5 <= len(files) <= MAX_FILES:raise Rejected('FILES_COUNT')
    required={'SC_VPS_Base_ReadOnly.py','SC_VPS_Metrics_ReadOnly.py','SC_VPS_Rescue_v8.py','SC_VPS_Rescue_v9.py',f'SC_VPS_Rescue_v{version}.py',f'tests/test_v{version}.py'}
    if not required.issubset(files):raise Rejected('REQUIRED_FILES')
    if any(type(k)!=str or not check_name(k,version) or type(v)!=str or not re.fullmatch(r'[0-9a-f]{64}',v) for k,v in files.items()):raise Rejected('FILE_SCHEMA')
    return data

def get(url: str, limit: int) -> bytes:
    req=Request(url,headers={'User-Agent':'SCVPS-SignedUpdater/1','Cache-Control':'no-cache'})
    try:
        with urlopen(req,timeout=22) as resp:
            if resp.status!=200: raise Rejected('HTTPS_STATUS')
            data=resp.read(limit+1)
    except (OSError,ValueError) as e:raise Rejected('HTTPS_FETCH') from e
    if len(data)>limit:raise Rejected('HTTPS_SIZE')
    return data

def verify(manifest: bytes, sig64: bytes, public_key=PUBLIC_KEY) -> dict:
    doc=strict_json(manifest)
    if not public_key.is_file() or public_key.is_symlink() or public_key.stat().st_size>4096:raise Rejected('PINNED_PUBLIC_KEY_MISSING')
    try: sig=base64.b64decode(b''.join(sig64.split()),validate=True)
    except (ValueError,base64.binascii.Error) as e:raise Rejected('SIGNATURE_BASE64') from e
    if len(sig)!=64:raise Rejected('SIGNATURE_LENGTH')
    with tempfile.TemporaryDirectory(prefix='scvps-sign-') as tmp:
        p=Path(tmp)
        (p/'manifest').write_bytes(manifest)
        (p/'signature').write_bytes(sig)
        try:
            v=subprocess.run(['/usr/bin/openssl','pkeyutl','-verify','-pubin','-inkey',str(public_key),'-rawin',
                '-in',str(p/'manifest'),'-sigfile',str(p/'signature')],capture_output=True,timeout=10,check=False)
        except (OSError,subprocess.TimeoutExpired) as e:raise Rejected('SIGNATURE_TOOL') from e
        if v.returncode!=0:raise Rejected('SIGNATURE_INVALID')
    return doc

def save_json(path: Path,value: dict):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise Rejected('STATE_SYMLINK')
    fd,tmp=tempfile.mkstemp(prefix='.scvps-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            os.fchmod(f.fileno(),0o600)
            json.dump(value,f,sort_keys=True,ensure_ascii=False)
            f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def read_state() -> dict:
    p=STATE/'state.json'
    if not p.exists():return {}
    if p.is_symlink() or p.stat().st_size>12000:raise Rejected('STATE_INVALID')
    try: obj=json.loads(p.read_text(encoding='utf8'))
    except (OSError,ValueError) as e:raise Rejected('STATE_JSON') from e
    if not isinstance(obj,dict):raise Rejected('STATE_TYPE')
    return obj

def target_dir(version: int) -> Path:return Path('/root/sc-vps-rescue-v'+str(version))

def stage_files(doc: dict,tmpdir: Path) -> Path:
    payload=tmpdir/'payload'
    payload.mkdir(mode=0o700)
    for name,expected in sorted(doc['files'].items()):
        url=RAW+doc['git_commit']+'/vps-maintenance/autodeploy/releases/'+doc['release_id']+'/'+name
        data=get(url,MAX_BYTES)
        if not data or sha(data)!=expected:raise Rejected('SOURCE_SHA_MISMATCH:'+name)
        dst=payload/name
        dst.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        dst.write_bytes(data);dst.chmod(0o600)
    if (payload/'SHA256SUMS').exists():
        src=(payload/'SHA256SUMS').read_text()
        for line in src.splitlines():
            x=re.fullmatch(r'([0-9a-f]{64})  (SC_VPS_[A-Za-z0-9_]+\.py)',line)
            if not x or doc['files'].get(x.group(2))!=x.group(1):raise Rejected('SOURCE_SHA256SUMS_MISMATCH')
    return payload

def preflight_tests(src:Path,version:int):
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(src)}
    for i in range(1,6):
        try:
            test=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p',f'test_v{version}.py','-q'],cwd=src,env=env,timeout=35,capture_output=True,text=True)
        except subprocess.TimeoutExpired as e:raise Rejected('TEST_TIMEOUT') from e
        if test.returncode!=0:raise Rejected('PREDEPLOY_TEST_FAILED_ROUND_'+str(i))

def install_code(doc:dict,src:Path,work:Path):
    version=doc['version']; target=target_dir(version)
    if target.is_symlink() or (target.exists() and not target.is_dir()):raise Rejected('TARGET_UNSAFE')
    if target.exists():
        for extra in target.glob('*.py'):
            if extra.name not in doc['files'] or extra.is_symlink():raise Rejected('TARGET_FOREIGN_SOURCE')
    was_existing=target.exists()
    if not was_existing:target.mkdir(mode=0o700,parents=True)
    BACKUPS.mkdir(mode=0o700,parents=True,exist_ok=True)
    if BACKUPS.is_symlink():raise Rejected('BACKUP_DIR_SYMLINK')
    backup=BACKUPS/(doc['release_id']+'-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    backup.mkdir(mode=0o700)
    copied=[]
    try:
        for name in sorted(doc['files']):
            dst=target/name
            dst.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            if dst.exists() or dst.is_symlink():
                if dst.is_symlink() or not dst.is_file():raise Rejected('TARGET_SYMLINK_OR_NOT_FILE')
                p=backup/name;p.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
                shutil.copy2(dst,p)
            else: copied.append(name)
            tmp=dst.with_name('.scvps-stage-'+dst.name)
            if tmp.exists() or tmp.is_symlink():raise Rejected('TARGET_STAGE_CONFLICT')
            shutil.copyfile(src/name,tmp);tmp.chmod(0o600)
            os.replace(tmp,dst)
            if sha(dst.read_bytes())!=doc['files'][name]:raise Rejected('TARGET_COPY_CORRUPTION')
    except Exception:
        restore_code(target,backup,copied,was_existing)
        raise
    return target,backup,copied,was_existing

def restore_code(target:Path,backup:Path,copied:list[str],was_existing:bool):
    for name in copied:
        p=target/name
        if p.exists() and not p.is_symlink():p.unlink()
    for f in backup.rglob('*'):
        if f.is_file():
            name=f.relative_to(backup);dest=target/name
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(f,dest)
    # Keep directories and original unrelated material intact; never recursive-delete.

def read_protected() -> dict:
    result={}
    for unit in ('stripchat-browser-desktop.service','line-openchat-guard.service'):
        try:
            q=subprocess.run(['systemctl','show',unit,'-p','ActiveState','--value'],capture_output=True,text=True,timeout=5)
            result[unit]=q.stdout.strip() if q.returncode==0 else 'unknown'
        except (OSError,subprocess.TimeoutExpired):result[unit]='unknown'
    try:
        q=subprocess.run(['docker','inspect','-f','{{.State.Running}}','stripchat-recorder'],capture_output=True,text=True,timeout=5)
        result['stripchat-recorder']=q.stdout.strip() if q.returncode==0 else 'unknown'
    except (OSError,subprocess.TimeoutExpired):result['stripchat-recorder']='unknown'
    return result

def operation(doc:dict,folder:Path) -> dict:
    args={'apply':'--apply','status':'--status','rollback':'--rollback'}
    command=[sys.executable,str(folder/f'SC_VPS_Rescue_v{doc["version"]}.py'),args[doc['operation']]]
    try:
        run=subprocess.run(command,cwd=folder,timeout=205,capture_output=True,text=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'})
    except subprocess.TimeoutExpired as e:raise Rejected('APPLY_TIMEOUT_WATCHDOG_MAY_BE_ACTIVE') from e
    return {'exit_code':run.returncode,'output_tail':run.stdout[-2400:],'error_tail':run.stderr[-600:]}

def once() -> int:
    if os.geteuid()!=0:print('SC_VPS_BLOCKED_NOT_ROOT');return 6
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(STATE/'lock','a+') as lk:
        try:fcntl.flock(lk,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:print('SC_VPS_SKIP_ANOTHER_AGENT_RUNNING');return 0
        try:
            doc=verify(get(CHANNEL+'channel.json',MAX_MANIFEST),get(CHANNEL+'channel.sig.b64',1024))
            last=read_state();seq=last.get('last_sequence',0)
            if type(seq)!=int or seq<0:raise Rejected('STATE_SEQUENCE')
            if last.get('status') in ('in_progress', 'needs_review', 'protected_service_changed'):
                raise Rejected('UNRESOLVED_PREVIOUS_RELEASE_REQUIRES_RECONCILIATION')
            if doc['sequence']<=seq:
                print('SC_VPS_ALREADY_HANDLED',seq);return 0
            if doc['sequence']>seq+100:raise Rejected('SEQUENCE_GAP_TOO_LARGE')
            baseline=read_protected()
            if baseline['stripchat-browser-desktop.service']!='active' or baseline['stripchat-recorder']!='true':raise Rejected('PRECHECK_PROTECTED_SERVICE_INACTIVE')
            with tempfile.TemporaryDirectory(prefix='sc-vps-release-') as td:
                work=Path(td)
                source=stage_files(doc,work)
                preflight_tests(source,doc['version'])
                target,backup,copied,existing=install_code(doc,source,work)
                operation_started=False
                try:
                    # Durable write-ahead fence: a killed parent must not
                    # accidentally rerun a partially started v10 operation.
                    save_json(STATE/'state.json', {
                        'last_sequence':doc['sequence'], 'release_id':doc['release_id'],
                        'operation':doc['operation'],'status':'in_progress',
                        'utc':now(), 'code_backup':str(backup)})
                    operation_started=True
                    result=operation(doc,target)
                    after=read_protected()
                    code_restored=False
                    rollback_result=None
                    if baseline!=after:
                        # v10 may have already persisted a memory setting.
                        # Roll back through v10 BEFORE touching its watchdog source.
                        if result['exit_code']==0 and doc['operation']=='apply':
                            rollback_result=operation({**doc,'operation':'rollback'},target)
                            if rollback_result['exit_code']==0:
                                restore_code(target,backup,copied,existing)
                                code_restored=True
                        status='protected_service_changed'
                    elif result['exit_code']==0:
                        status='applied'
                    elif result['exit_code']==3:
                        status='safety_refused'
                        # Explicit diagnosis-only exit has not armed persistence.
                        if ' | diagnosis_only' in result['output_tail']:
                            restore_code(target,backup,copied,existing)
                            code_restored=True
                    else:
                        status='needs_review'
                        # A v10 rollback timer could still be pending; retain
                        # the signed source for its independent safety watchdog.
                    state={'last_sequence':doc['sequence'],'release_id':doc['release_id'],'operation':doc['operation'],
                        'status':status,'utc':now(),'result':result,'protected_before':baseline,'protected_after':after,
                        'code_restored':code_restored,'code_backup':str(backup),'rollback_result':rollback_result}
                    save_json(STATE/'state.json',state)
                    print('SC_VPS_SIGNED_RELEASE_RESULT',json.dumps({'sequence':doc['sequence'],'status':status,'exit_code':result['exit_code']}))
                    return 0 if status in ('applied','safety_refused') else 5
                except Exception:
                    # After starting v10, never remove its potential watchdog
                    # source on an ambiguous failure. Leave signed files and
                    # the durable backup for safe reconciliation.
                    if not operation_started:
                        restore_code(target,backup,copied,existing)
                    raise
        except Exception as e:
            reason=str(e) if isinstance(e,Rejected) else type(e).__name__
            print('SC_VPS_SIGNED_RELEASE_BLOCKED',reason,flush=True)
            return 5

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--check',action='store_true')
    args=a.parse_args()
    if args.check:
        assert check_name('SC_VPS_Rescue_v10.py',10)
        assert not check_name('../../passwd',10)
        print('SC_VPS_AGENT_STATIC_PASS')
        return 0
    return once()
if __name__=='__main__':sys.exit(main())