#!/usr/bin/env python3
"""Stage-only QA launcher: derive identity from an original signed candidate."""
import argparse, base64, hashlib, json, os, re, runpy, subprocess, sys, tempfile
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

BASE = 'https://raw.githubusercontent.com/momopuke/judun-deploy/'
POINTER = 'main/ops/staging-request.json'
QA_PATH = 'dddae11693a904a7e9fa741e7222fa39bc8c3f4a/ops/qa/judun_stage_native_business_qa_v3_20261124.py'
QA_SHA = 'd9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568'
PUB = Path('/opt/judun-autodeploy/keys/release_signing_public.pem')
PUB_SHA = '17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def require(ok, code):
    if not ok:
        raise ValueError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def strict(raw):
    def pairs(items):
        d = dict(items)
        require(len(d) == len(items), 'DUPLICATE_JSON')
        return d
    return json.loads(raw, object_pairs_hook=pairs)

def fetch(path, limit):
    url = BASE + path
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url, headers={'Cache-Control':'no-cache'}), timeout=20) as r:
        require(r.status == 200 and r.geturl() == url, 'GITHUB_RESPONSE')
        raw = r.read(limit + 1)
    require(0 < len(raw) <= limit, 'GITHUB_SIZE')
    return raw

def commit_of(raw):
    d = strict(raw)
    require(isinstance(d, dict) and set(d) == {'candidate_commit'}, 'POINTER_SCHEMA')
    c = d['candidate_commit']
    require(isinstance(c, str) and re.fullmatch('[a-f0-9]{40}', c), 'NO_VALID_CANDIDATE')
    return c

def identity(raw):
    d = strict(raw)
    require(isinstance(d, dict) and set(d) == {'schema','base_snapshot','target','cms_sha256','zip_sha256'} and d['schema'] == 'judun.staging-deploy.v1', 'MANIFEST_SCHEMA')
    for k in ('cms_sha256','zip_sha256'):
        require(isinstance(d[k], str) and re.fullmatch('[a-f0-9]{64}', d[k]), 'MANIFEST_HASH')
    t = d['target']
    require(isinstance(t, dict) and set(t) == {'version','artifact_id','build_instance_id','source_tree_sha256','file_count'}, 'TARGET_SCHEMA')
    v = t['version']
    require(isinstance(v, str) and re.fullmatch('1\\.2\\.[0-9]+', v), 'TARGET_VERSION')
    for k, prefix in (('artifact_id','JUDUN-'+v+'-'),('build_instance_id',v+'-')):
        x = t[k]
        require(isinstance(x,str) and x.startswith(prefix) and re.fullmatch('[A-Za-z0-9._-]{1,160}',x), 'TARGET_ID')
    require(isinstance(t['source_tree_sha256'], str) and re.fullmatch('[a-f0-9]{64}',t['source_tree_sha256']), 'TARGET_TREE')
    require(type(t['file_count']) is int and 1 <= t['file_count'] <= 2000, 'TARGET_COUNT')
    return dict(version=v,artifact_id=t['artifact_id'],build_instance_id=t['build_instance_id'],source_tree_sha256=t['source_tree_sha256'],count=t['file_count'])

def verified(raw, sig, key, key_sha, work):
    require(sha(key) == key_sha, 'KEY_PIN')
    signature = base64.b64decode(b''.join(sig.split()), validate=True)
    require(len(signature) == 64, 'SIGNATURE_SIZE')
    for name, data in [('pub',key),('manifest',raw),('sig',signature)]:
        (work/name).write_bytes(data)
    r = subprocess.run(['openssl','pkeyutl','-verify','-pubin','-inkey',str(work/'pub'),'-rawin','-in',str(work/'manifest'),'-sigfile',str(work/'sig')],capture_output=True,timeout=10)
    require(r.returncode == 0, 'SIGNATURE_INVALID')
    return identity(raw)

def main():
    p = argparse.ArgumentParser(); p.add_argument('--run',action='store_true'); args=p.parse_args()
    require(os.geteuid() == 0,'ROOT_REQUIRED'); os.umask(0o077)
    commit = commit_of(fetch(POINTER,2048)); prefix = commit + '/staging/candidate'
    with tempfile.TemporaryDirectory(prefix='judun-native-qa-') as directory:
        work=Path(directory)
        expected=verified(fetch(prefix+'.json',8192),fetch(prefix+'.json.sig.b64',1024),PUB.read_bytes(),PUB_SHA,work)
        raw=fetch(QA_PATH,128000); require(sha(raw)==QA_SHA,'QA_SCRIPT_PIN')
        script=work/'native_qa.py'; script.write_bytes(raw)
        qa=runpy.run_path(str(script),run_name='judun_pinned_qa')
        env,_,token=qa['read_env'](); qa['Client'](token,'',expected).health()
        require(commit_of(fetch(POINTER,2048))==commit,'POINTER_CHANGED')
        receipt=qa['ROOT']/(expected['source_tree_sha256']+'.receipt.json')
        if receipt.exists():
            require(qa['valid_private'](receipt),'RECEIPT_UNSAFE')
            d=strict(receipt.read_bytes()); require(d.get('identity')==expected and d.get('status')=='PASS','RECEIPT_MISMATCH')
            print(json.dumps({'status':'EXISTING_NATIVE_QA_PASS','commit':commit,'identity':expected,'receipt_sha256':sha(receipt.read_bytes())})); return 0
        codefile=qa['ROOT']/'test-code'
        codes=[env.get('TEST_PAYMENT_CODE',''),env.get('JUDUN_QA_TEST_CODE','')]
        if codefile.exists():
            require(qa['valid_private'](codefile),'TEST_CODE_UNSAFE'); codes.append(codefile.read_text().strip())
        ready=any(c and sha(c.encode())==qa['CODE_PIN'] for c in codes)
        print(json.dumps({'status':'NATIVE_QA_PENDING','commit':commit,'identity':expected,'noninteractive_code_ready':bool(ready),'run_requested':args.run}),flush=True)
        if not args.run:
            return 0
        require(ready,'STAGE_TEST_CODE_UNAVAILABLE')
        cmd=[sys.executable,'-I','-B',str(script),'--version',expected['version'],'--artifact',expected['artifact_id'],'--build',expected['build_instance_id'],'--tree',expected['source_tree_sha256'],'--count',str(expected['count'])]
        # No TTY, no prompt, no repeat POST on ambiguous case; the original QA owns the case lock/state.
        return subprocess.run(cmd,stdin=subprocess.DEVNULL,start_new_session=True,check=False).returncode

if __name__=='__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('HOLD:',str(e) if type(e) is ValueError else type(e).__name__); sys.exit(2)
