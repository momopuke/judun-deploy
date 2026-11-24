#!/usr/bin/env python3
"""Judun stage-only native business acceptance. No production requests or real payments.
Persist only one synthetic QA job per expected tree; no automatic retry of POSTs.
"""
import argparse, csv, datetime, decimal, fcntl, getpass, hashlib, http.client, io, json, os, pathlib, re, secrets, shutil, sqlite3, stat, subprocess, sys, time, uuid
from http.cookies import SimpleCookie

HOST='127.0.0.1'; PORT=8011
ORIGIN='https://judun-test.tony870490.chatgpt.site'
CODE_PIN='c6379c61ae1b63f9927a580aae48f3a0cf74a3b4413b0daa5cb9b4c4cf556ddf'
ROOT=pathlib.Path('/var/lib/judun-stage-business-qa')
DEFAULT={'version':'1.2.191','artifact_id':'JUDUN-1.2.191-PIPELINE-CANARY-20261124','build_instance_id':'1.2.191-PIPELINE-CANARY-20261124','source_tree_sha256':'141654ca761a07e3ec56cf8417403adfa69f4414098e890a860338532dbe1fd8','count':98}
DATA_DIRS={pathlib.Path(x) for x in ('/var/lib/judun-staging','/var/lib/private/judun-staging','/var/lib/judun-staging/state')}
ITEMS=[('拆除工程',2,'式',3500,7000),('水泥粉光',8,'坪',1200,9600),('防水工程',5,'坪',1800,9000),('乳膠漆',10,'坪',650,6500)]
THEMES={'g1','g2','g3','g4','g5'}
class Stop(Exception):pass

def check(x,code):
    if not x:raise Stop(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def emit(label, **kwargs):print(json.dumps({'check':label,**kwargs},ensure_ascii=False),flush=True)
def atom(p,obj):
    tmp=p.with_name(p.name+'.tmp'); fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:json.dump(obj,f,ensure_ascii=False,sort_keys=True);f.flush();os.fsync(f.fileno())
    os.replace(tmp,p)

def valid_private(p):
    st=p.lstat();return stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and not(st.st_mode&0o077)

def verify_identity(b,d,r,e):
    check(b.get('payment_mode')=='test_unlock','STOP_WRONG_PAYMENT_MODE')
    for x in (b,d):
        check(x.get('status')=='ok' and str(x.get('version','')).removeprefix('v')==e['version'] and all(x.get(k)==e[k] for k in ('artifact_id','build_instance_id','source_tree_sha256')),'STOP_STAGE_IDENTITY_DRIFT')
    check(b.get('manifest_status')=='ok' and d.get('deep_verified') is True and d.get('files_verified')==d.get('manifest_file_count')==e['count'] and d.get('mismatch_count')==0 and r.get('status')=='ready' and str(r.get('version','')).removeprefix('v')==e['version'],'STOP_STAGE_DEEP_OR_READY')

# The already-installed launcher was attested on the VPS in issue #22,
# comment 7078212631 (immutable Git blob, main PR34). It sets the stage
# environment inside Python after exec; /proc/PID/environ is initial only.
STAGE_BASE=pathlib.Path('/srv/judun-staging')
LAUNCHER_BLOB='3cc8edca2246a13b94d70f8bf9237ed558bd6815'
REQUIRED_STAGE={'JUDUN_STAGING':'1','ENABLE_TEST_MODE':'true','COOP_MODE':'simulation','APP_DATA_DIR':'/var/lib/judun-staging','PUBLIC_BASE_URL':ORIGIN}
LIVE_KEYS=('ECPAY_MERCHANT_ID','ECPAY_HASH_KEY','ECPAY_HASH_IV','JUDUN_ECPAY_LIVE_PROVISIONED')

def launcher_blob(raw):
    return hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()

def stage_environment(env):
    # Only called after attesting the exact isolated launcher and listener.
    # Explicitly conflicting initial values are never overwritten.
    check(not any(env.get(k) for k in LIVE_KEYS),'STOP_LIVE_PAYMENT_CONFIG')
    for k,v in REQUIRED_STAGE.items():
        x=env.get(k,'')
        if k=='APP_DATA_DIR':
            check(not x or pathlib.Path(x) in DATA_DIRS,'STOP_STAGE_DATA_DIR')
        else:
            check(not x or x==v,'STOP_STAGE_ENV_CONFLICT_'+k)
    token=env.get('JUDUN_STAGING_SESSION','')
    check(len(token)>=40 and not re.search(r'[\r\n;]',token),'STOP_STAGE_SESSION_INVALID')
    return dict(env,**REQUIRED_STAGE),token

def unit_properties():
    p=subprocess.run(['systemctl','show','--property=ActiveState,MainPID,DynamicUser,InaccessiblePaths,PartOf,ExecStart','judun-staging-isolated.service'],capture_output=True,text=True,timeout=8,check=True)
    return dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)

