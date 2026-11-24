#!/usr/bin/env python3
"""One bounded stage-only recovery campaign. Preserve the two original cases.
No production requests, real payment, edits to signed source or bypass of QA.
"""
import fcntl, hashlib, json, os, pathlib, re, runpy, stat, subprocess, sys, tempfile, time, uuid

BASE='https://raw.githubusercontent.com/momopuke/judun-deploy/'
RUNNER=('dddae11693a904a7e9fa741e7222fa39bc8c3f4a/ops/qa/judun_stage_native_business_qa_v3_20261124.py','d9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568')
SDK=('be5dd2fe788430d25d783b9c10be3030370d08f2/ops/qa/judun_v191_sdk_exception_rca_20261125.py','48370026e3a63a54ee14eadd1c0efd6842a36c3f')
FAILED='a725a3576d956db72a8cb16d51efb107b338429e3746c068ec0d177976c56eb9'
FIRST='e3052d04b49362c110f410fe2a1adffbf67542879b2127110a2f28105a5a1845'
DELAYS=(60,120,240)

def need(ok,code):
    if not ok:raise SystemExit(code)
def classify(r):
    if not (r.get('check')=='OCR_PROBE' and r.get('stage_identity_after')=='PASS' and r.get('new_jobs')==0 and r.get('production_modified') is False):
        return 'STOP'
    d=r.get('diagnostic') or {}
    if r.get('code')=='APP_EXACT_PASS' and r.get('rows')==r.get('expected')==d.get('valid')==4 and d.get('calls')==1:
        return 'PASS'
    t=set(d.get('trace') or [])
    if r.get('code')=='APP_EXCEPTION' and d.get('phase')=='WORKER' and d.get('calls')==1 and {'SDK_EXCEPTION_TYPE=ServerError','SDK_HTTP_STATUS=503','SDK_STATUS=UNAVAILABLE'}<=t:
        return 'RETRY'
    return 'STOP'
def self_test():
    base=dict(check='OCR_PROBE',stage_identity_after='PASS',new_jobs=0,production_modified=False)
    good=dict(base,code='APP_EXACT_PASS',rows=4,expected=4,diagnostic=dict(valid=4,calls=1))
    bad=dict(base,code='APP_EXCEPTION',diagnostic=dict(phase='WORKER',calls=1,trace=['SDK_EXCEPTION_TYPE=ServerError','SDK_HTTP_STATUS=503','SDK_STATUS=UNAVAILABLE']))
    for obj,want in [(good,'PASS'),(bad,'RETRY'),(dict(good,rows=3),'STOP'),(dict(good,production_modified=True),'STOP'),(dict(good,new_jobs=1),'STOP'),(dict(bad,diagnostic={'phase':'WORKER','calls':1,'trace':['SDK_HTTP_STATUS=429']}),'STOP'),(dict(bad,stage_identity_after='FAIL'),'STOP'),({},'STOP')]:
        need(classify(obj)==want,'STOP_SELF_TEST')
    print('503_GATE_SELF_TEST=8/8_PASS',flush=True)
def download(dst,spec,blob=False):
    subprocess.run(['/usr/bin/curl','-fsSL','--proto','=https','--tlsv1.2','--retry','2','--max-time','60',BASE+spec[0],'-o',str(dst)],check=True,timeout=90)
    raw=dst.read_bytes()
    actual=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() if blob else hashlib.sha256(raw).hexdigest()
    need(actual==spec[1],'STOP_TOOL_HASH')
def private_json(q,p):
    need(q['valid_private'](p),'STOP_PRIVATE_STATE')
    return json.loads(p.read_text())
def run_probe(sdk):
    p=subprocess.run([sys.executable,'-I','-B',str(sdk)],capture_output=True,text=True,timeout=480)
    rows=[]
    for line in p.stdout.splitlines():
        try:r=json.loads(line)
        except ValueError:continue
        if isinstance(r,dict) and r.get('check')=='OCR_PROBE':rows.append(r)
    if p.returncode!=0 or len(rows)!=1:
        return 'STOP'
    result=classify(rows[0])
    print('NATIVE_OCR_PREFLIGHT='+result,flush=True)
    return result
