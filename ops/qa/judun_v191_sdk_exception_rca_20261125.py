#!/usr/bin/env python3
"""Narrow diagnostic extension of the already executed v191 stage-only probe."""
import hashlib, inspect, os, pathlib, re, runpy, subprocess, sys, tempfile

def safe_sdk_trace(exc):
    m = re.match(r'^OCR worker failed: ([A-Za-z_][A-Za-z0-9_]{0,63}):\s*(.*)', str(exc), re.S)
    if not m:
        return ['SDK_ENVELOPE=UNMATCHED']
    kind, detail = m.groups()
    s = detail.lower()
    out = ['SDK_EXCEPTION_TYPE='+kind]
    http = re.search(r'^\s*([45]\d\d)\b', s) if kind in ('ClientError','ServerError','APIError','HTTPError') else None
    if not http:
        http = re.search(r'\b(?:http(?: status)?|status_code|[\'\"]code[\'\"])\s*[:= ]\s*([45]\d\d)\b', s)
    if http:
        out.append('SDK_HTTP_STATUS='+http.group(1))
    statuses = ('INVALID_ARGUMENT','FAILED_PRECONDITION','OUT_OF_RANGE','UNAUTHENTICATED','PERMISSION_DENIED','NOT_FOUND','RESOURCE_EXHAUSTED','UNAVAILABLE','DEADLINE_EXCEEDED','INTERNAL','UNIMPLEMENTED','CANCELLED','API_KEY_INVALID','API_KEY_SERVICE_BLOCKED','API_KEY_HTTP_REFERRER_BLOCKED','BILLING_DISABLED','SERVICE_DISABLED')
    statuses = [x for x in statuses if re.search(r'\b'+x.lower()+r'\b',s)]
    if statuses:
        out.append('SDK_STATUS='+','.join(statuses))
    rules = (
        ('KEY_MISSING',r'gemini_api_key missing'),
        ('AUTH',r'api.key.{0,30}(?:invalid|not valid|expired|blocked)|unauthenticated|credentials'),
        ('LOCATION',r'location.{0,50}(?:not supported|unsupported)|country.{0,30}(?:not supported|unsupported)'),
        ('BILLING',r'billing|payment required'),
        ('MODEL',r'model.{0,60}(?:not found|not supported|does not exist|invalid)'),
        ('QUOTA',r'quota|rate limit|resource.exhausted'),
        ('EMPTY_RESPONSE',r'empty ocr response|no candidates|finish.reason|safety.block'),
        ('INVALID_REQUEST',r'invalid.argument|bad request|invalid request'),
        ('VALIDATION',r'validation error|extra inputs|field required|unexpected keyword'),
        ('SDK_COMPATIBILITY',r'has no attribute|cannot import|no module named|not callable'),
        ('TIMEOUT',r'timeout|timed out|deadline'),
        ('PROXY_TLS',r'proxy|certificate|ssl|tls'),
        ('NETWORK',r'connection|network|dns|name resolution'),
        ('PERMISSION',r'permission|forbidden|access denied'),
        ('SERVER',r'unavailable|internal server|overloaded|temporarily'),
        ('RESPONSE_SHAPE',r'json|decode|serializ|response_mime_type|response_schema'),
        ('IPC',r'broken pipe|eoferror|pickle|connection reset'),
    )
    hits = [name for name,pattern in rules if re.search(pattern,s)]
    out.append('SDK_HINTS='+(','.join(hits) if hits else 'UNCLASSIFIED'))
    fields = ('http_options','retry_options','timeout_ms','timeout','attempts','max_output_tokens','response_mime_type','generate_content','api_version','text_only','pydantic','httpx','connecterror','remoteprotocolerror','validationerror','invalid','missing','unsupported','unrecognized','unexpected','integer','float','none','required','invalidargument','servererror','clienterror')
    found=[x for x in fields if re.search(r'\b'+x+r'\b',s)]
    if found:
        out.append('SDK_FIELDS='+','.join(found))
    return out

