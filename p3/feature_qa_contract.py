"""Declarative supplemental QA contract. Does not install or execute any service."""
import json, re, hashlib, subprocess, tempfile
from pathlib import Path
SCHEMA='judun.feature-qa-plan.v1'
ORIGINAL_PUB_SHA='17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'
ALLOWED=('vendor_markup','native_model_trace','preview_110')
class Reject(ValueError): pass
def require(ok, reason):
    if not ok: raise Reject(reason)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def decode(raw):
    require(0<len(raw)<=8192,'PLAN_SIZE')
    def pairs(items):
        obj=dict(items);require(len(items)==len(obj),'DUPLICATE_KEY');return obj
    try: return json.loads(raw,object_pairs_hook=pairs)
    except (UnicodeError,json.JSONDecodeError): raise Reject('PLAN_JSON') from None
def verify_signature(raw,sig,pub,pin=ORIGINAL_PUB_SHA):
    require(sha(pub)==pin,'SIGNER_PIN');require(len(sig)==64,'SIGNATURE_SIZE')
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        for name,b in [('plan',raw),('sig',sig),('pub',pub)]: (root/name).write_bytes(b)
        p=subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(root/'pub'),'-rawin','-in',str(root/'plan'),'-sigfile',str(root/'sig')],capture_output=True,timeout=10)
        require(p.returncode==0,'SIGNATURE_INVALID')
def validate(raw,sig,pub,identity,native_receipt,*,pin=ORIGINAL_PUB_SHA):
    verify_signature(raw,sig,pub,pin)
    d=decode(raw)
    require(type(d) is dict and set(d)=={'schema','identity','checks','target_model','max_preview_seconds'},'PLAN_FIELDS')
    require(d['schema']==SCHEMA,'PLAN_SCHEMA')
    i=d['identity'];require(type(i) is dict and set(i)=={'version','artifact_id','build_instance_id','source_tree_sha256','count'},'IDENTITY_FIELDS')
    require(i==identity,'IDENTITY_MISMATCH')
    require(type(i['version']) is str and re.fullmatch(r'1\.2\.[0-9]+',i['version']),'VERSION')
    for k in ('artifact_id','build_instance_id'):
        require(type(i[k]) is str and re.fullmatch(r'[A-Za-z0-9._-]{1,160}',i[k]),'ID_FORMAT')
    require(type(i['source_tree_sha256']) is str and re.fullmatch('[0-9a-f]{64}',i['source_tree_sha256']),'TREE')
    require(type(i['count']) is int and 1<=i['count']<=2000,'FILE_COUNT')
    r=decode(native_receipt);require(type(r) is dict and r.get('status')=='PASS' and r.get('identity')==identity,'NATIVE_RECEIPT')
    c=d['checks'];require(type(c) is list and 0<len(c)<=len(ALLOWED) and all(type(x) is str and x in ALLOWED for x in c) and len(set(c))==len(c),'CHECK_ALLOWLIST')
    require('preview_110' not in c or 'native_model_trace' in c,'CHECK_DEPENDENCY')
    model=d['target_model'];require(type(model) is str and re.fullmatch(r'gemini-[a-z0-9.-]{1,100}',model),'MODEL_ID')
    limit=d['max_preview_seconds'];require(type(limit) is int and 30<=limit<=900,'TIME_BUDGET')
    return {'identity':i,'checks':c,'target_model':model,'max_preview_seconds':limit,'plan_sha256':sha(raw),'native_receipt_sha256':sha(native_receipt)}
