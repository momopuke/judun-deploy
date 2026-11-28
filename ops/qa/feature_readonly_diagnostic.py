#!/usr/bin/env python3
"""Read-only feature diagnostic. No business POST, service restart, or DB write."""
import base64, hashlib, json, os, re, runpy, stat, subprocess, tempfile
from contextlib import ExitStack
from pathlib import Path

TOOLS=Path('/opt/judun-stage-qa-auto')
FEATURE=Path('/opt/judun-feature-qa')
ROOT=Path('/var/lib/judun-stage-business-qa')
PUB=Path('/opt/judun-autodeploy/keys/release_signing_public.pem')
PIN='17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'
AUTO='452ed674c51edf848c7bd4b90c2a5e0be318baa115487cdac4f4804728aeb108'
LAUNCHER='25e060c2ce7702a59edbf01f025ec8da50d82e1fc185d21eb689b543ff760dc2'
HANDLERS='ad0009bf78944226525b9656ecee610e212cfa2fd6449a4add877fec102303c9'
CONTRACT='0148e7899e8889e489257a941817a8bbf572cd8fdaad20e32188043b5f11f199'
CODES=set('MODEL_TARGET_NOT_PROVEN PAID_THEME_TARGET_NOT_PROVEN MARKUP_ROLE MARKUP_FIELDS MARKUP_FOREIGN_FIELDS MARKUP_SUMMARY MARKUP_COMPANY_NAV MARKUP_HTTP FEATURE_TIMEOUT_RESUME_SAME_CASE FEATURE_ANALYSIS_FAILED FEATURE_MODEL_OR_COUNT FRESH_CORE_MODEL_NOT_PROVEN FEATURE_ITEMS_INCOMPLETE FEATURE_FINAL_PROGRESS FEATURE_BUDGET_EXCEEDED AMBIGUOUS_POST_NO_REPEAT FEATURE_PROGRESS_REGRESSION FEATURE_STATE_IDENTITY FEATURE_RECEIPT_IDENTITY NATIVE_RECEIPT_PIN NATIVE_RECEIPT_IDENTITY NATIVE_STATE_UNSAFE NATIVE_STATE_IDENTITY NATIVE_CASE_PIN SYNTHETIC_TRACE_CASE_MISSING UNEXPECTED_PAYMENT_ORDER FEATURE_EVIDENCE_PENDING FEATURE_EVIDENCE_BUSY_RETRY FILE_SIZE UNSAFE_FILE STAGE_SELECTION SIGNATURE_INVALID TOOL_PIN IDENTITY_MISMATCH HTTPError URLError Stop BlockingIOError TimeoutError PermissionError FileNotFoundError'.split())
PHASES={'new','upload_pending','uploaded','confirm_pending','confirmed'}
def need(ok,code):
    if not ok:raise ValueError(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def secure(p,limit=262144,private=True):
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and not s.st_mode&(0o077 if private else 0o022),'UNSAFE_FILE')
        raw=f.read(limit+1)
    need(0<len(raw)<=limit,'FILE_SIZE');return raw
def load(p,pin):
    need(sha(secure(p))==pin,'TOOL_PIN')
    return runpy.run_path(str(p),run_name='judun_feature_diag')
def emit(**d):print(json.dumps(d,sort_keys=True),flush=True)
def summarize_models(d,target):
    models=d.get('paid_theme_models',{})
    need(isinstance(models,dict),'TRACE_SCHEMA')
    expected={'g1','g2','g3','g4','g5'}
    present=expected&set(models)
    return {'configured_target':d.get('configured_model')==target,'core_target':d.get('core_model')==target,'core_no_fallback':d.get('core_fallback') is False,'paid_present':len(present),'paid_target':sum(isinstance(models[k],dict) and models[k].get('model')==target for k in present),'paid_no_fallback':sum(isinstance(models[k],dict) and models[k].get('fallback') is False for k in present)}
def summarize_checkpoint(d,identity,plan_sha):
    need(d.get('identity')==identity and d.get('plan_sha256')==plan_sha,'FEATURE_STATE_IDENTITY')
    phase=d.get('phase')
    need(phase in PHASES,'FEATURE_PHASE')
    samples=d.get('samples',[]);need(isinstance(samples,list),'FEATURE_SAMPLES')
    out={'phase':phase}
    if samples:
        v=samples[-1]
        if isinstance(v,dict) and type(v.get('done')) is int and type(v.get('total')) is int and 0<=v['done']<=v['total']<=116:
            out.update(done=v['done'],total=v['total'],stalled=v.get('stalled') is True)
    return out
def unit_status(unit):
    p=subprocess.run(['systemctl','show',unit,'-p','ActiveState,SubState,Result,ExecMainStatus'],capture_output=True,text=True,timeout=10,check=True)
    d={}
    for line in p.stdout.splitlines():
        k,_,v=line.partition('=')
        if k in {'ActiveState','SubState','Result','ExecMainStatus'} and re.fullmatch('[a-z0-9-]{1,40}',v):d[k]=v
    emit(unit=unit,**d)