def validate_unit(props):
    check(props.get('ActiveState')=='active' and props.get('DynamicUser')=='yes' and not props.get('PartOf'),'STOP_STAGE_UNIT_NOT_ISOLATED')
    check('/var/www/advisor' in [x.lstrip('-+') for x in props.get('InaccessiblePaths','').split()],'STOP_PRODUCTION_NOT_INACCESSIBLE')
    check(str(STAGE_BASE/'venv/bin/python') in props.get('ExecStart','') and str(STAGE_BASE/'staging_release.py') in props.get('ExecStart',''),'STOP_STAGE_UNIT_COMMAND')
    v=props.get('MainPID','');check(v.isdigit() and int(v)>1,'STOP_STAGE_MAINPID');return int(v)

def validate_listener(raw,pid):
    lines=[x for x in raw.splitlines() if x.strip()]
    check(len(lines)==1,'STOP_STAGE_LISTENER_COUNT')
    fields=lines[0].split();check(len(fields)>=5 and fields[3]=='127.0.0.1:8011','STOP_STAGE_LISTENER_ADDRESS')
    check(set(re.findall(r'pid=(\d+)',lines[0]))=={str(pid)},'STOP_STAGE_LISTENER_PID')

def read_env():
    props=unit_properties();pid=validate_unit(props)
    proc=pathlib.Path('/proc')/str(pid)
    cmd=[v.decode() for v in (proc/'cmdline').read_bytes().split(b'\0') if v]
    check(cmd==[str(STAGE_BASE/'venv/bin/python'),'-I','-B',str(STAGE_BASE/'staging_release.py'),'serve'],'STOP_STAGE_LAUNCHER_COMMAND')
    uid=re.search(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',(proc/'status').read_text(),re.M)
    check(uid and all(int(x)>0 for x in uid.groups()),'STOP_STAGE_PROCESS_ROOT')
    for path in (STAGE_BASE,STAGE_BASE/'staging_release.py'):
        st=path.lstat();check(st.st_uid==0 and not (st.st_mode&0o022) and not path.is_symlink(),'STOP_STAGE_LAUNCHER_OWNER')
    source=STAGE_BASE/'staging_release.py';check(source.is_file() and source.stat().st_size<512000,'STOP_STAGE_LAUNCHER_FILE')
    actual=launcher_blob(source.read_bytes());check(actual==LAUNCHER_BLOB,'STOP_STAGE_LAUNCHER_BLOB_'+actual)
    p=subprocess.run(['ss','-H','-lntp','sport = :8011'],capture_output=True,text=True,timeout=8,check=True)
    validate_listener(p.stdout,pid)
    current=STAGE_BASE/'current';check(current.is_symlink(),'STOP_STAGE_CURRENT_NOT_LINK')
    selected=current.resolve();check(selected.parent==(STAGE_BASE/'releases').resolve() and (selected/'app.py').is_file() and (selected/'DEPLOY_MANIFEST.json').is_file(),'STOP_STAGE_CURRENT_PATH')
    raw=(proc/'environ').read_bytes()
    initial={k.decode():v.decode(errors='replace') for x in raw.split(b'\0') if b'=' in x for k,v in [x.split(b'=',1)]}
    env,token=stage_environment(initial)
    data=pathlib.Path(env['APP_DATA_DIR']).resolve();check(data in DATA_DIRS,'STOP_STAGE_DATA_DIR')
    check((data/'app_data.db').is_file() and not (data/'app_data.db').is_symlink(),'STOP_STAGE_DB_PATH')
    check(validate_unit(unit_properties())==pid,'STOP_STAGE_PID_CHANGED')
    emit('STAGE_LAUNCHER_ATTESTED',status='PASS',launcher_blob=actual)
    return env,data,token

def stage_code(env,remember):
    p=ROOT/'test-code'; values=[env.get('TEST_PAYMENT_CODE',''),env.get('JUDUN_QA_TEST_CODE','')]
    if p.exists():check(valid_private(p),'STOP_UNSAFE_STAGE_CODE_FILE');values.append(p.read_text().strip())
    for code in values:
        if code and sha(code.encode())==CODE_PIN:
            if remember and not p.exists():
                fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                with os.fdopen(fd,'w') as f:f.write(code+'\n');f.flush();os.fsync(f.fileno())
            return code
    try:
        with open('/dev/tty','r+') as tty:code=getpass.getpass('Stage-only test code (hidden; no production password): ',stream=tty).strip()
    except (OSError,EOFError):raise Stop('STOP_STAGE_TEST_CODE_REQUIRED')
    check(sha(code.encode())==CODE_PIN,'STOP_STAGE_TEST_CODE_INVALID')
    if remember:
        fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as f:f.write(code+'\n');f.flush();os.fsync(f.fileno())
    return code

class Client:
    def __init__(self,token,code,expected):self.token=token;self.code=code;self.expected=expected;self.report={}
    def call(self,path,method='GET',body=None,headers=None,anon=False,expect=(200,),limit=24_000_000):
        check(path.startswith('/') and not path.startswith('//') and '\n' not in path and '\r' not in path,'STOP_UNSAFE_PATH')
        check(bool(re.fullmatch(r'/(?:health/(?:build|artifact\?deep=true|ready)|extract|(?:status-lite|status|confirm|download|download-highlight|recover-unlock)/[0-9a-f-]{36}|unlock/(?:basic|promax)/[0-9a-f-]{36}|print-jobs/[0-9a-f]{64}(?:/file)?)',path)),'STOP_ROUTE_NOT_ALLOWED')
        h={'Host':ORIGIN.split('://')[1],'Origin':ORIGIN,'Cache-Control':'no-cache','Accept-Encoding':'identity'}
        if not anon:h['Cookie']='; '.join([f'judun_staging_access={self.token}']+[f'{k}={v}' for k,v in self.report.items()])
        if headers:h.update(headers)
        c=http.client.HTTPConnection(HOST,PORT,timeout=35)
        try:
            c.request(method,path,body=body,headers=h);r=c.getresponse();raw=r.read(limit+1);status=r.status;rh=r.getheaders()
        finally:c.close()
        check(len(raw)<=limit,'STOP_RESPONSE_TOO_LARGE')
        check(status in expect,f'STOP_HTTP_{status}_{method}_{path.split("/")[1]}')
        return raw,rh,status
    def j(self,path,method='GET',obj=None,headers=None,**kw):
        h=dict(headers or {});body=None
        if obj is not None:body=json.dumps(obj,ensure_ascii=False).encode();h['Content-Type']='application/json'
        raw,rh,status=self.call(path,method,body,h,**kw)
        x=json.loads(raw);check(isinstance(x,dict),'STOP_JSON_SHAPE');return x,rh
    def health(self):verify_identity(*(self.j(p)[0] for p in ('/health/build','/health/artifact?deep=true','/health/ready')),self.expected)
    def capture(self,headers,job):
        name='jd_access_'+re.sub(r'[^A-Za-z0-9]','',job)[:16]
        for k,v in headers:
            if k.lower()=='set-cookie':
                c=SimpleCookie();c.load(v)
                if name in c:
                    val=c[name].value;check(re.fullmatch(r'[A-Za-z0-9_-]{20,100}',val),'STOP_REPORT_COOKIE_FORMAT');self.report={name:val};return
        raise Stop('STOP_REPORT_COOKIE_MISSING')

def quote(nonce):
    f=io.StringIO();w=csv.writer(f,lineterminator='\n');w.writerow(['項目','數量','單位','單價','總價','備註'])
    for name,q,u,p,t in ITEMS:w.writerow([name,q,u,p,t,'QA-'+nonce])
    return f.getvalue().encode('utf-8-sig')

def validate_rows(rows):
    check(isinstance(rows,list) and len(rows)==len(ITEMS),'STOP_EXTRACT_COUNT')
    def field(r,*ks):return next((r[k] for k in ks if k in r),None)
    def num(v):return decimal.Decimal(str(v).replace(',','').replace('NT$','').replace('元','').strip())
    got=[]
    for r in rows:
        check(isinstance(r,dict),'STOP_EXTRACT_ROW_SHAPE')
        label=str(field(r,'項目','item') or '')
        matches=[name for name,*_ in ITEMS if name in label]
        check(len(matches)==1,'STOP_EXTRACT_ITEM_NAME')
        try:got.append((matches[0],num(field(r,'數量','qty')),str(field(r,'單位','unit')).strip(),num(field(r,'單價','unit_price')),num(field(r,'總價','original_price'))))
        except (ValueError,decimal.InvalidOperation):raise Stop('STOP_EXTRACT_NUMERIC')
    check(sorted(got)==sorted(ITEMS),'STOP_EXTRACT_AMOUNT_OR_UNIT_MISMATCH')
    return sum(t for _,_,_,_,t in ITEMS)

def score_ok(x):
    try:return decimal.Decimal(str(x.get('risk_score')).split('/')[0])==0 and str(x.get('risk_score')).endswith('/10') and x.get('risk_provisional') is True
    except (decimal.InvalidOperation,ValueError):return False

def poll(get,done,timeout,label,failed=None):
    end=time.monotonic()+timeout;last=None
    while time.monotonic()<end:
        try:x=get()
        except (OSError,http.client.HTTPException,TimeoutError):time.sleep(5);continue
        if done(x):return x
        if failed and failed(x):raise Stop('STOP_'+label+'_FAILED')
        state=str(x.get('status',''))[:35]
        if state!=last:emit(label,status=state);last=state
        time.sleep(8)
    raise Stop('STOP_'+label+'_TIMEOUT_RESUME_SAME_CASE')

def verify_saved(data,job,email):
    db=data/'app_data.db';check(db.is_file() and not db.is_symlink(),'STOP_STAGE_DB_PATH')
    with sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5) as c:
        c.execute('PRAGMA query_only=ON')
        r=c.execute('SELECT tier,status,evaluated_data,project_profile FROM jobs WHERE id=? AND contact_email=?',(job,email)).fetchone()
        check(r is not None and r[0]=='promax' and '完成' in r[1] and not json.loads(r[3] or '{}').get('staging_sample'),'STOP_NATIVE_CASE_IDENTITY')
        ed=json.loads(r[2] or '{}');guides=ed.get('advanced_guides') or {}
        a=ed.get('risk_assessment') or {}; amount=next((f for f in a.get('factors',[]) if f.get('code')=='amounts'),{})
        check(a.get('provisional') is True and amount.get('checked_count')==4 and not amount.get('mismatches') and decimal.Decimal(str(amount.get('points')))==0,'STOP_PERSISTED_SCORE_EVIDENCE')
        check(all(isinstance(guides.get(k),str) and guides[k].strip() for k in THEMES),'STOP_PROMAX_GUIDES_INCOMPLETE')
        mail=dict(c.execute('SELECT kind,state FROM email_outbox WHERE job_id=? AND recipient=?',(job,email)).fetchall())
        orders=c.execute('SELECT COUNT(*) FROM payment_orders WHERE job_id=?',(job,)).fetchone()[0]
    check(orders==0,'STOP_UNEXPECTED_PAYMENT_ORDER')
    # test_unlock intentionally creates no paid orders; paid notice requires a
    # verified persisted PaymentOrder. Missing paid notices are not a sandbox failure.
    check(not any(k in mail for k in ('paid_basic','paid_promax')),'STOP_PAID_NOTICE_WITHOUT_ORDER')
    return {'themes':sorted(THEMES),'test_mail':{'free':mail.get('free','missing'),'paid_basic':'NOT_APPLICABLE_TEST_UNLOCK','paid_promax':'NOT_APPLICABLE_TEST_UNLOCK'},'real_payment_orders':orders}

