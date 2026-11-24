#!/usr/bin/env python3
"""Stage-only synthetic single-file OCR diagnosis. No app import, HTTP POST, database writes or production modifications."""
import hashlib, pathlib, sys
PROBE_PIN="f5cf551afea94e1668cfb349adc8aa120959dd6124cabd853be0b3b9a3a0ce09"
UPLOAD="a725a3576d956db72a8cb16d51efb107b338429e3746c068ec0d177976c56eb9"
CHILD=r'''
import ast, hashlib, json, logging, os, re, sys, threading, traceback
from pathlib import Path
from typing import Tuple
req=json.load(sys.stdin)
source=Path(req['source'])
sys.path.insert(0,str(source))
if not req.get('mock'):
    os.chdir('/var/lib/judun-staging')
    sys.argv=['/srv/judun-staging/staging_release.py','serve']
    sys.modules['__main__'].__file__=sys.argv[0]
from ocr_spawn_worker import OCRRequest,run_request as worker
from ocr_budget import OCRJobBudget
from ocr_recovery import quality
from ocr_cache_gate import validated_cache
from quote_terms import SCHEMA as QUOTE_TERMS_SCHEMA,normalize_terms,extract_terms
src=ast.parse((source/'app.py').read_text())
outer=next(n for n in src.body if isinstance(n,ast.FunctionDef) and n.name=='run_ocr_extraction')
func=next(n for n in ast.walk(outer) if isinstance(n,ast.FunctionDef) and n.name=='extract_one_file')
names={'_stable_cache_hash','_decode_text','extract_document_text','extract_json_from_response','clean_category_name'}
module=ast.Module(body=[n for n in src.body if isinstance(n,ast.FunctionDef) and n.name in names]+[func],type_ignores=[])
assert len(module.body)==6
stage='BEFORE_WORKER';calls=0
OCR_CACHE_VERSION='ocr_v130_r4_provenance_fail_closed'
GEMINI_LITE_MODEL_ID=(os.getenv('GEMINI_LITE_MODEL',os.getenv('GEMINI_MODEL','gemini-3.5-flash-lite')).strip() or 'gemini-3.5-flash-lite')
TEXT_DOCUMENT_EXTS={'.csv'}
_ai_cache_get=lambda *args: None
logger=logging.getLogger('probe')
ocr_budget=OCRJobBudget(1)
extraction_prompt=req['prompt']
def run_request(*a,**kw):
    global stage,calls
    stage='WORKER';calls+=1
    if calls!=1:raise RuntimeError('call limit')
    if req.get('mock'):
        result=json.dumps({'items':[dict(zip(['項目','數量','單位','單價','總價'],r)) for r in req['items']]},ensure_ascii=False)
    else:result=worker(*a,**kw)
    stage='AFTER_WORKER'
    return result
exec(compile(module,str(source/'app.py'),'exec'),globals())
body=req['text'].split('以下是由文件安全擷取出的文字與表格內容：\n',1)[1].encode('utf-8-sig')
assert hashlib.sha256(body).hexdigest()==req['upload_sha256']
def main():
    try:
        _,rows,terms,_=extract_one_file(0,(body,req['filename'],'text/csv'),0)
        valid=quality(rows)[0]
        def norm(r):
            from decimal import Decimal
            n=[x for x,*_ in req['items'] if x in str(r['項目'])]
            if len(n)!=1:raise ValueError('label')
            return (n[0],Decimal(str(r['數量']).replace(',','')),r['單位'],Decimal(str(r['單價']).replace(',','')),Decimal(str(r['總價']).replace(',','')))
        try: exact=sorted(map(norm,rows))==sorted(tuple(r) for r in req['items'])
        except Exception:exact=False
        result=dict(code='APP_EXACT_PASS' if exact and valid==4 else 'APP_QUALITY_OR_ROW_MISMATCH',rows=len(rows),expected=4,valid=valid,calls=calls,phase=stage)
    except Exception as e:
        msg=str(e).lower()
        cat=next((code for pat,code in [(r'permission|read.only|unsafe shared lock','PERMISSION'),(r'no module|importerror','IMPORT'),(r'quota|resource.exhausted|\b429\b','QUOTA'),(r'api.key|unauthenticated|\b401\b','AUTH'),(r'not.found|\b404\b','MODEL'),(r'deadline|timeout|timed out','TIMEOUT'),(r'eof|broken pipe|pickle|spawn','SPAWN_IPC'),(r'network|connection|ssl|certificate','NETWORK')] if re.search(pat,msg)),'OTHER')
        result=dict(code='APP_EXCEPTION',phase=stage,calls=calls,exception=type(e).__name__,category=cat,trace=[f'{Path(x.filename).name}:{x.lineno}:{x.name}' for x in traceback.extract_tb(e.__traceback__) if Path(x.filename).name in ('app.py','ocr_spawn_worker.py','ocr_budget.py','quote_terms.py','connection.py','process.py','spawn.py')])
    print('JUDUN_OCR_PROBE '+json.dumps(result),flush=True)
t=threading.Thread(target=main);t.start();t.join()
'''
def main():
    if len(sys.argv)!=3:raise SystemExit('STOP_ARGUMENTS')
    probe,runner=sys.argv[1:]
    raw=pathlib.Path(probe).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PROBE_PIN:raise SystemExit('STOP_PROBE_HASH')
    text=raw.decode()
    start=text.index("CHILD=r'''");end=text.index("\nCODES=",start)
    text=text[:start]+"CHILD="+repr(CHILD)+text[end:]
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise SystemExit('STOP_PATCH_CONTRACT')
        text=text.replace(old,new)
    replace("UPLOAD='e3052d04b49362c110f410fe2a1adffbf67542879b2127110a2f28105a5a1845'","UPLOAD="+repr(UPLOAD))
    replace("items=q['ITEMS']","items=q['ITEMS'],upload_sha256=UPLOAD")
    replace("CODES={","CODES={'APP_EXACT_PASS','APP_QUALITY_OR_ROW_MISMATCH','APP_EXCEPTION',")
    replace("rows=d.get('rows'),expected=d.get('expected'),stage_identity_after=","rows=d.get('rows'),expected=d.get('expected'),diagnostic={k:d[k] for k in ('phase','valid','calls','exception','category','trace') if k in d},stage_identity_after=")
    sys.argv=[probe,runner]
    exec(compile(text,probe,'exec'),{'__name__':'__main__','__file__':probe})
if __name__=='__main__':main()