def log_codes(unit):
    p=subprocess.run(['journalctl','-u',unit,'--since','2026-11-28 09:32:00 UTC','-n','180','--no-pager','-o','json','--output-fields=MESSAGE'],capture_output=True,text=True,timeout=15)
    if p.returncode or len(p.stdout)>1000000: return []
    out=[]
    for line in p.stdout.splitlines():
        try:d=json.loads(line);m=d.get('MESSAGE','')
        except (ValueError,TypeError):continue
        if not isinstance(m,str):continue
        for prefix in ('HOLD:','FEATURE_EVIDENCE_HOLD '):
            if m.startswith(prefix) and m[len(prefix):] in CODES:out.append(m[len(prefix):])
        if m in CODES:out.append(m)
    return out[-6:]
def self_test():
    target='gemini-test';d={'configured_model':target,'core_model':target,'core_fallback':False,'paid_theme_models':{'g1':{'model':target,'fallback':False},'g2':{'model':'other','fallback':True}}}
    assert summarize_models(d,target)=={'configured_target':True,'core_target':True,'core_no_fallback':True,'paid_present':2,'paid_target':1,'paid_no_fallback':1}
    i={'id':'test'};p={'identity':i,'plan_sha256':'hash','phase':'confirmed','nonce':'NEVER_PRINT','samples':[{'done':45,'total':116,'stalled':True,'secret':'NEVER_PRINT'}]}
    assert summarize_checkpoint(p,i,'hash')=={'phase':'confirmed','done':45,'total':116,'stalled':True}
    for x in ({**p,'identity':{}},{**p,'phase':'SECRET'},{**p,'plan_sha256':'wrong'}):
        try:summarize_checkpoint(x,i,'hash')
        except ValueError:pass
        else:raise AssertionError('unsafe checkpoint')
    assert 'nonce' not in summarize_checkpoint(p,i,'hash')
    print('FEATURE_DIAGNOSTIC_SELF_TEST=6/6_PASS')
def main():
    need(os.geteuid()==0,'ROOT_REQUIRED')
    for p in (TOOLS,FEATURE,ROOT):
        s=p.lstat();need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&0o077,'UNSAFE_DIR')
    a=load(TOOLS/'auto.py',AUTO);l=load(TOOLS/'launcher.py',LAUNCHER)
    h=load(FEATURE/'feature_qa_handlers.py',HANDLERS);c=load(FEATURE/'feature_qa_contract.py',CONTRACT)
    for unit in ('judun-stage-feature-qa.service','judun-stage-feature-delivery.service','judun-stage-feature-qa.timer','judun-stage-feature-delivery.timer'):
        unit_status(unit)
        if unit.endswith('.service'):emit(unit=unit,recent_known_codes=log_codes(unit))
    with ExitStack() as s:
        try:
            a['existing_lock'](s,a['PULL']/'.lock');a['existing_lock'](s,a['STAGE']/'.lock');a['existing_lock'](s,ROOT/'qa.lock')
        except BlockingIOError:
            emit(status='BUSY_READONLY_DIAGNOSTIC_DEFERRED');return
        selected=a['snapshot'](a['STAGE'])
        commit=l['commit_of'](l['fetch'](l['POINTER'],2048));prefix=commit+'/staging/candidate'
        pub=secure(PUB,8192,False)
        with tempfile.TemporaryDirectory() as d:
            ident=l['verified'](l['fetch'](prefix+'.json',8192),l['fetch'](prefix+'.json.sig.b64',1024),pub,PIN,Path(d))
        tree=ident['source_tree_sha256'];need(selected[:2]==(ident['artifact_id'],tree),'STAGE_SELECTION')
        raw=secure(ROOT/(tree+'.receipt.json'),8192);path='main/ops/feature-qa-plans/'+tree
        plan=c['validate'](l['fetch'](path+'.json',8192),base64.b64decode(b''.join(l['fetch'](path+'.json.sig.b64',1024).split()),validate=True),pub,ident,raw)
        emit(status='SIGNED_FEATURE_PLAN_AND_NATIVE_RECEIPT',candidate_commit=commit,tree=tree,plan_sha256=plan['plan_sha256'],native_receipt_sha256=plan['native_receipt_sha256'])
        qa=h['module']();_,data,token=qa.read_env();qa.Client(token,'',ident).health()
        trace=h['verify_native'](qa,data,plan)
        emit(check='NATIVE_MODEL_TRACE_READONLY',**summarize_models(trace,plan['target_model']))
        for suffix in ('.feature110.json','.feature110.receipt.json','.feature-qa.receipt.json'):
            p=ROOT/(tree+suffix)
            if not os.path.lexists(p):emit(file=suffix,present=False);continue
            d=json.loads(secure(p))
            need(d.get('identity')==ident and d.get('plan_sha256')==plan['plan_sha256'],'FEATURE_STATE_IDENTITY')
            if suffix=='.feature110.json':emit(file=suffix,present=True,**summarize_checkpoint(d,ident,plan['plan_sha256']))
            else:emit(file=suffix,present=True,status='PASS' if d.get('status')=='PASS' else 'NOT_PASS')
        need(a['snapshot'](a['STAGE'])==selected and l['commit_of'](l['fetch'](l['POINTER'],2048))==commit,'STAGE_CHANGED')
        emit(status='READONLY_DIAGNOSTIC_COMPLETE_NOT_RELEASE_APPROVAL')
if __name__=='__main__':
    import sys
    if sys.argv[1:]==['--self-test']:self_test()
    elif not sys.argv[1:]:
        try:main()
        except Exception as e:
            msg=str(e);emit(status='HOLD',code=msg if msg in CODES else type(e).__name__);sys.exit(2)
    else:sys.exit(2)
