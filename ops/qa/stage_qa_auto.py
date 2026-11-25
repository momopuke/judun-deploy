#!/usr/bin/env python3
"""One native stage-only QA attempt per immutable selected snapshot."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import runpy
import stat
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path

STAGE = Path('/srv/judun-staging')
PULL = Path('/var/lib/judun-staging-pull')
STATE = Path('/var/lib/judun-stage-native-qa-auto')
RECEIPTS = Path('/var/lib/judun-stage-business-qa')
TOOLS = Path('/opt/judun-stage-qa-auto')
LAUNCHER_SHA = '25e060c2ce7702a59edbf01f025ec8da50d82e1fc185d21eb689b543ff760dc2'
QA_SHA = 'd9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568'

def need(ok, reason):
    if not ok:
        raise ValueError(reason)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def secure_read(path, limit=1048576, private=True):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as f:
        s = os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid() and s.st_nlink == 1, 'UNSAFE_FILE')
        need(not (s.st_mode & (0o077 if private else 0o022)), 'UNSAFE_MODE')
        raw = f.read(limit+1)
    need(0 < len(raw) <= limit, 'FILE_SIZE')
    return raw

def snapshot(stage):
    link = os.readlink(stage/'current')
    match = re.fullmatch(r'releases/(JUDUN-[A-Za-z0-9._-]{1,120})-([0-9a-f]{64})', link)
    need(match is not None, 'INVALID_STAGE_SELECTION')
    return match.group(1), match.group(2), digest(link.encode())

def receipt_at(root, artifact, tree):
    raw = secure_read(root/(tree+'.receipt.json'))
    data = json.loads(raw)
    e = data.get('identity', {})
    need(data.get('status') == 'PASS' and e.get('artifact_id') == artifact and e.get('source_tree_sha256') == tree and type(e.get('count')) is int and e['count'] > 0, 'RECEIPT_IDENTITY')
    return digest(raw)

def atomic(path, value):
    tmp = path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, sort_keys=True); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
        d = os.open(path.parent, os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(d)
        finally: os.close(d)
    finally:
        tmp.unlink(missing_ok=True)

def existing_lock(stack, path):
    fd = os.open(path, os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK)
    stack.callback(os.close, fd)
    s = os.fstat(fd)
    need(stat.S_ISREG(s.st_mode) and s.st_uid == os.geteuid() and s.st_nlink == 1 and not(s.st_mode&0o077), 'UNSAFE_LOCK')
    fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)

def once(stage, pull, state, receipts, invoke):
    with ExitStack() as stack:
        try:
            # Same lock order as existing staging pull agent; never switch during QA.
            existing_lock(stack,pull/'.lock')
            existing_lock(stack,stage/'.lock')
        except BlockingIOError:
            return {'status':'BUSY_RETRY_NEXT_PULL'}
        artifact, tree, key = snapshot(stage)
        p = state/(key+'.json')
        if os.path.lexists(p):
            prior = json.loads(secure_read(p))
            return {'status':'ALREADY_ATTEMPTED','previous':prior['status'],'tree':tree}
        record = {'status':'STARTED','artifact':artifact,'tree':tree}
        atomic(p,record)  # persistent BEFORE invoking a potentially mutating QA job
        try:
            rc = invoke()
            need(rc == 0, 'QA_EXIT_'+str(rc))
            need(snapshot(stage)==(artifact,tree,key), 'STAGE_CHANGED')
            result = receipt_at(receipts,artifact,tree)
            record.update(status='PASS',receipt_sha256=result)
        except Exception as e:
            record.update(status='HOLD',reason=str(e) if type(e) is ValueError else type(e).__name__)
        atomic(p,record)
        return record

def verify_tool(path, pin):
    need(digest(secure_read(path, 256000)) == pin,'TOOL_PIN_MISMATCH')

def main():
    p = argparse.ArgumentParser(); p.add_argument('--probe',action='store_true'); p.add_argument('--needs-run',action='store_true'); args=p.parse_args()
    need(os.geteuid()==0,'ROOT_REQUIRED'); os.umask(0o077)
    if args.needs_run:
        _,_,key=snapshot(STAGE)
        return 1 if os.path.lexists(STATE/(key+'.json')) else 0
    launch=TOOLS/'launcher.py'; qa_path=TOOLS/'native_qa.py'
    verify_tool(launch,LAUNCHER_SHA)
    if args.probe:
        verify_tool(qa_path,QA_SHA)
        qa=runpy.run_path(str(qa_path),run_name='judun_code_probe')
        env,_,_=qa['read_env']()
        codes=[env.get('TEST_PAYMENT_CODE',''),env.get('JUDUN_QA_TEST_CODE','')]
        codefile=RECEIPTS/'test-code'
        if os.path.lexists(codefile):
            codes.append(secure_read(codefile,4096).decode().strip())
        ready=any(c and digest(c.encode())==qa['CODE_PIN'] for c in codes)
        print('NONINTERACTIVE_STAGE_CODE='+('READY' if ready else 'NOT_READY'),flush=True)
        need(ready,'STAGE_TEST_CODE_UNAVAILABLE')
        return subprocess.run([sys.executable,'-I','-B',str(launch)],stdin=subprocess.DEVNULL,check=False).returncode
    need(STATE.is_dir() and not STATE.is_symlink(),'STATE_DIR_REQUIRED')
    ss=STATE.stat(); need(ss.st_uid==0 and not(ss.st_mode&0o077),'STATE_DIR_UNSAFE')
    # Capture native output in the journal only; the original QA never outputs its test code.
    result=once(STAGE,PULL,STATE,RECEIPTS,lambda:subprocess.run([sys.executable,'-I','-B',str(launch),'--run'],stdin=subprocess.DEVNULL,check=False).returncode)
    print(json.dumps(result,sort_keys=True),flush=True)
    return 2 if result.get('status')=='HOLD' else 0

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as e:
        print('HOLD:',str(e) if type(e) is ValueError else type(e).__name__,flush=True);sys.exit(2)