def pdf_key(raw):
    s=raw.decode('utf-8',errors='replace');m=re.search(r'/print-jobs/([0-9a-f]{64})/file',s) or re.search(r'const key\s*=\s*"([0-9a-f]{64})"',s)
    check(m is not None,'STOP_PDF_TASK_KEY');return m[1]

def get_pdf(c,job,kind,tree):
    raw,_,_=c.call('/download'+('-highlight' if kind=='highlight' else '')+'/'+job)
    k=pdf_key(raw);poll(lambda:c.j('/print-jobs/'+k)[0],lambda x:x.get('status')=='complete',240,'PDF_'+kind.upper(),lambda x:x.get('status')=='failed')
    raw,_,_=c.call('/print-jobs/'+k+'/file');check(raw.startswith(b'%PDF-') and b'%%EOF' in raw[-2048:] and len(raw)>1024,'STOP_PDF_INVALID')
    p=ROOT/(tree+'-'+kind+'.pdf');fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:f.write(raw);f.flush();os.fsync(f.fileno())
    result={'sha256':sha(raw),'bytes':len(raw),'visual_review':'NOT_RUN'}
    if shutil.which('pdfinfo'):
        r=subprocess.run(['pdfinfo',str(p)],capture_output=True,text=True,timeout=20);m=re.search(r'^Pages:\s+(\d+)',r.stdout,re.M)
        check(r.returncode==0 and m and int(m[1])>0,'STOP_PDF_PAGE_PARSE');result['pages']=int(m[1])
    else:result['pages']='NOT_VERIFIED_PDFINFO_UNAVAILABLE'
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--remember-stage-code',action='store_true');p.add_argument('--version',default=DEFAULT['version']);p.add_argument('--artifact',default=DEFAULT['artifact_id']);p.add_argument('--build',default=DEFAULT['build_instance_id']);p.add_argument('--tree',default=DEFAULT['source_tree_sha256']);p.add_argument('--count',type=int,default=98);a=p.parse_args()
    check(os.geteuid()==0,'STOP_ROOT_REQUIRED');check(bool(re.fullmatch(r'[a-f0-9]{64}',a.tree)) and 1<=a.count<=2000,'STOP_EXPECTED_IDENTITY_FORMAT')
    expected=dict(version=a.version,artifact_id=a.artifact,build_instance_id=a.build,source_tree_sha256=a.tree,count=a.count)
    os.umask(0o077);ROOT.mkdir(mode=0o700,exist_ok=True);st=ROOT.lstat();check(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not(st.st_mode&0o077),'STOP_QA_DIR_UNSAFE')
    lock=os.open(ROOT/'qa.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    env,data,token=read_env(); c=Client(token,'',expected);c.health();emit('EXACT_STAGE_IDENTITY',status='PASS',expected=expected)
    statep=ROOT/(a.tree+'.json');receiptp=ROOT/(a.tree+'.receipt.json')
    if receiptp.exists():
        check(valid_private(receiptp),'STOP_RECEIPT_FILE_UNSAFE');existing=json.loads(receiptp.read_text());check(existing.get('identity')==expected and existing.get('status')=='PASS','STOP_RECEIPT_IDENTITY');print(json.dumps(existing,ensure_ascii=False,indent=2));return
    if statep.exists():check(valid_private(statep),'STOP_STATE_FILE_UNSAFE');s=json.loads(statep.read_text());check(s.get('identity')==expected,'STOP_STATE_IDENTITY')
    else:s={'identity':expected,'nonce':secrets.token_hex(8),'phase':'new','checks':{},'created_at':now()};atom(statep,s)
    # Require the valid stage-only code before spending AI resources.
    c.code=stage_code(env,a.remember_stage_code)
    email='judun-qa-'+s['nonce']+'@example.invalid';payload=quote(s['nonce'])
    def save(phase):s['phase']=phase;atom(statep,s)
    def passcheck(k,**v):s['checks'][k]={'status':'PASS',**v};atom(statep,s);emit(k,status='PASS',**v)
    if s['phase']=='new':
        c.health();save('upload_pending');b='qa'+secrets.token_hex(16);part=(f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="judun-qa-{s["nonce"]}.csv"\r\nContent-Type: text/csv\r\n\r\n').encode()+payload+f'\r\n--{b}--\r\n'.encode();raw,_,_=c.call('/extract','POST',part,{'Content-Type':'multipart/form-data; boundary='+b});j=json.loads(raw).get('job_id');check(str(uuid.UUID(j))==j,'STOP_JOB_ID');s['job_id']=j;passcheck('upload',sha256=sha(payload));save('uploaded')
    check(s['phase']!='upload_pending','STOP_AMBIGUOUS_UPLOAD_NO_AUTOMATIC_RETRY');job=s['job_id'];check(str(uuid.UUID(job))==job,'STOP_JOB_ID')
    if s.get('report_cookie'):c.report=s['report_cookie']
    if s['phase']=='uploaded':
        x=poll(lambda:c.j('/status-lite/'+job)[0],lambda x:x.get('status')=='待確認',300,'EXTRACTION',lambda x:x.get('status')=='錯誤');rows=x.get('items');total=validate_rows(rows);passcheck('extract',rows=4,total=total)
        c.health();save('confirm_pending');d,headers=c.j('/confirm/'+job,'POST',{'items':rows,'email':email});check(d.get('job_id')==job and d.get('status')=='started','STOP_CONFIRM_RESPONSE');c.capture(headers,job);s['report_cookie']=c.report;save('confirmed')
    check(s['phase']!='confirm_pending','STOP_AMBIGUOUS_CONFIRM_NO_AUTOMATIC_RETRY');check(bool(c.report),'STOP_REPORT_SESSION_MISSING')
    status=lambda:c.j('/status/'+job)[0]
    if s['phase']=='confirmed':
        d=poll(status,lambda x:'完成' in x.get('status','') and x.get('tier')=='free' and bool(x.get('report')),420,'FREE',lambda x:x.get('status')=='錯誤');check(score_ok(d),'STOP_FIXED_SCORE_MISMATCH');c.call('/status/'+job,anon=True,expect=(401,));passcheck('quote_scoring',risk_score=d.get('risk_score'),provisional=True,anonymous_rejected=True);save('free_done')
    for tier,before,after in [('basic','free_done','basic_done'),('promax','basic_done','promax_done')]:
        pending=tier+'_pending'
        if s['phase']==before:
            c.health();save(pending);d,_=c.j('/unlock/'+tier+'/'+job,'POST',headers={'X-Test-Payment-Code':c.code});check(d.get('status') in ('started','already_unlocked'),'STOP_UNLOCK_RESPONSE')
        if s['phase']==pending:
            def terminal(x):return x.get('tier')==tier and '完成' in x.get('status','') and (x.get('unlock_task') or {}).get('state') in ('completed','partial') and bool(x.get('report'))
            def failed(x):return x.get('status')=='錯誤' or (x.get('unlock_task') or {}).get('state')=='failed'
            d=poll(status,terminal,600,tier.upper(),failed)
            if (d.get('unlock_task') or {}).get('state')=='partial':
                # Only a native missing-content continuation; never repeat unlock/payment.
                marker='recover_'+tier;check(not s.get(marker),'STOP_PARTIAL_AFTER_ONE_RECOVERY');c.health();s[marker]=True;atom(statep,s)
                result,_=c.j('/recover-unlock/'+job,'POST');check(result.get('status') in ('started','running','completed'),'STOP_RECOVERY_RESPONSE')
                d=poll(status,lambda x:terminal(x) and (x.get('unlock_task') or {}).get('state')=='completed',600,tier.upper()+'_RECOVERY',failed)
            check(score_ok(d),'STOP_SCORE_DRIFT_AFTER_UNLOCK');passcheck(tier,unlock_state='completed');save(after)
    check(s['phase']=='promax_done','STOP_UNEXPECTED_PHASE')
    saved=poll(lambda:verify_saved(data,job,email),lambda x:x['test_mail']['free']=='sent',90,'FREE_MAIL');passcheck('native_promax_and_mail',**saved)
    for k in ('full','highlight'):
        if 'pdf_'+k not in s['checks']:passcheck('pdf_'+k,**get_pdf(c,job,k,a.tree))
    c.health();receipt={'schema':'judun.stage-native-business-qa.v1','status':'PASS','identity':expected,'case_fingerprint':sha(job.encode())[:16],'checks':s['checks'],'completed_at':now(),'release_gate':'HOLD_PENDING_INDEPENDENT_PDF_VISUAL_ROLLBACK_AND_PRODUCTION_SIGNING','scope':'synthetic_stage_only; PDF structure validation; visual review and migration rollback separate; test_unlock has no paid order or paid-mail test'};atom(receiptp,receipt);print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except Stop as e:emit('HOLD',error=str(e));sys.exit(2)
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,http.client.HTTPException,subprocess.SubprocessError) as e:emit('HOLD',error=type(e).__name__);sys.exit(3)
