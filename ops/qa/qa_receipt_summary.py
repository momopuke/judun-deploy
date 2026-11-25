#!/usr/bin/env python3
"""Publish only a stage QA attestation hash; never expose the original receipt."""
import hashlib, json, os, re, stat, tempfile
from pathlib import Path
STAGE=Path('/srv/judun-staging')
STATE=Path('/var/lib/judun-stage-native-qa-auto')
RECEIPTS=Path('/var/lib/judun-stage-business-qa')
EXPORT=Path('/srv/judun-stage-health-oidc/qa-summary/receipt.json')
HEX=re.compile(r'[0-9a-f]{64}\Z')
KEYS=('version','artifact_id','build_instance_id','source_tree_sha256','count')

def need(ok,code):
    if not ok: raise ValueError(code)

def sha(raw): return hashlib.sha256(raw).hexdigest()

def strict(raw):
    def pairs(xs):
        d=dict(xs); need(len(d)==len(xs),'DUPLICATE_FIELD'); return d
    return json.loads(raw,object_pairs_hook=pairs)

def read(path,private):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as f:
        s=os.fstat(f.fileno())
        need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1,'UNSAFE_FILE')
        need(not(s.st_mode&(0o077 if private else 0o022)),'UNSAFE_MODE')
        raw=f.read(1048577)
    need(0<len(raw)<=1048576,'FILE_SIZE'); return raw

def identity(e):
    need(isinstance(e,dict) and set(e)==set(KEYS),'IDENTITY_SCHEMA')
    v=e['version']; need(isinstance(v,str) and re.fullmatch(r'1\.2\.\d+',v),'VERSION')
    for k,prefix in [('artifact_id','JUDUN-'+v+'-'),('build_instance_id',v+'-')]:
        x=e[k]; need(isinstance(x,str) and x.startswith(prefix) and re.fullmatch(r'[A-Za-z0-9._-]{1,160}',x),'IDENTITY')
    need(isinstance(e['source_tree_sha256'],str) and HEX.fullmatch(e['source_tree_sha256']),'TREE')
    need(type(e['count']) is int and 1<=e['count']<=2000,'COUNT')
    return {k:e[k] for k in KEYS}

def summarize(link,record,raw):
    m=re.fullmatch(r'releases/(JUDUN-[A-Za-z0-9._-]{1,160})-([a-f0-9]{64})',link)
    need(m is not None,'STAGE_POINTER'); artifact,tree=m.groups()
    need(isinstance(record,dict) and record.get('status')=='PASS' and record.get('artifact')==artifact and record.get('tree')==tree,'AUTO_QA_NOT_PASS')
    digest=sha(raw); need(record.get('receipt_sha256')==digest,'RECEIPT_HASH')
    d=strict(raw); need(isinstance(d,dict) and d.get('schema')=='judun.stage-native-business-qa.v1' and d.get('status')=='PASS','RECEIPT_SCHEMA')
    e=identity(d.get('identity')); need(e['artifact_id']==artifact and e['source_tree_sha256']==tree,'STAGE_IDENTITY')
    return {'schema':'judun.native-qa-summary.v1','status':'PASS','identity':e,'receipt_sha256':digest}

def validate(summary,build):
    need(isinstance(summary,dict) and set(summary)=={'schema','status','identity','receipt_sha256'},'SUMMARY_SCHEMA')
    need(summary['schema']=='judun.native-qa-summary.v1' and summary['status']=='PASS','SUMMARY_STATUS')
    e=identity(summary['identity']); h=summary['receipt_sha256']
    need(isinstance(h,str) and HEX.fullmatch(h),'SUMMARY_HASH')
    need(build.get('status')=='ok' and build.get('manifest_status')=='ok' and build.get('payment_mode')=='test_unlock','STAGE_NOT_READY')
    need(str(build.get('version','')).removeprefix('v')==e['version'] and all(build.get(k)==e[k] for k in KEYS[1:4]),'STALE_SUMMARY')
    return {'native_qa_status':'PASS','native_qa_receipt_sha256':h,'native_qa_file_count':e['count']}

def decorate(build,path=EXPORT,reader=read):
    result=dict(build)
    try: result.update(validate(strict(reader(path,False)),build))
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        result.update(native_qa_status='PENDING',native_qa_receipt_sha256='',native_qa_file_count=0)
    return result

def publish(stage=STAGE,state=STATE,receipts=RECEIPTS,export=EXPORT):
    need(os.geteuid()==0,'ROOT_REQUIRED')
    link=os.readlink(stage/'current'); m=re.fullmatch(r'releases/(JUDUN-[A-Za-z0-9._-]{1,160})-([a-f0-9]{64})',link)
    need(m is not None,'STAGE_POINTER'); tree=m.group(2)
    for root,private in [(state,True),(receipts,True),(export.parent,False)]:
        s=root.lstat(); need(stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not(s.st_mode&(0o077 if private else 0o022)),'UNSAFE_DIRECTORY')
    summary=summarize(link,strict(read(state/(sha(link.encode())+'.json'),True)),read(receipts/(tree+'.receipt.json'),True))
    need(os.readlink(stage/'current')==link,'STAGE_CHANGED')
    fd,tmp=tempfile.mkstemp(prefix='.qa-',dir=export.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(json.dumps(summary,sort_keys=True).encode()+b'\n'); f.flush(); os.fchmod(f.fileno(),0o644); os.fsync(f.fileno())
        os.replace(tmp,export)
        d=os.open(export.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(d)
        finally: os.close(d)
    finally:
        Path(tmp).unlink(missing_ok=True)
    print('NATIVE_QA_SUMMARY_PUBLISHED',summary['receipt_sha256'],flush=True)
    return summary

if __name__=='__main__':
    try: publish()
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as e:
        print('NATIVE_QA_SUMMARY_HOLD',type(e).__name__,flush=True); raise SystemExit(2)
