"""Bounded feature receipt transport and independent release-review boundary.
No service changes, no production credentials or signing key retrieval.
"""
import hashlib,json,re,math,os,stat,subprocess,tempfile
from pathlib import Path
HEX=re.compile(r'[0-9a-f]{64}\Z')
ORIGINAL_PIN='17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'
RECIPIENT_PIN='f328e4787ba44d6c8a38cfec942f0b5b8f3d8f22312fbb22cbb6ea4a5597f27d'
CHECKS={'vendor_markup','native_model_trace','preview_110'}
REVIEW_CHECKS={'live_browser','fresh_core_api','paid_api','preview_budget','performance_comparison','fallback','rollback','pdf_visual'}
MAX=262144

def need(ok,code):
    if not ok: raise ValueError(code)
def sha(b):return hashlib.sha256(b).hexdigest()
def hash_ok(s):return type(s) is str and bool(HEX.fullmatch(s))
def json_strict(raw):
    need(type(raw) is bytes and 0<len(raw)<=MAX,'JSON_SIZE')
    def pairs(xs):
        d=dict(xs);need(len(d)==len(xs),'DUPLICATE_KEY');return d
    def bad(_):raise ValueError('NONFINITE_JSON')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
def identity(i):
    need(type(i) is dict and set(i)=={'version','artifact_id','build_instance_id','source_tree_sha256','count'},'IDENTITY_FIELDS')
    v=i['version'];need(type(v) is str and re.fullmatch(r'1\.2\.[0-9]+',v),'VERSION')
    for k,p in [('artifact_id','JUDUN-'+v+'-'),('build_instance_id',v+'-')]:
        s=i[k];need(type(s) is str and s.startswith(p) and re.fullmatch(r'[A-Za-z0-9._-]{1,160}',s),'IDENTITY_FORMAT')
    need(hash_ok(i['source_tree_sha256']) and type(i['count']) is int and 1<=i['count']<=2000,'IDENTITY_VALUES');return i

def verify_receipt(raw,plan,native_hash):
    r=json_strict(raw);need(type(r) is dict and set(r)=={'schema','status','identity','plan_sha256','native_receipt_sha256','checks','release_gate','browser','rollback','completed_at'},'RECEIPT_FIELDS')
    need(r['schema']=='judun.feature-qa-receipt.v1' and r['status']=='PASS' and r['release_gate']=='HOLD_PENDING_INDEPENDENT_REVIEW','RECEIPT_STATUS')
    need(identity(r['identity'])==plan['identity'] and r['plan_sha256']==plan['plan_sha256'] and r['native_receipt_sha256']==native_hash==plan['native_receipt_sha256'],'RECEIPT_BINDING')
    need(hash_ok(native_hash) and hash_ok(r['plan_sha256']),'RECEIPT_HASH')
    need(r['browser']=='NOT_RUN' and r['rollback']=='NOT_RUN','RECEIPT_SCOPE')
    need(type(r['checks']) is dict and set(r['checks'])==set(plan['checks']) and 0<len(r['checks']) and set(r['checks'])<=CHECKS,'RECEIPT_CHECKS')
    return {'identity':r['identity'],'plan_sha256':r['plan_sha256'],'native_receipt_sha256':native_hash,'feature_receipt_sha256':sha(raw),'feature_qa_status':'EVIDENCE_READY_NOT_RELEASE_APPROVAL'}

def summarize_live(proof,build):
    """Call only after existing OIDC authentication and native summary decoration."""
    pending={'feature_qa_status':'PENDING','feature_receipt_sha256':'','feature_plan_sha256':''}
    try:
        i=identity(proof['identity']);need(proof['feature_qa_status']=='EVIDENCE_READY_NOT_RELEASE_APPROVAL','FEATURE_STATUS')
        need(build.get('payment_mode')=='test_unlock' and build.get('status')=='ok' and build.get('manifest_status')=='ok','STAGE_NOT_READY')
        need(str(build.get('version','')).removeprefix('v')==i['version'] and all(build.get(k)==i[k] for k in ('artifact_id','build_instance_id','source_tree_sha256')),'STALE_FEATURE')
        need(build.get('native_qa_status')=='PASS' and build.get('native_qa_receipt_sha256')==proof['native_receipt_sha256'] and type(build.get('native_qa_file_count')) is int and build['native_qa_file_count']==i['count'],'NATIVE_MISMATCH')
        need(all(hash_ok(proof[k]) for k in ('feature_receipt_sha256','plan_sha256','native_receipt_sha256')),'FEATURE_HASH')
        return {'feature_qa_status':proof['feature_qa_status'],'feature_receipt_sha256':proof['feature_receipt_sha256'],'feature_plan_sha256':proof['plan_sha256']}
    except (KeyError,ValueError,TypeError,AttributeError):return pending