def self_test():
    samples=[('ClientError: 400 INVALID_ARGUMENT. {"error":{"code":400,"message":"private-ABC"}}','SDK_HTTP_STATUS=400'),('RuntimeError: GEMINI_API_KEY missing in child','SDK_HINTS=KEY_MISSING'),('ValueError: empty OCR response','SDK_HINTS=EMPTY_RESPONSE'),('ValidationError: unexpected keyword timeout; private-ABC','SDK_FIELDS=timeout,unexpected'),('ClientError: 429 RESOURCE_EXHAUSTED. private-ABC','SDK_HTTP_STATUS=429'),('AttributeError: module object has no attribute private-ABC','SDK_HINTS=SDK_COMPATIBILITY')]
    for raw,expected in samples:
        out=safe_sdk_trace(RuntimeError('OCR worker failed: '+raw))
        if expected not in out or 'private-ABC' in repr(out):
            raise SystemExit('STOP_CLASSIFIER_SELF_TEST')
    if safe_sdk_trace(RuntimeError('unrelated private-ABC'))!=['SDK_ENVELOPE=UNMATCHED']:
        raise SystemExit('STOP_CLASSIFIER_SELF_TEST')
    print('SDK_CLASSIFIER_SELF_TEST=7/7_PASS',flush=True)

BASE='https://raw.githubusercontent.com/momopuke/judun-deploy/'
SPECS=(
 ('runner.py','dddae11693a904a7e9fa741e7222fa39bc8c3f4a/ops/qa/judun_stage_native_business_qa_v3_20261124.py','sha256','d9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568'),
 ('probe.py','0c3d872267538c5d3186cbbf0fd830bf39c57072/ops/qa/judun_v191_ocr_failure_probe_20261124.py','sha256','f5cf551afea94e1668cfb349adc8aa120959dd6124cabd853be0b3b9a3a0ce09'),
 ('rca.py','8392b10649780728711f84bdcbd59a657051197c/ops/qa/judun_v191_native_ocr_rca_20261125.py','blob','d3a88ef12d8b34c2ff9b7413a184f029e18978a8'),
)
def prepare_child(child):
    mark='def main():\n'
    emit="    print('JUDUN_OCR_PROBE '+json.dumps(result),flush=True)"
    if child.count(mark)!=1 or child.count(emit)!=1:
        raise SystemExit('STOP_RCA_PATCH_CONTRACT')
    child=child.replace(mark,inspect.getsource(safe_sdk_trace)+'\n'+mark)
    child=child.replace(emit,"        result['trace'].extend(safe_sdk_trace(e))\n"+emit)
    compile(child,'<sdk-diagnostic-child>','exec')
    return child

def main():
    self_test()
    if sys.argv[1:]==['--self-test']:
        return
    if len(sys.argv)!=1 or os.geteuid()!=0:
        raise SystemExit('STOP_ARGUMENTS_OR_ROOT')
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='judun-sdk-rca-',dir='/root') as tmp:
        d=pathlib.Path(tmp)
        for name,path,kind,pin in SPECS:
            file=d/name
            subprocess.run(['/usr/bin/curl','-fsSL','--proto','=https','--tlsv1.2','--retry','2','--max-time','60',BASE+path,'-o',str(file)],check=True,timeout=90)
            raw=file.read_bytes()
            actual=hashlib.sha256(raw).hexdigest() if kind=='sha256' else hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
            if actual!=pin:
                raise SystemExit('STOP_DEPENDENCY_HASH')
        q=runpy.run_path(str(d/'rca.py'),run_name='sdk_rca_import')
        entry=q['main'];g=entry.__globals__
        g['CHILD']=prepare_child(g['CHILD'])
        print('PINNED_RCA_AND_CHILD_COMPILE=PASS',flush=True)
        sys.argv=[str(d/'rca.py'),str(d/'probe.py'),str(d/'runner.py')]
        entry()
if __name__=='__main__':
    main()
