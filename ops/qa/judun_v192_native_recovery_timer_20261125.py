#!/usr/bin/env python3
"""Bounded native staging QA recovery; not a production release authority."""
import fcntl, hashlib, json, os, pathlib, runpy, stat, sqlite3, subprocess, sys, time, uuid

TREE='29a007c6329cfdca27aeda9952ca6e1ad904707ec2130f6b33a0d2785f5447e1'
BUILD='1.2.192-OCR-PROVIDER-RECOVERY-20261125'
EXPECTED=dict(version='1.2.192',artifact_id='JUDUN-'+BUILD,build_instance_id=BUILD,source_tree_sha256=TREE,count=98)
PIN='d9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568'
ERROR='辨識服務暫時無法使用（503），請稍後再試；不代表原始文件有問題。'
INITIAL='e376de575dccc7dcf9723a4de376310a3fc492185e975ae4b35fa560fe96b74f'
HOME=pathlib.Path('/root/judun-v192-native-recovery')
SERVICE='judun-v192-native-recovery.service'
TIMER='judun-v192-native-recovery.timer'
LIMIT=2
INTERVAL=1800

def need(ok,code):
    if not ok:raise RuntimeError(code)
def emit(code,**v):print(json.dumps(dict(check=code,**v),ensure_ascii=False),flush=True)
def gate(state,status,error,receipt):
    if receipt:return 'PASS'
    if state.get('phase')!='uploaded':return 'HOLD_OTHER_PHASE'
    if status!='錯誤' or error!=ERROR:return 'HOLD_NOT_EXACT_503'
    return 'RETRY_503'
def selftest():
    cases=[({'phase':'uploaded'},'錯誤',ERROR,False,'RETRY_503'),
    ({'phase':'uploaded'},'錯誤','other',False,'HOLD_NOT_EXACT_503'),
    ({'phase':'uploaded'},'待確認',ERROR,False,'HOLD_NOT_EXACT_503'),
    ({'phase':'confirm_pending'},'錯誤',ERROR,False,'HOLD_OTHER_PHASE'),
    ({},None,None,True,'PASS')]
    for a,b,c,d,w in cases:need(gate(a,b,c,d)==w,'STOP_SELF_TEST')
    need(EXPECTED['build_instance_id']!=EXPECTED['artifact_id'],'STOP_BUILD_ID')
    emit('RECOVERY_GATE_SELF_TEST',status='PASS',cases=len(cases)+1)
def loadq():
    runner=HOME/'runner.py'
    need(runner.is_file() and not runner.is_symlink() and runner.stat().st_uid==0 and not runner.stat().st_mode&0o022,'STOP_RUNNER_OWNER')
    need(hashlib.sha256(runner.read_bytes()).hexdigest()==PIN,'STOP_RUNNER_HASH')
    return runpy.run_path(str(runner),run_name='recovery_qa')
def read(q,p):
    need(q['valid_private'](p),'STOP_PRIVATE_STATE')
    return json.loads(p.read_text())
def stop_timer():
    r=subprocess.run(['systemctl','disable','--now',TIMER],capture_output=True,timeout=30)
    emit('RECOVERY_TIMER_STOP',status='PASS' if r.returncode==0 else 'HOLD_TIMER_STOP_FAILED')
def terminal(q,ledger,state,code):
    state.update(phase='terminal',outcome=code)
    q['atom'](ledger,state)
    emit(code,attempts=state['attempts'],production_release='HOLD')
    stop_timer()
