"""Additional trusted-base guard for v195 and subsequent signed feature plans.
Does not alter the original three-file production release contract.
"""
import base64,re
from feature_evidence import need,sha,identity,hash_ok,verify_review,ORIGINAL_PIN
from feature_qa_contract import decode,verify_signature,ALLOWED
V195_TREE='36c9920d2bab3e66defca3d5da10c600a4188f4b887ae2206bf741e95de3a292'

def target_identity(target):
    return identity({'version':target['expected_display_version'].removeprefix('v'),'artifact_id':target['target_artifact_id'],'build_instance_id':target['target_build_instance_id'],'source_tree_sha256':target['expected_source_tree_sha256'],'count':target['expected_managed_file_count']})

def paths(target):
    tree=target_identity(target)['source_tree_sha256'];p='ops/feature-qa-plans/'+tree;r='ops/feature-qa-reviews/'+tree
    return (p+'.json',p+'.json.sig.b64',r+'.json',r+'.json.sig.b64')

def required(target,exists):
    p=paths(target);i=target_identity(target)
    # All v195 product builds must have the reviewed plan; if a later tree has
    # any feature-control artifact, partial/missing counterparts fail closed.
    # Other future releases retain original native QA until their classification
    # policy is explicitly defined; never infer a changed feature from a version.
    return i['version']=='1.2.195' or i['source_tree_sha256']==V195_TREE or any(exists(x) for x in p)

def signed(raw,sig_b64,pub,pin):
    need(type(sig_b64) is bytes and 0<len(sig_b64)<=1024,'FEATURE_SIGNATURE_SIZE')
    sig=base64.b64decode(b''.join(sig_b64.split()),validate=True);verify_signature(raw,sig,pub,pin);return sig

def verify(target,read_blob,public_key,attested,*,pin=ORIGINAL_PIN):
    i=target_identity(target);p,ps,r,rs=paths(target);raw=read_blob(p,8192);signed(raw,read_blob(ps,1024),public_key,pin);plan=decode(raw)
    need(type(plan) is dict and set(plan)=={'schema','identity','checks','target_model','max_preview_seconds'} and plan['schema']=='judun.feature-qa-plan.v1' and plan['identity']==i,'FEATURE_PLAN_IDENTITY')
    checks=plan['checks'];need(type(checks) is list and 0<len(checks)<=len(ALLOWED) and all(type(x) is str and x in ALLOWED for x in checks) and len(set(checks))==len(checks),'FEATURE_PLAN_CHECKS')
    need(i['version']!='1.2.195' or set(checks)==set(ALLOWED),'V195_ALL_CHECKS_REQUIRED')
    need('preview_110' not in checks or 'native_model_trace' in checks,'FEATURE_PLAN_DEPENDENCY')
    need(type(plan['target_model']) is str and re.fullmatch(r'gemini-[a-z0-9.-]{1,100}',plan['target_model']) and type(plan['max_preview_seconds']) is int and 30<=plan['max_preview_seconds']<=900,'FEATURE_PLAN_LIMITS')
    n=attested.get('native_qa') or {};builds=attested.get('feature_qa_builds')
    need(n.get('native_qa_status')=='PASS' and hash_ok(n.get('native_qa_receipt_sha256')) and type(n.get('native_qa_file_count')) is int and n['native_qa_file_count']==i['count'],'FEATURE_NATIVE_REQUIRED')
    need(type(builds) is list and len(builds)==2 and all(type(b) is dict for b in builds),'FEATURE_OIDC_DOUBLE_READ_REQUIRED')
    f=builds[0];need(hash_ok(f.get('feature_receipt_sha256')) and f.get('feature_plan_sha256')==sha(raw),'FEATURE_RECEIPT_REQUIRED')
    proof={'identity':i,'native_receipt_sha256':n['native_qa_receipt_sha256'],'plan_sha256':sha(raw),'feature_receipt_sha256':f['feature_receipt_sha256'],'feature_qa_status':'EVIDENCE_READY_NOT_RELEASE_APPROVAL'}
    approval=read_blob(r,8192);sig=base64.b64decode(b''.join(read_blob(rs,1024).split()),validate=True)
    need(verify_review(approval,sig,public_key,proof,target['candidate_acceptance_sha256'],*builds,pin=pin),'FEATURE_REVIEW_REQUIRED')
    return proof['feature_receipt_sha256']