def stable_attestation(first,second,proof):
    a=summarize_live(proof,first);b=summarize_live(proof,second)
    need(a==b and a['feature_qa_status']=='EVIDENCE_READY_NOT_RELEASE_APPROVAL','OIDC_FEATURE_PENDING_OR_CHANGED')
    for x in (first,second):
        need(all(x.get(k)==v for k,v in a.items()),'OIDC_FEATURE_HASH_MISMATCH')
    return a

def openssl(args,raw):
    p=subprocess.run(['openssl',*args],input=raw,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    need(p.returncode==0 and 0<len(p.stdout)<=MAX+65536,'CRYPTO_OPERATION');return p.stdout

def encrypt(raw,proof,cert,pin=RECIPIENT_PIN):
    need(sha(raw)==proof['feature_receipt_sha256'],'RAW_MISMATCH');der=openssl(['x509','-outform','DER'],cert);need(sha(der)==pin,'RECIPIENT_PIN')
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/'cert.pem';p.write_bytes(cert)
        blob=openssl(['cms','-encrypt','-binary','-aes-256-cbc','-outform','DER',str(p)],raw)
    meta={'schema':'judun.feature-qa-cms.v1','tree':proof['identity']['source_tree_sha256'],'native_receipt_sha256':proof['native_receipt_sha256'],'feature_receipt_sha256':proof['feature_receipt_sha256'],'plan_sha256':proof['plan_sha256'],'ciphertext_sha256':sha(blob),'ciphertext_bytes':len(blob),'recipient_cert_der_sha256':pin}
    return blob,meta

def receive(blob,meta,plan,proof,first,second,cert,key,pin=RECIPIENT_PIN):
    stable_attestation(first,second,proof)
    need(set(meta)=={'schema','tree','native_receipt_sha256','feature_receipt_sha256','plan_sha256','ciphertext_sha256','ciphertext_bytes','recipient_cert_der_sha256'} and meta['schema']=='judun.feature-qa-cms.v1','ENVELOPE_FIELDS')
    need(meta['tree']==proof['identity']['source_tree_sha256'] and all(meta[k]==proof[k] for k in ('native_receipt_sha256','feature_receipt_sha256','plan_sha256')),'ENVELOPE_BINDING')
    need(type(meta['ciphertext_bytes']) is int and 0<len(blob)<=MAX+65536 and len(blob)==meta['ciphertext_bytes'] and sha(blob)==meta['ciphertext_sha256'],'CIPHERTEXT_HASH')
    need(meta['recipient_cert_der_sha256']==pin==sha(openssl(['x509','-outform','DER'],Path(cert).read_bytes())),'RECIPIENT_PIN')
    st=Path(key).lstat();need(stat.S_ISREG(st.st_mode) and not st.st_mode&0o077,'KEY_MODE')
    raw=openssl(['cms','-decrypt','-binary','-inform','DER','-recip',str(cert),'-inkey',str(key)],blob)
    need(verify_receipt(raw,plan,proof['native_receipt_sha256'])==proof,'DECRYPTED_RECEIPT_MISMATCH');return raw

def verify_review(raw,sig,pub,proof,acceptance_sha,first,second,pin=ORIGINAL_PIN):
    """Only a separate original-signer approval with exact evidence can permit release.
    The feature runner cannot create this record. Never signs or changes a release.
    """
    stable_attestation(first,second,proof)
    need(sha(pub)==pin and len(sig)==64,'REVIEW_SIGNER_PIN')
    with tempfile.TemporaryDirectory() as d:
        d=Path(d)
        for n,b in [('pub',pub),('review',raw),('sig',sig)]: (d/n).write_bytes(b)
        p=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(d/'pub'),'-rawin','-in',str(d/'review'),'-sigfile',str(d/'sig')],capture_output=True,timeout=10)
        need(p.returncode==0,'REVIEW_SIGNATURE')
    x=json_strict(raw);need(type(x) is dict and set(x)=={'schema','identity','native_receipt_sha256','feature_receipt_sha256','plan_sha256','candidate_acceptance_sha256','review_checks','status'},'REVIEW_FIELDS')
    need(x['schema']=='judun.feature-release-review.v1' and x['status']=='PASS','REVIEW_STATUS')
    need(all(x[k]==proof[k] for k in ('identity','native_receipt_sha256','feature_receipt_sha256','plan_sha256')) and hash_ok(acceptance_sha) and x['candidate_acceptance_sha256']==acceptance_sha,'REVIEW_BINDING')
    need(type(x['review_checks']) is dict and set(x['review_checks'])==REVIEW_CHECKS and all(hash_ok(v) for v in x['review_checks'].values()),'REVIEW_EVIDENCE_REQUIRED')
    return True