def main():
    selftest()
    if sys.argv[1:]==['--self-test']:return
    need(os.geteuid()==0,'STOP_ROOT')
    need(HOME.is_dir() and not HOME.is_symlink() and HOME.stat().st_uid==0 and not HOME.stat().st_mode&0o077,'STOP_HOME')
    q=loadq()
    root=q['ROOT'];st=root.lstat()
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o077,'STOP_QA_ROOT')
    ledger=root/(TREE+'.native-recovery-ledger.json')
    lock=os.open(root/'v192-native-recovery.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state=read(q,ledger) if ledger.exists() else dict(identity=EXPECTED,attempts=0,phase='idle')
    need(state.get('identity')==EXPECTED and type(state.get('attempts')) is int and 0<=state['attempts']<=LIMIT,'STOP_LEDGER')
    if sys.argv[1:]==['--install']:
        need(state['phase']=='idle' and state['attempts']==0 and not ledger.exists(),'STOP_ALREADY_INITIALIZED')
        # Verify native identity and existing exact synthetic failure before enabling.
        validate(q,root,first=True)
        state['next_epoch']=int(time.time())+INTERVAL
        q['atom'](ledger,state)
        for name,body in [(SERVICE, '[Unit]\nDescription=Judun v192 bounded native staging recovery\n[Service]\nType=oneshot\nUser=root\nUMask=0077\nTimeoutStartSec=45min\nExecStart=/usr/bin/python3 -I -B /root/judun-v192-native-recovery/recover.py --run\n'),(TIMER,'[Unit]\nDescription=Judun v192 native recovery timer\n[Timer]\nOnActiveSec=30min\nOnUnitInactiveSec=30min\nAccuracySec=1min\nUnit='+SERVICE+'\n[Install]\nWantedBy=timers.target\n')]:
            p=pathlib.Path('/etc/systemd/system')/name
            fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
            with os.fdopen(fd,'w') as f:f.write(body);f.flush();os.fsync(f.fileno())
        subprocess.run(['systemctl','daemon-reload'],check=True,timeout=30)
        subprocess.run(['systemctl','enable','--now',TIMER],check=True,timeout=30)
        emit('TIMER_INSTALLED',max_additional_native_cases=LIMIT,interval_seconds=INTERVAL,production_modified=False)
        return
    need(sys.argv[1:]==['--run'],'STOP_ARGUMENTS')
    if state['phase']=='terminal':
        emit('TERMINAL_NO_PROVIDER_CALL',outcome=state.get('outcome'))
        stop_timer()
        return
    if state['phase']!='idle':
        terminal(q,ledger,state,'HOLD_INTERRUPTED_ATTEMPT')
        return
    if int(time.time())<state.get('next_epoch',0):
        emit('NOT_DUE');return
    receipt=root/(TREE+'.receipt.json')
    if receipt.exists():
        r=read(q,receipt);need(r.get('identity')==EXPECTED and r.get('status')=='PASS','STOP_RECEIPT')
        terminal(q,ledger,state,'NATIVE_QA_PASS_OTHER_GATES_PENDING');return
    if state['attempts']>=LIMIT:
        terminal(q,ledger,state,'HOLD_503_ATTEMPT_LIMIT');return
    # Hold QA lock while checking and archiving exact checkpoint. The pinned
    # native runner acquires its own QA lock before upload; never repeat an
    # ambiguous POST or overwrite any existing archive.
    fd=os.open(root/'qa.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        p,s,code=validate(q,root,first=(state['attempts']==0),allow_hold=True)
        if code!='RETRY_503':
            terminal(q,ledger,state,code);return
        dest=root/(TREE+'.native-recovery-failed-'+str(state['attempts'])+'.json')
        need(not os.path.lexists(dest),'STOP_ARCHIVE_EXISTS')
        state['attempts']+=1
        state['phase']='reserved'
        q['atom'](ledger,state)
        os.rename(p,dest)
        emit('ORIGINAL_CHECKPOINT_ARCHIVED',attempt=state['attempts'],production_modified=False)
    finally:os.close(fd)
    args=[sys.executable,'-I','-B',str(HOME/'runner.py'),'--version',EXPECTED['version'],'--artifact',EXPECTED['artifact_id'],'--build',EXPECTED['build_instance_id'],'--tree',TREE,'--count','98']
    rc=subprocess.run(args,stdin=subprocess.DEVNULL,timeout=2400).returncode
    if rc==0 and receipt.exists():
        r=read(q,receipt);need(r.get('identity')==EXPECTED and r.get('status')=='PASS','STOP_RECEIPT')
        terminal(q,ledger,state,'NATIVE_QA_PASS_OTHER_GATES_PENDING');return
    p,s,code=validate(q,root,first=False,allow_hold=True)
    if code!='RETRY_503' or state['attempts']>=LIMIT:
        terminal(q,ledger,state,code if code!='RETRY_503' else 'HOLD_503_ATTEMPT_LIMIT');return
    state.update(phase='idle',next_epoch=int(time.time())+INTERVAL)
    q['atom'](ledger,state)
    emit('EXACT_503_RETRY_SCHEDULED',attempts=state['attempts'],next_in_seconds=INTERVAL)
def validate(q,root,first,allow_hold=False):
    env,data,token=q['read_env']()
    c=q['Client'](token,'',EXPECTED);c.health()
    p=root/(TREE+'.json')
    s=read(q,p);need(s.get('identity')==EXPECTED,'STOP_CHECKPOINT_IDENTITY')
    job=s.get('job_id')
    if s.get('phase')!='uploaded' or not job:
        if allow_hold:return p,s,'HOLD_OTHER_PHASE'
        raise RuntimeError('STOP_NOT_UPLOADED')
    need(str(uuid.UUID(job))==job,'STOP_JOB_ID')
    import re
    nonce=s['nonce'];need(bool(re.fullmatch('[a-f0-9]{16}',nonce)),'STOP_NONCE')
    digest=q['sha'](q['quote'](nonce))
    need(s.get('checks',{}).get('upload',{}).get('sha256')==digest,'STOP_SYNTHETIC_HASH')
    if first:need(digest==INITIAL,'STOP_INITIAL_CASE_HASH')
    with sqlite3.connect((data/'app_data.db').as_uri()+'?mode=ro',uri=True,timeout=5) as db:
        db.execute('PRAGMA query_only=ON')
        row=db.execute('SELECT status,error FROM jobs WHERE id=?',(job,)).fetchone()
    need(row is not None,'STOP_JOB_NOT_FOUND')
    code=gate(s,row[0],row[1],False)
    if code=='RETRY_503':
        need(c.j('/status-lite/'+job)[0].get('status')=='錯誤','STOP_STATUS_DISAGREEMENT')
        codes=[env.get('TEST_PAYMENT_CODE',''),env.get('JUDUN_QA_TEST_CODE','')]
        saved=root/'test-code'
        if saved.exists():need(q['valid_private'](saved),'STOP_STAGE_CODE_FILE');codes.append(saved.read_text().strip())
        need(any(v and q['sha'](v.encode())==q['CODE_PIN'] for v in codes),'STOP_STAGE_CODE_UNAVAILABLE')
    if not allow_hold:need(code=='RETRY_503','STOP_NOT_EXACT_503')
    return p,s,code
if __name__=='__main__':
    try:
        os.umask(0o077);main()
    except Exception as e:
        msg=str(e);emit('HOLD',error=msg if msg.startswith('STOP_') and msg.isascii() and len(msg)<160 else type(e).__name__)
        if sys.argv[1:]==['--run'] and os.geteuid()==0:
            try:stop_timer()
            except Exception:emit('HOLD_TIMER_STOP_FAILED')
        sys.exit(2)
