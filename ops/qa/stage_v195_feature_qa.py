#!/usr/bin/env python3
"""Exact v195 stage-only supplemental QA. Existing native case is read-only.
One new synthetic 110-row preview at most; no real payments or paid unlocks.
No service/config changes, no customer data, no credentials printed.
"""
import csv, fcntl, hashlib, http.client, importlib.util, io, json, os, pathlib, re, secrets, sqlite3, stat, time, uuid
from html.parser import HTMLParser
from datetime import datetime, timezone
TREE='36c9920d2bab3e66defca3d5da10c600a4188f4b887ae2206bf741e95de3a292'
EXPECTED={'version':'1.2.195','artifact_id':'JUDUN-1.2.195-COMPANY-PREVIEW-HYDROGEN-20261127','build_instance_id':'1.2.195-COMPANY-PREVIEW-HYDROGEN-20261127','source_tree_sha256':TREE,'count':98}
NATIVE_SHA='d9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568'
RECEIPT_SHA='bf30b904d9355dfee1d6199827f9d454515eed5881ef1dcbe9a5798d6df8af68'
TARGET='gemini-4-hydrogen'
NATIVE=pathlib.Path('/opt/judun-stage-qa-auto/native_qa.py')
ROOT=pathlib.Path('/var/lib/judun-stage-business-qa')
AREAS=('玄關','客廳','餐廳','廚房','主臥','次臥','書房','主浴','客浴','陽台','走道')
WORKS=(('拆除清運',1,'式',3500),('牆面批土',4,'坪',450),('牆面乳膠漆',4,'坪',650),('天花板油漆',3,'坪',700),('地坪保護',3,'坪',300),('插座更換',2,'個',700),('照明配線',2,'處',1200),('矽利康收邊',3,'米',250),('門框修補',1,'式',1600),('完工清潔',1,'式',2200))
ITEMS=[(a+n,q,u,p,q*p) for a in AREAS for n,q,u,p in WORKS]
def require(ok,code):
 if not ok:raise RuntimeError(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()
def pin_file(p,pin):
 st=p.lstat();require(stat.S_ISREG(st.st_mode) and st.st_uid==0 and not st.st_mode&0o022,'UNSAFE_PINNED_FILE');raw=p.read_bytes();require(sha(raw)==pin,'PIN_MISMATCH');return raw
def module():
 pin_file(NATIVE,NATIVE_SHA);spec=importlib.util.spec_from_file_location('native_qa',NATIVE);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class Markup(HTMLParser):
 def __init__(self,raw):super().__init__();self.ids={};self.links=[];self.nav=False;self.feed(raw)
 def handle_starttag(self,t,a):
  a=dict(a)
  if 'id' in a:self.ids[a['id']]=a
  if t=='body':self.role=a.get('data-intake-role')
  if t=='nav' and 'intakeNav' in a.get('class','').split():self.nav=True
  if t=='a' and self.nav:self.links.append(a.get('href'))
 def handle_endtag(self,t):
  if t=='nav':self.nav=False
def verify_markup(raw,role):
 m=Markup(raw);company=role=='company';require(getattr(m,'role',None)==role,'MARKUP_ROLE');require(('companyFields' if company else 'ownerFields') in m.ids,'MARKUP_FIELDS');require(('ownerFields' if company else 'companyFields') not in m.ids and 'adminSection' not in m.ids,'MARKUP_FOREIGN_FIELDS');require(('required' in m.ids.get('intakeSummary',{}))!=company,'MARKUP_SUMMARY');require(not company or m.links==['/'],'MARKUP_COMPANY_NAV');return True
def get_page(qa,token,path):
 require(path in ('/matching/?role=company','/matching/?role=owner'),'ROUTE_DENIED');c=http.client.HTTPConnection(qa.HOST,qa.PORT,timeout=15)
 try:
  c.request('GET',path,headers={'Host':qa.ORIGIN.split('://')[1],'Cookie':'judun_staging_access='+token,'Accept-Encoding':'identity','Cache-Control':'no-cache'});r=c.getresponse();raw=r.read(2000001);require(r.status==200 and len(raw)<=2000000,'MARKUP_HTTP');return raw.decode()
 finally:c.close()
def trace(data,job,email):
 with sqlite3.connect((data/'app_data.db').as_uri()+'?mode=ro',uri=True,timeout=5) as c:
  c.execute('PRAGMA query_only=ON');r=c.execute('SELECT tier,status,evaluated_data FROM jobs WHERE id=? AND contact_email=?',(job,email)).fetchone();require(r and '完成' in r[1],'SYNTHETIC_TRACE_CASE_MISSING');d=json.loads(r[2] or '{}');orders=c.execute('SELECT count(*) FROM payment_orders WHERE job_id=?',(job,)).fetchone()[0];require(orders==0,'UNEXPECTED_PAYMENT_ORDER')
 t=d.get('model_trace') or {};p=t.get('performance') or {};core=t.get('core_analysis') or {};paid=t.get('advanced_themes') or {};f=d.get('full_item_analysis') or {}
 def model(v):
  x=v.get('model','');return x if isinstance(x,str) and re.fullmatch(r'[A-Za-z0-9._-]{1,120}',x) else 'UNKNOWN'
 return {'tier':r[0],'configured_model':model({'model':t.get('configured_reasoning_model')}),'core_model':model(core),'core_fallback':core.get('fallback_used'),'paid_theme_models':{k:{'model':model(v),'fallback':v.get('fallback_used')} for k,v in paid.items() if k in {'g1','g2','g3','g4','g5'} and isinstance(v,dict)},'performance':{k:p[k] for k in ('core_model_ms','item_model_ms','preview_parallel_wall_ms','total_ms','all_item_count') if type(p.get(k)) is int},'items':{k:f[k] for k in ('expected','completed','pending') if type(f.get(k)) is int}}
def verify_native(qa,data):
 r=ROOT/(TREE+'.receipt.json');require(qa.valid_private(r) and sha(r.read_bytes())==RECEIPT_SHA,'NATIVE_RECEIPT_PIN');doc=json.loads(r.read_bytes());require(doc.get('identity')==EXPECTED and doc.get('status')=='PASS','NATIVE_RECEIPT_IDENTITY');s=ROOT/(TREE+'.json');require(qa.valid_private(s),'NATIVE_STATE_UNSAFE');d=json.loads(s.read_bytes());require(d.get('identity')==EXPECTED and str(uuid.UUID(d['job_id']))==d['job_id'] and re.fullmatch('[0-9a-f]{16}',d['nonce']),'NATIVE_STATE_IDENTITY');require(sha(d['job_id'].encode())[:16]==doc['case_fingerprint'],'NATIVE_CASE_PIN');return trace(data,d['job_id'],'judun-qa-'+d['nonce']+'@example.invalid')
def main():
 require(os.geteuid()==0,'ROOT_REQUIRED');os.umask(0o077);qa=module();require(len(ITEMS)==110 and len({x[0] for x in ITEMS})==110,'FIXTURE_ROWS');require(ROOT.is_dir() and not ROOT.is_symlink() and ROOT.stat().st_uid==0 and not ROOT.stat().st_mode&0o077,'QA_DIR_UNSAFE')
 fd=os.open(ROOT/'qa.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 env,data,token=qa.read_env();client=qa.Client(token,'',EXPECTED);client.health();native=verify_native(qa,data);print(json.dumps({'check':'EXISTING_NATIVE_MODEL_TRACE','result':native}),flush=True)
 require(native['configured_model']==TARGET and native['core_model']==TARGET and native['core_fallback'] is False,'MODEL_TARGET_NOT_PROVEN');require(len(native['paid_theme_models'])==5 and all(v['model']==TARGET and v['fallback'] is False for v in native['paid_theme_models'].values()),'PAID_THEME_TARGET_NOT_PROVEN')
 for role in ('company','owner'):verify_markup(get_page(qa,token,'/matching/?role='+role),role)
 print('STAGE_SERVER_MARKUP_PASS (not browser)',flush=True)
 path=ROOT/(TREE+'.feature110.json');out=ROOT/(TREE+'.feature110.receipt.json');
 if out.exists():
  require(qa.valid_private(out),'FEATURE_RECEIPT_UNSAFE');r=json.loads(out.read_bytes());require(r.get('identity')==EXPECTED,'FEATURE_RECEIPT_IDENTITY');print(json.dumps(r,ensure_ascii=False));return
 if path.exists():
  require(qa.valid_private(path),'FEATURE_STATE_UNSAFE');s=json.loads(path.read_bytes());require(s.get('identity')==EXPECTED and re.fullmatch('[0-9a-f]{16}',s['nonce']),'FEATURE_STATE_IDENTITY')
 else:s={'identity':EXPECTED,'nonce':secrets.token_hex(8),'phase':'new','samples':[]};qa.atom(path,s)
 def save(phase):s['phase']=phase;qa.atom(path,s)
 email='judun-feature110-'+s['nonce']+'@example.invalid';qa.ITEMS=ITEMS
 if s['phase']=='new':
  payload=qa.quote(s['nonce']);b='qa'+secrets.token_hex(16);part=(f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="feature110-{s["nonce"]}.csv"\r\nContent-Type: text/csv\r\n\r\n').encode()+payload+f'\r\n--{b}--\r\n'.encode();client.health();save('upload_pending');raw,_,_=client.call('/extract','POST',part,{'Content-Type':'multipart/form-data; boundary='+b});j=json.loads(raw)['job_id'];require(str(uuid.UUID(j))==j,'FEATURE_JOB_ID');s['job_id']=j;save('uploaded')
 require(s['phase'] not in ('upload_pending','confirm_pending'),'AMBIGUOUS_POST_NO_REPEAT');job=s['job_id'];require(str(uuid.UUID(job))==job,'FEATURE_JOB_ID')
 if s['phase']=='uploaded':
  x=qa.poll(lambda:client.j('/status-lite/'+job)[0],lambda x:x.get('status')=='待確認',420,'FEATURE_EXTRACT',lambda x:x.get('status')=='錯誤');rows=x['items'];require(qa.validate_rows(rows)==sum(x[-1] for x in ITEMS),'FEATURE_ROWS');client.health();s['confirmed_at']=time.time();save('confirm_pending');d,h=client.j('/confirm/'+job,'POST',{'items':rows,'email':email});require(d.get('job_id')==job and d.get('status')=='started','FEATURE_CONFIRM');client.capture(h,job);s['report_cookie']=client.report;save('confirmed')
 client.report=s['report_cookie'];require(s['phase']=='confirmed','FEATURE_PHASE');deadline=time.monotonic()+900
 while time.monotonic()<deadline:
  x=client.j('/status-lite/'+job)[0];p=x.get('analysis_progress') or {};done=p.get('done');total=p.get('total');sample={'at':time.time(),'done':done,'total':total,'stalled':bool(p.get('stalled'))}
  if total==116 and type(done) is int:
   require(0<=done<=116,'FEATURE_PROGRESS_RANGE');prev=[v for v in s['samples'] if v['total']==116];require(not prev or done>=prev[-1]['done'],'FEATURE_PROGRESS_REGRESSION');s['samples'].append(sample);qa.atom(path,s);print(json.dumps({'check':'FEATURE_PROGRESS','done':done,'total':total,'stalled':sample['stalled']}),flush=True)
  if '完成' in x.get('status',''):break
  require(x.get('status')!='錯誤','FEATURE_ANALYSIS_FAILED');time.sleep(8)
 else:raise RuntimeError('FEATURE_TIMEOUT_RESUME_SAME_CASE')
 d=trace(data,job,email);require(d['core_model']==TARGET and d['core_fallback'] is False and d['performance'].get('all_item_count')==110,'FEATURE_MODEL_OR_COUNT');require(d['items'].get('expected')==110 and d['items'].get('pending')==0,'FEATURE_ITEMS_INCOMPLETE');require(s['samples'] and s['samples'][-1]['done']==116,'FEATURE_FINAL_PROGRESS');client.health();elapsed=round(time.time()-s['confirmed_at'],3);r={'status':'PASS','identity':EXPECTED,'native_receipt_sha256':RECEIPT_SHA,'existing_native_trace':native,'feature_trace':d,'wall_seconds':elapsed,'samples':s['samples'],'server_markup':'PASS','browser':'NOT_RUN','fallback_fault_injection':'SEPARATE_OFFLINE','rollback':'SEPARATE','completed_at':now()};qa.atom(out,r);print(json.dumps(r,ensure_ascii=False),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  # Never print raw exceptions or private data. Only controlled diagnostic codes.
  msg=str(e);print('HOLD:'+ (msg if re.fullmatch('[A-Z0-9_]{3,100}',msg) else type(e).__name__),flush=True);raise SystemExit(2)
