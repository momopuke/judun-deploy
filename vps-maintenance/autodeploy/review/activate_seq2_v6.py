#!/usr/bin/env python3
"""SC VPS: recover signed updater after a legacy seq-1 safety refusal.

Strict scope: upgrades only the already pinned signed updater and its service
260s->900s; runs ONLY signed seq-2 read-only status. Never re-applies v10,
changes browser memory policy, restarts protected services or erases receipts.
"""
from __future__ import annotations
import base64
import datetime as dt
import fcntl
import hashlib
import types
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

V5_PATH=Path('/tmp/sc-vps-reconcile-v5.py')
V5_SHA='7cafdeccee1ef3deab269399d840f85d988eb642e1f70bb219c802c2cc09c332'
V5_URL='https://raw.githubusercontent.com/momopuke/judun-deploy/e44fe97a77249632b47c5bbfb8ccf739b4258876/vps-maintenance/autodeploy/review/reconcile_v5.py'
CHANNEL='https://raw.githubusercontent.com/momopuke/judun-deploy/vps-maintenance/vps-maintenance/autodeploy/'
MANIFEST_SHA='d426a61640a1c5fe9a1710b815514611a6ece382b386269fb574e1b59a51c8d7'
SIGNATURE_SHA='00e20771dfd2ca601231b42437052507645f664e5cdcc3d23930b1a4f5e4dbc7'
RELEASE='SC-VPS-v10-20261104-a1'

class Rejected(Exception): pass

def sha(data): return hashlib.sha256(data).hexdigest()

