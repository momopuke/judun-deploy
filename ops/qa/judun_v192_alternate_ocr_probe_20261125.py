#!/usr/bin/env python3
"""One bounded alternate-model probe of the existing failed v192 synthetic OCR job.
Requires the previously verified QA runner. No HTTP POST, DB writes or production access.
One synthetic provider call may be made under the existing stage worker identity.
"""
import ast, hashlib, json, os, pathlib, re, runpy, stat, subprocess, sys, uuid
PIN='d9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568'
APP='5d3aad579a564898ada9bbb389504be4f3c7a8f8fe3b5c85f8e377c74d5aa5c4'
WORKER='8e651f18956b551e733af45cbb295114443aeb6669701ddc06e774714cbf0e1f'

def digest(raw):return hashlib.sha256(raw).hexdigest()
def emit(**x):print(json.dumps(x,ensure_ascii=False),flush=True)
def require(ok,code):
    if not ok:raise RuntimeError(code)

def source_prompt(src):
    matches=[n.value.value for n in ast.walk(ast.parse(src)) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='extraction_prompt' for t in n.targets) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str)]
    require(len(matches)==1,'STOP_PROMPT_CONTRACT');return matches[0]

# stdout/stderr of the child are captured, never printed raw. Report only an
# allowlisted diagnostic; provider exception text can contain sensitive data.
CHILD=r'''
import json,os,sys,time,re
req=json.load(sys.stdin)
sys.path.insert(0,req['source'])
def say(code,**fields):print('JUDUN_OCR_PROBE '+json.dumps(dict(code=code,**fields)),flush=True)
def classify(e):
    s=str(e).lower(); t=type(e).__name__
    for pattern,code in [(r'api.key.invalid|api.key.not.valid|unauthenticated|\b401\b','PROVIDER_AUTH_INVALID'),(r'resource.exhausted|\b429\b|quota','PROVIDER_QUOTA_OR_RATE_LIMIT'),(r'\b404\b|not.found|model.*not.supported','PROVIDER_MODEL_NOT_FOUND'),(r'\b403\b|permission.denied.*api|permission_denied','PROVIDER_PERMISSION_DENIED'),(r'\b400\b|invalid.argument','PROVIDER_BAD_REQUEST'),(r'\b50[0234]\b|unavailable','PROVIDER_UNAVAILABLE'),(r'gemini_api_key missing','STAGE_PROVIDER_KEY_MISSING'),(r'no module named|modulenotfounderror','WORKER_IMPORT_FAILED'),(r'permissionerror|permission denied|read-only file system|unsafe shared lock','WORKER_FILESYSTEM_OR_LOCK_PERMISSION'),(r'capacity|host-wide','WORKER_CAPACITY_EXHAUSTED'),(r'deadline|timed out|timeout','WORKER_DEADLINE'),(r'empty ocr response','PROVIDER_EMPTY_RESPONSE'),(r'connection|network|certificate|ssl','WORKER_NETWORK_OR_TLS'),(r'eoferror|broken pipe|cannot pickle|pickling','WORKER_SPAWN_OR_IPC')]:
        if re.search(pattern,s):return code
    return {'PermissionError':'WORKER_FILESYSTEM_OR_LOCK_PERMISSION','TimeoutError':'WORKER_DEADLINE','EOFError':'WORKER_SPAWN_OR_IPC','ModuleNotFoundError':'WORKER_IMPORT_FAILED'}.get(t,'WORKER_OTHER_ERROR')
try:
    from ocr_spawn_worker import OCRRequest,run_request
    from ocr_budget import OCRJobBudget
    model=(os.getenv('GEMINI_LITE_MODEL',os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')).strip() or 'gemini-3.5-flash-lite')
    if not os.getenv('GEMINI_API_KEY'):say('STAGE_PROVIDER_KEY_MISSING');sys.exit(0)
    budget=OCRJobBudget(1);remaining=budget.reserve(0)
    deadline=min(budget.deadline,time.monotonic()+65)
    result=run_request(OCRRequest(content=req['text'].encode(),filename=req['filename'],mime='text/plain',model=model,prompt=req['prompt'],timeout_ms=max(1,int(min(remaining,60)*1000)),text_only=True),deadline=deadline,slots=max(1,min(4,int(os.getenv('JUDUN_OCR_HOST_SLOTS','2')))))
    from decimal import Decimal
    s=result.strip()
    if s.startswith('```json'):s=s[7:]
    elif s.startswith('```'):s=s[3:]
    if s.endswith('```'):s=s[:-3]
    try:x=json.loads(s.strip(),strict=False)
    except ValueError:say('PROVIDER_RESPONSE_NOT_JSON');sys.exit(0)
    rows=x if isinstance(x,list) else x.get('items',[]) if isinstance(x,dict) else []
    try:
        vals=[]
        for row in rows:
            name=row.get('項目',row.get('item',''))
            matches=[n for n,*_ in req['items'] if n in name]
            if len(matches)!=1:raise ValueError('unmatched')
            def num(a,b):return Decimal(str(row.get(a,row.get(b,''))).replace(',','').strip())
            vals.append((matches[0],num('數量','qty'),row.get('單位',row.get('unit','')),num('單價','unit_price'),num('總價','total_price')))
        exact=sorted(vals)==sorted(tuple(r) for r in req['items'])
    except (ValueError,TypeError,AttributeError,ArithmeticError):exact=False
    say('WORKER_PROVIDER_EXACT_PASS' if exact else 'PROVIDER_ROW_MISMATCH',rows=len(rows) if isinstance(rows,list) else 0,expected=4)
except Exception as e:say(classify(e))
'''
CODES={'PROVIDER_AUTH_INVALID','PROVIDER_QUOTA_OR_RATE_LIMIT','PROVIDER_MODEL_NOT_FOUND','PROVIDER_PERMISSION_DENIED','PROVIDER_BAD_REQUEST','PROVIDER_UNAVAILABLE','STAGE_PROVIDER_KEY_MISSING','WORKER_IMPORT_FAILED','WORKER_FILESYSTEM_OR_LOCK_PERMISSION','WORKER_CAPACITY_EXHAUSTED','WORKER_DEADLINE','PROVIDER_EMPTY_RESPONSE','WORKER_NETWORK_OR_TLS','WORKER_SPAWN_OR_IPC','WORKER_OTHER_ERROR','PROVIDER_RESPONSE_NOT_JSON','WORKER_PROVIDER_EXACT_PASS','PROVIDER_ROW_MISMATCH'}