def main():
    self_test()
    if sys.argv[1:]==['--self-test']:return
    need(len(sys.argv)==1 and os.geteuid()==0,'STOP_ARGUMENTS_OR_ROOT')
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='judun-503-resume-',dir='/root') as tmp:
        d=pathlib.Path(tmp);runner=d/'runner.py';sdk=d/'sdk.py'
        download(runner,RUNNER);download(sdk,SDK,True)
        q=runpy.run_path(str(runner),run_name='qa_resume_503')
        root=q['ROOT']; st=root.lstat()
        need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o077,'STOP_QA_ROOT')
        outer=os.open(root/'resume-once.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
        fcntl.flock(outer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        e=q['DEFAULT'];tree=e['source_tree_sha256']
        p=root/(tree+'.json');first=root/(tree+'.original-ocr-failure.json')
        second=root/(tree+'.second-ocr-failure.json');ledger=root/(tree+'.503-recovery.json');receipt=root/(tree+'.receipt.json')
        env,_,token=q['read_env']();c=q['Client'](token,'',e);c.health()
        codefile=root/'test-code'
        values=[env.get('TEST_PAYMENT_CODE',''),env.get('JUDUN_QA_TEST_CODE','')]
        if codefile.exists():
            need(q['valid_private'](codefile),'STOP_STAGE_CODE_FILE')
            values.append(codefile.read_text().strip())
        need(any(v and q['sha'](v.encode())==q['CODE_PIN'] for v in values),'STOP_SAVED_STAGE_CODE_UNAVAILABLE')
        def failed_state(path,digest):
            s=private_json(q,path)
            need(s.get('identity')==e and s.get('phase')=='uploaded','STOP_ORIGINAL_PHASE')
            need(q['sha'](q['quote'](s['nonce']))==s['checks']['upload']['sha256']==digest,'STOP_ORIGINAL_HASH')
            job=s['job_id'];need(str(uuid.UUID(job))==job,'STOP_JOB_ID')
            need(c.j('/status-lite/'+job)[0].get('status')=='錯誤','STOP_ORIGINAL_NOT_FAILED')
        def state_lock():
            fd=os.open(root/'qa.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);return fd
        if receipt.exists():
            r=private_json(q,receipt)
            need(r.get('identity')==e and r.get('status')=='PASS','STOP_RECEIPT')
            print('EXISTING_NATIVE_QA_RECEIPT=PASS; RELEASE_STILL_REQUIRES_OTHER_GATES',flush=True);return
        failed_state(first,FIRST)
        state=private_json(q,ledger) if ledger.exists() else dict(identity=e,attempts=0,phase='preflight')
        need(state.get('identity')==e and type(state.get('attempts')) is int and 0<=state['attempts']<=len(DELAYS),'STOP_CAMPAIGN_LEDGER')
        if second.exists():
            failed_state(second,FAILED)
            need(state.get('phase')=='ready','STOP_ARCHIVE_WITHOUT_PREFLIGHT')
            if not p.exists():
                need(time.time()-state.get('ready_epoch',0)<=300,'STOP_STALE_PREFLIGHT_WITH_NO_JOB')
            else:
                s=private_json(q,p);need(s.get('identity')==e,'STOP_NEW_STATE_IDENTITY')
                need(s.get('checks',{}).get('upload',{}).get('sha256') not in (FIRST,FAILED),'STOP_ORIGINAL_ACTIVE')
            print('RESUME_EXISTING_RECOVERY_CAMPAIGN_ONLY',flush=True)
        else:
            need(state.get('phase')=='preflight','STOP_CAMPAIGN_STATE')
            failed_state(p,FAILED)
            while state['attempts']<len(DELAYS):
                delay=DELAYS[state['attempts']]
                print('PROVIDER_BACKOFF_SECONDS='+str(delay),flush=True)
                time.sleep(delay)
                c.health();failed_state(p,FAILED)
                state['attempts']+=1;q['atom'](ledger,state)
                verdict=run_probe(sdk)
                if verdict=='RETRY':continue
                if verdict!='PASS':
                    state['phase']='stopped';q['atom'](ledger,state)
                    raise SystemExit('HOLD_NON_503_OR_UNVERIFIED_PREFLIGHT')
                fd=state_lock()
                try:
                    c.health();failed_state(p,FAILED)
                    need(not second.exists(),'STOP_SECOND_ARCHIVE_EXISTS')
                    state['phase']='ready';state['ready_epoch']=time.time();q['atom'](ledger,state)
                    os.rename(p,second)
                    print('BOTH_FAILED_CHECKPOINTS_PRESERVED=PASS',flush=True)
                finally:os.close(fd)
                break
            need(state.get('phase')=='ready','HOLD_PROVIDER_503_RETRY_LIMIT_REACHED')
        c.health()
        print('ONE_NATIVE_RECOVERY_CASE_MAX; NO_REAL_PAYMENT; PRODUCTION_HOLD',flush=True)
        # The pinned runner persists its upload intent before POST and refuses
        # to repeat ambiguous uploads/confirmations or to create a second case.
        rc=subprocess.run([sys.executable,'-I','-B',str(runner),'--remember-stage-code']).returncode
        if rc:raise SystemExit(rc)
        r=private_json(q,receipt)
        need(r.get('identity')==e and r.get('status')=='PASS','STOP_RECEIPT')
        print('NATIVE_BUSINESS_QA=PASS; RELEASE_STILL_REQUIRES_OTHER_GATES',flush=True)
if __name__=='__main__':main()