def fetch(url,limit):
    req=urllib.request.Request(url,headers={'User-Agent':'SC-VPS-Seq2-Recovery/1','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=25) as h:
        if h.status!=200:raise Rejected('FETCH_STATUS_NOT_200')
        z=h.read(limit+1)
    if len(z)>limit or not z:raise Rejected('FETCH_SIZE_INVALID')
    return z

def load_verified_v5():
    if V5_PATH.is_symlink():raise Rejected('BASE_V5_SYMLINK')
    if V5_PATH.exists():
        data=V5_PATH.read_bytes()
        if sha(data)!=V5_SHA:raise Rejected('BASE_V5_HASH_MISMATCH')
    else:
        data=fetch(V5_URL,50000)
        if sha(data)!=V5_SHA:raise Rejected('BASE_V5_FETCH_HASH_MISMATCH')
        # Run code from an isolated local temporary file; never overwrite a
        # preexisting path. The source is pinned by its full SHA256.
        V5_PATH.parent.mkdir(parents=True,exist_ok=True)
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
        if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
        try:
            fd=os.open(V5_PATH,flags,0o600)
            with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        except FileExistsError:raise Rejected('BASE_V5_CONCURRENT_CHANGE')
    # Compile precisely the bytes whose SHA256 was checked, not a cached pyc.
    mod=types.ModuleType('sc_v5_verified')
    exec(compile(data,str(V5_PATH),'exec'),mod.__dict__)
    return mod

def parse_receipt(raw):
    if raw is None or len(raw)>12000:return 'UNKNOWN'
    try:d=json.loads(raw)
    except (ValueError,UnicodeError):return 'UNKNOWN'
    if not isinstance(d,dict) or d.get('release_id')!=RELEASE:return 'UNKNOWN'
    a,b=d.get('protected_before'),d.get('protected_after')
    if not isinstance(a,dict) or a!=b:return 'UNKNOWN'
    if a.get('stripchat-browser-desktop.service')!='active' or a.get('stripchat-recorder')!='true':return 'UNKNOWN'
    if a.get('line-openchat-guard.service') not in ('active','unknown'):return 'UNKNOWN'
    x=d.get('result')
    if not isinstance(x,dict) or type(x.get('exit_code')) is not int:return 'UNKNOWN'
    if (type(d.get('last_sequence')) is int and d['last_sequence']==1 and d.get('operation')=='apply'
            and d.get('status')=='safety_refused' and d.get('code_restored') is True
            and x['exit_code']==3 and 'code_installed' not in d):
        return 'LEGACY_SEQ1_REFUSED_UNVERIFIED_MEMORY'
    if (type(d.get('last_sequence')) is int and d['last_sequence']==2 and d.get('operation')=='status'
            and d.get('status')=='applied' and x['exit_code']==0):
        if d.get('code_restored') is False and 'code_installed' not in d:
            return 'LEGACY_SEQ2_STATUS_APPLIED'
        if d.get('code_installed') is False and 'code_restored' not in d:
            return 'CURRENT_SEQ2_STATUS_APPLIED'
    return 'UNKNOWN'

def load_channel(m):
    manifest=fetch(CHANNEL+'channel.json',8192)
    sig64=fetch(CHANNEL+'channel.sig.b64',1024)
    if sha(manifest)!=MANIFEST_SHA or sha(sig64)!=SIGNATURE_SHA:
        raise Rejected('SIGNED_CHANNEL_CHANGED_REQUIRES_REVIEW')
    try: doc=json.loads(manifest)
    except (ValueError,UnicodeError):raise Rejected('CHANNEL_JSON_INVALID')
    if doc.get('sequence')!=2 or doc.get('operation')!='status' or doc.get('release_id')!=RELEASE:
        raise Rejected('CHANNEL_NOT_PINNED_SEQ2_STATUS')
    sig=base64.b64decode(b''.join(sig64.split()),validate=True)
    if len(sig)!=64:raise Rejected('CHANNEL_SIGNATURE_LENGTH')
    with tempfile.TemporaryDirectory(prefix='sc-vps-seq2-verify-') as td:
        p=Path(td); (p/'doc').write_bytes(manifest);(p/'sig').write_bytes(sig)
        a=subprocess.run(['/usr/bin/openssl','pkeyutl','-verify','-pubin','-inkey',str(m.PUB),
                          '-rawin','-in',str(p/'doc'),'-sigfile',str(p/'sig')],
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if a.returncode!=0:raise Rejected('CHANNEL_SIGNATURE_INVALID')
    return doc

def observe_protected(m):
    return {'browser':m.proc('systemctl','show','stripchat-browser-desktop.service','-p','ActiveState','--value'),
            'line':m.proc('systemctl','show','line-openchat-guard.service','-p','ActiveState','--value'),
            'recorder':m.proc('docker','inspect','-f','{{.State.Running}}','stripchat-recorder')}

def inspect(m):
    a=m.safe_read(m.AGENT,30000);k=m.safe_read(m.PUB,4096)
    s=m.safe_read(m.SERVICE,8192); t=m.safe_read(m.TIMER,8192)
    state=m.safe_read(m.STATE,12000)
    agent=m.agent_variant(a);unit=m.service_variant(s)
    if agent not in ('CURRENT','KNOWN_LEGACY'):raise Rejected('UNRECOGNIZED_AGENT')
    if unit not in ('CURRENT','SAFE_260_TIMEOUT_ONLY'):raise Rejected('UNRECOGNIZED_SERVICE_UNIT')
    if k is None or sha(k)!=m.PUB_SHA256:raise Rejected('TRUST_ROOT_MISMATCH')
    if t is None:raise Rejected('TIMER_UNIT_MISSING')
    m.ensure_known_unit(m.TIMER,t,{m.UNIT_TIMER_180.encode(),m.UNIT_TIMER_300.encode()})
    r=parse_receipt(state)
    if r=='UNKNOWN':raise Rejected('UNVERIFIED_PREVIOUS_RELEASE_STATE')
    if m.systemd_state('sc-vps-autodeploy.service') in ('active','activating','reloading'):
        raise Rejected('UPDATE_SERVICE_BUSY')
    if not m.rollback_watchdogs_clear():raise Rejected('ROLLBACK_WATCHDOGS_NOT_CLEAR')
    return {'agent':a,'key':k,'service':s,'timer':t,'state':state,'agent_type':agent,
            'unit_type':unit,'receipt_type':r,
            'timer_active':m.systemd_state('sc-vps-autodeploy.timer')=='active'}

def read_only_success(m):
    state=m.safe_read(m.STATE,12000)
    if parse_receipt(state) not in ('CURRENT_SEQ2_STATUS_APPLIED','LEGACY_SEQ2_STATUS_APPLIED'):
        return False
    d=json.loads(state)
    if d.get('last_sequence')!=2 or d.get('operation')!='status':return False
    if d.get('status')!='applied' or d.get('result',{}).get('exit_code')!=0:return False
    if d.get('code_installed') is not False:return False
    return True

def main():
    if '--self-test' in sys.argv:
        assert parse_receipt(None)=='UNKNOWN'
        assert parse_receipt(b'{}')=='UNKNOWN'
        assert parse_receipt(b'{')=='UNKNOWN'
        print('SC_VPS_SEQ2_MIGRATION_SELF_TEST_PASS');return 0
    if os.geteuid()!=0:raise Rejected('ROOT_REQUIRED')
    m=load_verified_v5()
    for p in (m.BASE,m.STATE.parent,m.SERVICE.parent,m.TIMER.parent):
        if p.is_symlink():raise Rejected('UNSAFE_PARENT_SYMLINK')
    lock=m.ENROLL_LOCK
    if lock.is_symlink():raise Rejected('ENROLL_LOCK_SYMLINK')
    flags=os.O_RDWR|os.O_CREAT
    if hasattr(os,'O_NOFOLLOW'):flags|=os.O_NOFOLLOW
    fd=os.open(lock,flags,0o600)
    with os.fdopen(fd,'r+') as lk:
        try:fcntl.flock(lk.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise Rejected('ANOTHER_ENROLLMENT_IN_PROGRESS')
        sample=inspect(m)
        channel=load_channel(m)
        baseline=observe_protected(m)
        if baseline['browser']!='active' or baseline['recorder']!='true':raise Rejected('PROTECTED_SERVICE_INACTIVE')
        print('SC_VPS_SEQ2_RECOVERY_PRECHECK',json.dumps({
            'agent':sample['agent_type'],'unit':sample['unit_type'],'receipt':sample['receipt_type'],
            'timer_active':sample['timer_active'],'channel':str(channel['sequence'])+':'+channel['operation']}),flush=True)
        if (sample['agent_type']=='CURRENT' and sample['unit_type']=='CURRENT'
            and read_only_success(m) and sample['timer_active']):
            m.verify_effective_timeout()
            print('SC_VPS_SEQ2_CHANNEL_VERIFIED_ALREADY_ACTIVE');return 0
        # Source identity verified. Preserve the historical seq-1 refusal,
        # even though its v10 memory outcome remains *unknown*.
        if sample['receipt_type']=='LEGACY_SEQ2_STATUS_APPLIED' and not m.signed_v10_installed():
            raise Rejected('LEGACY_SEQ2_SOURCE_HASH_MISMATCH')
        if sample['agent_type']=='CURRENT' and sample['receipt_type']=='LEGACY_SEQ1_REFUSED_UNVERIFIED_MEMORY':
            # Allowed after a previous partial upgrade. No v10 re-application.
            pass
        lockpath=m.STATE.parent/'lock'
        if lockpath.is_symlink():raise Rejected('AGENT_LOCK_SYMLINK')
        f2=os.O_CREAT|os.O_RDWR
        if hasattr(os,'O_NOFOLLOW'):f2|=os.O_NOFOLLOW
        fda=os.open(lockpath,f2,0o600)
        changed=[];agent_started=False;old_timer_active=sample['timer_active']
        with os.fdopen(fda,'r+') as agentlock:
            try:fcntl.flock(agentlock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise Rejected('OLD_AGENT_CURRENTLY_RUNNING')
            if m.safe_read(m.STATE,12000)!=sample['state'] or m.safe_read(m.AGENT,30000)!=sample['agent'] or m.safe_read(m.SERVICE,8192)!=sample['service']:
                raise Rejected('RACE_PREVENTED_FILES_CHANGED')
            if old_timer_active:
                m.proc('systemctl','stop','sc-vps-autodeploy.timer',timeout=45)
                if m.systemd_state('sc-vps-autodeploy.timer')=='active':raise Rejected('TIMER_STOP_UNCONFIRMED')
            try:
                if sample['agent_type']=='KNOWN_LEGACY':
                    new=m.fetch_trusted_agent()
                    m.make_backup(m.AGENT,sample['agent'])
                    m.atomic_update_existing(m.AGENT,sample['agent'],new)
                    changed.append((m.AGENT,sample['agent'],new))
                    print('SC_VPS_VERIFIED_AGENT_UPDATED',flush=True)
                if sample['unit_type']=='SAFE_260_TIMEOUT_ONLY':
                    new=sample['service'].replace(b'TimeoutStartSec=260s',b'TimeoutStartSec=900s')
                    if m.service_variant(new)!='CURRENT':raise Rejected('UNEXPECTED_SERVICE_REWRITE')
                    m.make_backup(m.SERVICE,sample['service'])
                    m.atomic_update_existing(m.SERVICE,sample['service'],new)
                    changed.append((m.SERVICE,sample['service'],new))
                    m.proc('systemctl','daemon-reload',timeout=45)
                    print('SC_VPS_TIMEOUT_UPDATED_260_TO_900',flush=True)
                m.verify_effective_timeout()
                if sha(m.safe_read(m.AGENT,30000))!=m.AGENT_SHA256:raise Rejected('AGENT_FINAL_SHA_MISMATCH')
                if m.safe_read(m.STATE,12000)!=sample['state']:raise Rejected('HISTORICAL_RECEIPT_CHANGED')
                if observe_protected(m)!=baseline:raise Rejected('PROTECTED_SERVICES_CHANGED_PRESTATUS')
                # Preserve the old signed apply refusal in a local root-only
                # backup before the new agent writes a seq-2 status receipt.
                m.make_backup(m.STATE,sample['state'])
            except BaseException:
                for path,old,new in reversed(changed):
                    try:m.atomic_update_existing(path,new,old)
                    except Exception:print('SC_VPS_ROLLBACK_NEEDS_REVIEW',path.name,flush=True)
                try:m.proc('systemctl','daemon-reload',timeout=45)
                except Exception:pass
                if old_timer_active:
                    try:m.proc('systemctl','start','sc-vps-autodeploy.timer',timeout=45)
                    except Exception:print('SC_VPS_TIMER_RESTORE_NEEDS_REVIEW',flush=True)
                raise
        # The legacy agent lock is released; the enrollment lock remains held.
        # New agent's signed seq-2 STATUS executes in an isolated temp folder.
        # It NEVER calls v10 --apply or changes memory.high.
        try:
            if sample['receipt_type']=='LEGACY_SEQ2_STATUS_APPLIED':
                # Old agent has *already* consumed signed seq-2 status and
                # installed exactly the seven pinned v10 source files. Starting
                # the new agent cannot rerun that sequence and must not be
                # claimed to have done so.
                if m.safe_read(m.STATE,12000)!=sample['state'] or not m.signed_v10_installed():
                    raise Rejected('LEGACY_SEQ2_STATUS_CHANGED')
                print('SC_VPS_LEGACY_SEQ2_SIGNED_STATUS_CONFIRMED',flush=True)
            elif sample['receipt_type']=='CURRENT_SEQ2_STATUS_APPLIED':
                if not read_only_success(m):raise Rejected('SEQ2_NEW_AGENT_STATE_UNVERIFIED')
                print('SC_VPS_CURRENT_SEQ2_SIGNED_STATUS_CONFIRMED',flush=True)
            else:
                # Sequence 1 was a safe refusal, but does not prove the memory
                # change rolled back. This command ONLY checks v10 status.
                agent_started=True
                m.proc('systemctl','start','sc-vps-autodeploy.service',timeout=920)
                if not read_only_success(m):raise Rejected('SEQ2_SIGNED_STATUS_DID_NOT_PASS')
            if observe_protected(m)!=baseline:raise Rejected('PROTECTED_SERVICES_CHANGED_AFTER_STATUS')
            m.proc('systemctl','enable','--now','sc-vps-autodeploy.timer',timeout=45)
            if m.systemd_state('sc-vps-autodeploy.timer')!='active':raise Rejected('NEW_TIMER_NOT_ACTIVE')
            m.verify_effective_timeout()
            print('SC_VPS_SIGNED_SEQ2_STATUS_ACCEPTED',flush=True)
            print('SC_VPS_AUTO_DEPLOY_AGENT_ENROLLED_AND_TIMER_ACTIVE',flush=True)
            print('NOTE_V10_MEMORY_FIX_NOT_VERIFIED_BY_STATUS',flush=True)
            return 0
        except BaseException:
            # Do not roll back after starting the new agent: it may have
            # committed a durable state. Preserve the new agent and backups.
            if agent_started:
                try:m.proc('systemctl','stop','sc-vps-autodeploy.timer',timeout=45)
                except Exception:pass
                print('SC_VPS_SEQ2_STATUS_NEEDS_REVIEW_TIMER_STOPPED',flush=True)
            raise

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print('SC_VPS_SEQ2_RECOVERY_BLOCKED',str(e) if isinstance(e,Rejected) else type(e).__name__,flush=True)
        sys.exit(9)