def main():
    require(os.geteuid()==0,'STOP_ROOT_REQUIRED');require(len(sys.argv)==2,'STOP_RUNNER_PATH')
    runner=pathlib.Path(sys.argv[1]);require(digest(runner.read_bytes())==PIN,'STOP_RUNNER_HASH')
    q=runpy.run_path(str(runner),run_name='qa_probe_import')
    expected=dict(version='1.2.192',artifact_id='JUDUN-1.2.192-OCR-PROVIDER-RECOVERY-20261125',build_instance_id='1.2.192-OCR-PROVIDER-RECOVERY-20261125',source_tree_sha256='29a007c6329cfdca27aeda9952ca6e1ad904707ec2130f6b33a0d2785f5447e1',count=98);root=q['ROOT'];meta=root.lstat();require(stat.S_ISDIR(meta.st_mode) and meta.st_uid==0 and not meta.st_mode&0o077,'STOP_QA_ROOT')
    import fcntl
    lock=os.open(root/'qa.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    env,_,token=q['read_env']();c=q['Client'](token,'',expected);c.health()
    p=root/(expected['source_tree_sha256']+'.json');require(q['valid_private'](p),'STOP_QA_STATE')
    s=json.loads(p.read_text());require(s.get('identity')==expected and s.get('phase')=='uploaded','STOP_QA_PHASE');job=s['job_id'];require(str(uuid.UUID(job))==job,'STOP_JOB_ID')
    result=c.j('/status-lite/'+job)[0];require(result.get('status')=='錯誤','STOP_NOT_FAILED_OCR')
    nonce=s['nonce'];require(re.fullmatch('[a-f0-9]{16}',nonce),'STOP_QA_NONCE');payload=q['quote'](nonce)
    require(digest(payload)==s['checks']['upload']['sha256'],'STOP_SYNTHETIC_UPLOAD_HASH')
    pid=q['validate_unit'](q['unit_properties']());base=q['STAGE_BASE'];selected=(base/'current').resolve()
    app=selected/'app.py';worker=selected/'ocr_spawn_worker.py';require(digest(app.read_bytes())==APP and digest(worker.read_bytes())==WORKER,'STOP_SOURCE_HASH')
    prompt=source_prompt(app.read_text());fname='judun-qa-'+nonce+'.csv';text=f'檔名：{fname}\n以下是由文件安全擷取出的文字與表格內容：\n'+payload.decode('utf-8-sig')
    raw=(pathlib.Path('/proc')/str(pid)/'status').read_text();u=re.search(r'^Uid:\s+(\d+)\s+(\d+)',raw,re.M);g=re.search(r'^Gid:\s+(\d+)\s+(\d+)',raw,re.M);require(u and g and int(u[2])>0 and int(g[2])>0,'STOP_STAGE_IDENTITY')
    # No credential values in command line or output. The only credential passed
    # locally is the stage process's existing provider key, not its session/code.
    allow={'GEMINI_API_KEY','GEMINI_MODEL','GEMINI_LITE_MODEL','GEMINI_REASONING_MODEL','HTTP_PROXY','HTTPS_PROXY','NO_PROXY','http_proxy','https_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','HOME','LANG','TMPDIR'}
    childenv={k:v for k,v in env.items() if k in allow or k.startswith('JUDUN_OCR_')};childenv['PATH']='/usr/bin:/bin'
    require(q['validate_unit'](q['unit_properties']())==pid,'STOP_STAGE_PID_CHANGED')
    emit(check='EXISTING_SYNTHETIC_CASE',status='FAILED_OCR_CONFIRMED',upload_sha256=digest(payload),stage_identity='PASS',provider_key_present=bool(childenv.get('GEMINI_API_KEY')))
    if not childenv.get('GEMINI_API_KEY'):emit(check='OCR_PROBE',code='STAGE_PROVIDER_KEY_MISSING');return
    primary=(env.get('GEMINI_LITE_MODEL',env.get('GEMINI_MODEL','gemini-3.5-flash-lite')).strip() or 'gemini-3.5-flash-lite')
    alternate=env.get('GEMINI_REASONING_MODEL','gemini-3.8-flash').strip() or 'gemini-3.8-flash'
    require(primary!=alternate,'STOP_MODELS_IDENTICAL')
    require(all(re.fullmatch(r'[A-Za-z0-9._/-]{1,100}',m) for m in (primary,alternate)),'STOP_MODEL_FORMAT')
    emit(check='MODEL_COMPARISON',primary=primary,alternate=alternate)
    childenv['GEMINI_LITE_MODEL']=alternate
    # Single invocation, no server POST, same stage mount/net/ipc namespaces,
    # existing unprivileged UID/GID, actual pinned OCR worker and original prompt.
    args=['/usr/bin/nsenter','--target',str(pid),'--mount','--net','--ipc','--','/usr/bin/setpriv','--reuid',u[2],'--regid',g[2],'--clear-groups','--no-new-privs',str(base/'venv/bin/python'),'-I','-B','-c',CHILD]
    marker=root/(expected['source_tree_sha256']+'.alternate-probe-attempt')
    require(not os.path.lexists(marker),'STOP_ALTERNATE_PROBE_ALREADY_ATTEMPTED')
    fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        f.write('one synthetic provider attempt reserved\n');f.flush();os.fsync(f.fileno())
    try:r=subprocess.run(args,input=json.dumps(dict(source=str(selected),text=text,filename=fname,prompt=prompt,items=q['ITEMS']),ensure_ascii=False),text=True,capture_output=True,timeout=85,env=childenv)
    except subprocess.TimeoutExpired:emit(check='OCR_PROBE',code='PROBE_PROCESS_TIMEOUT');return
    lines=[l.removeprefix('JUDUN_OCR_PROBE ') for l in r.stdout.splitlines() if l.startswith('JUDUN_OCR_PROBE ')]
    if len(lines)!=1:
        emit(check='OCR_PROBE',code='PROBE_NAMESPACE_OR_EXEC_FAILED',exit_code=r.returncode);return
    d=json.loads(lines[0]);require(d.get('code') in CODES,'STOP_UNKNOWN_PROBE_RESULT');c.health()
    emit(check='OCR_PROBE',code=d['code'],rows=d.get('rows'),expected=d.get('expected'),stage_identity_after='PASS',new_jobs=0,production_modified=False)
if __name__=='__main__':
    try:main()
    except Exception as e:
        msg=str(e);emit(check='HOLD',error=msg if re.fullmatch(r'STOP_[A-Z0-9_]+',msg) else type(e).__name__);sys.exit(2)
