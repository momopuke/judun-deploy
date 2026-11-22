#!/usr/bin/env python3
"""One-shot, staging-only 4-grid and PDF QA on an already-paid synthetic sample.
Runs the shipped native functions under the active stage process uid/gid, never
imports production code, creates payments, changes production, or signs releases.
Fixes v1 failure: accepts only R1 source-approved DynamicUser staging data roots,
and locates real worker PIDs via listener, systemd MainPID and cgroups.
"""
import hashlib, json, os, re, shutil, sqlite3, subprocess, sys, time
from pathlib import Path
from urllib.request import urlopen

BASE='http://127.0.0.1:8011'
DB=Path('/var/lib/judun-staging/app_data.db')
FP='e110ada5dbd5'
ART='JUDUN-1.2.190-STAGE-SANDBOX-E2E-R1-UNSIGNED'
TREE='464a6d76b1ecb723c8a4767c0e4b354d649f582f6c565c1174ccdd3f89c55c32'
APP_SHA='4da942d2512eca43a9cd8451022fb7598203b4512ddf8f0958bed2f6ecda9af6'
PDF_SHA='175967b1b6afa26617af5409af0bdeea4342228fadf51b7c4e5126f80f6a93ae'
F=('price_secret','shoddy_tactics','contract_specs','inspection_tips')

def stop(msg):
    raise SystemExit('STOP_'+msg)
def get(path):
    with urlopen(BASE+path, timeout=7) as r:return json.load(r)
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def preflight():
    if os.geteuid()!=0:stop('NEEDS_ROOT_FINALSHELL')
    b=get('/health/build'); a=get('/health/artifact?deep=true'); r=get('/health/ready')
    if not (b.get('artifact_id')==a.get('artifact_id')==ART
            and b.get('source_tree_sha256')==a.get('source_tree_sha256')==TREE
            and b.get('payment_mode')=='ecpay_stage'
            and a.get('files_verified')==a.get('manifest_file_count')==98
            and a.get('mismatch_count')==0 and a.get('deep_verified') is True
            and r.get('status')=='ready'):stop('STAGE_IDENTITY')
    print('STAGE_IDENTITY_98_98=PASS',flush=True)
    if DB.is_symlink() or not DB.is_file():stop('STAGE_DB_INVALID')
    c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
    c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
    try:
        hits=[]
        for row in c.execute('SELECT id,tier,status,project_profile,evaluated_data,item_deep_dives FROM jobs ORDER BY created_at DESC LIMIT 2000'):
            if hashlib.sha256(str(row['id']).encode()).hexdigest()[:12]!=FP:continue
            p=json.loads(row['project_profile'] or '{}')
            if isinstance(p,dict) and p.get('staging_sample') is True:hits.append(row)
        if len(hits)!=1:stop('SAMPLE_NOT_UNIQUE')
        j=hits[0]
        if j['tier']!='promax' or '完成' not in str(j['status']):stop('NOT_PROMAX_COMPLETE')
        paid={(x['tier'],int(x['amount'])) for x in c.execute('SELECT tier,amount FROM payment_orders WHERE job_id=? AND status=?',(j['id'],'paid'))}
        if ('basic',299) not in paid or ('promax',300) not in paid:stop('PAYMENT_PERSISTENCE')
        u=c.execute('SELECT state FROM unlock_tasks WHERE job_id=?',(j['id'],)).fetchone()
        if not u or u['state']!='completed':stop('UNLOCK_INCOMPLETE')
        data=json.loads(j['evaluated_data'] or '{}')
        rows=data.get('items_analysis')
        if not isinstance(rows,list) or len(rows)!=4 or not all(isinstance(x,dict) for x in rows):stop('FOUR_ITEMS_NOT_FOUND')
        if any(not isinstance(x.get('item'),str) or not x['item'].strip() for x in rows):stop('ITEM_NAMES_INVALID')
        print('ORIGINAL_SANDBOX_PAID_PROMAX=PASS',flush=True)
        return str(j['id'])
    finally:c.close()

STAGE_DATA_ROOTS = frozenset((
    '/var/lib/judun-staging',
    '/var/lib/private/judun-staging',
    '/var/lib/judun-staging/state',
))
STAGE_UNITS = ('judun-staging-isolated.service', 'judun-staging.service')

def stage_process():
    """Find an actual staging worker, not just systemd's wrapper MainPID.

    Under systemd's DynamicUser / StateDirectory, APP_DATA_DIR can be one
    of several *application-declared* staging paths. This discovery never
    guesses credentials or copies environment from an unrelated process.
    """
    candidates = []
    diagnostics = []
    try:
        ss = subprocess.run(['ss', '-H', '-lntp', 'sport = :8011'],
                            capture_output=True, text=True, timeout=6, check=True)
        candidates += [int(x) for x in re.findall(r'pid=(\d+)', ss.stdout)]
        if not candidates:
            diagnostics.append('listener_pid_not_exposed')
    except Exception:
        diagnostics.append('ss_unavailable')

    for unit in STAGE_UNITS:
        try:
            p = subprocess.run(['systemctl', 'show', '--property=MainPID,ControlGroup',
                                unit], capture_output=True, text=True, timeout=6, check=True)
            properties = dict(line.split('=', 1) for line in p.stdout.splitlines() if '=' in line)
            mainpid = int(properties.get('MainPID') or '0')
            if mainpid > 1:
                candidates.append(mainpid)
            cg = properties.get('ControlGroup', '')
            if cg.startswith('/') and '..' not in Path(cg).parts:
                procs = Path('/sys/fs/cgroup') / cg.lstrip('/') / 'cgroup.procs'
                try:
                    candidates += [int(v) for v in procs.read_text().split()]
                except (OSError, ValueError):
                    diagnostics.append(unit + ':cgroup_unavailable')
        except Exception:
            diagnostics.append(unit + ':systemd_unavailable')
    if not candidates:
        print('STAGE_DISCOVERY=' + ','.join(diagnostics), flush=True)
        stop('STAGING_PROCESS_NOT_FOUND')

    # Never dump environ: it may contain credentials. Report only gate labels.
    issues = []
    for pid in dict.fromkeys(candidates):
        try:
            proc = Path('/proc') / str(pid)
            raw = (proc / 'environ').read_bytes()
            env = dict((k.decode('utf-8'), v.decode('utf-8'))
                       for item in raw.split(b'\0') if b'=' in item
                       for k, v in [item.split(b'=', 1)])
            if env.get('JUDUN_STAGING') != '1':
                issues.append('stage_flag_missing')
                continue
            if env.get('APP_DATA_DIR', '').rstrip('/') not in STAGE_DATA_ROOTS:
                issues.append('stage_data_path_unrecognized')
                continue
            if env.get('JUDUN_STAGING_ECPAY_SANDBOX') != '1':
                issues.append('stage_sandbox_flag_missing')
                continue
            cwd = Path(os.readlink(proc / 'cwd'))
            cmd = [x.decode('utf-8', 'replace') for x in (proc / 'cmdline').read_bytes().split(b'\0') if x]
            status = (proc / 'status').read_text()
            uid = int(re.search(r'^Uid:\s*(\d+)', status, re.M).group(1))
            gid = int(re.search(r'^Gid:\s*(\d+)', status, re.M).group(1))
            groups = [int(v) for v in re.search(r'^Groups:\s*(.*)$', status, re.M).group(1).split()]
            if uid == 0:
                issues.append('stage_worker_root_identity')
                continue
            # Require exact bytes for the *staging* application before
            # allowing any worker to import app.py or write synthetic data.
            try:
                appdir, runners = find_runtime(cwd, cmd)
            except SystemExit:
                issues.append('stage_source_sha_mismatch')
                continue
            print('STAGING_SOURCE_AND_PROCESS_IDENTITY=PASS', flush=True)
            return pid, cwd, cmd, env, uid, gid, groups, appdir, runners
        except (OSError, ValueError, AttributeError, IndexError):
            issues.append('stage_process_unreadable')
    print('STAGE_DISCOVERY_CANDIDATES=' + str(len(set(candidates))), flush=True)
    print('STAGE_DISCOVERY_REASONS=' + ','.join(sorted(set(issues + diagnostics))), flush=True)
    stop('STAGING_PROCESS_ENV_NOT_FOUND')

def find_runtime(cwd,cmd):
    dirs=[cwd,cwd/'payload',cwd/'current',Path('/srv/judun-staging/current'),Path('/srv/judun-staging')]
    for i,c in enumerate(cmd):
        if c=='--app-dir' and i+1<len(cmd):dirs.insert(0,Path(cmd[i+1]))
        if c.endswith('/app.py'):dirs.insert(0,Path(c).parent)
    app_dir=None
    for d in dict.fromkeys(dirs):
        if (d/'app.py').is_file() and (d/'pdf_queue.py').is_file():
            if sha(d/'app.py')==APP_SHA and sha(d/'pdf_queue.py')==PDF_SHA:
                app_dir=d;break
    if app_dir is None:stop('ACTIVE_SOURCE_PATH_OR_SHA_MISMATCH')
    runners=[]
    if cmd:
        p=Path(cmd[0]);runners.append(p)
        if 'uvicorn' in p.name:runners.extend([p.parent/'python',p.parent/'python3'])
    for d in (cwd,app_dir,app_dir.parent,Path('/srv/judun-staging')):
        runners.extend([d/'venv/bin/python',d/'.venv/bin/python',d/'venv/bin/python3',d/'.venv/bin/python3'])
    runners.append(Path('/usr/bin/python3'))
    return app_dir,list(dict.fromkeys(runners))

WORKER=r'''
import hashlib, json, os, re, shutil, subprocess, sys, time
from pathlib import Path
SRC=Path(sys.argv[1]);JOB_ID=sys.argv[2]
sys.path.insert(0,str(SRC))
import app as a
FIELDS=('price_secret','shoddy_tactics','contract_specs','inspection_tips')
def die(why):raise SystemExit('STOP_WORKER_'+why)
if (not a.STAGING_ENVIRONMENT or
        str(Path(a.DATA_DIR).resolve()) not in ('/var/lib/judun-staging', '/var/lib/private/judun-staging', '/var/lib/judun-staging/state')):
    die('ENV_NOT_STAGE')
if a.os.getenv('JUDUN_STAGING_ECPAY_SANDBOX')!='1':die('SANDBOX_NOT_ENABLED')
with a.SessionLocal() as db:
    j=db.get(a.Job,JOB_ID)
    if not j or not a.is_staging_sample(j) or j.tier!='promax' or '完成' not in str(j.status):die('SAMPLE_NOT_ELIGIBLE')
    paid={(o.tier,o.amount) for o in db.query(a.PaymentOrder).filter(a.PaymentOrder.job_id==JOB_ID,a.PaymentOrder.status=='paid').all()}
    if ('basic',299) not in paid or ('promax',300) not in paid:die('PAID_NOT_FOUND')
    data=json.loads(j.evaluated_data or '{}')
    rows=data.get('items_analysis')
    if not isinstance(rows,list) or len(rows)!=4:die('ITEM_ROWS_INVALID')
    if len({a.analysis_item_key(row) for row in rows})!=4:die('ITEM_KEYS_DUPLICATED')
    status=j.status
print('STAGE_NATIVE_ENTITLEMENT_CHECK=PASS',flush=True)
for ix,row in enumerate(rows,1):
    key=a.analysis_item_key(row)
    with a.SessionLocal() as db:
        j=db.get(a.Job,JOB_ID)
        if not j or not a.is_staging_sample(j) or j.tier!='promax':die('SAMPLE_CHANGED')
        guide=json.loads(j.item_deep_dives or '{}')
        old=guide.get(key)
        ready=isinstance(old,dict) and all(isinstance(old.get(k),str) and old[k].strip() for k in FIELDS)
        if j.status in {'微付費運算中','基本指南生成中'}:die('BACKGROUND_TASK_RUNNING')
    if not ready:
        a.run_item_deep_dive(JOB_ID,key,status)
    with a.SessionLocal() as db:
        j=db.get(a.Job,JOB_ID)
        if not j or not a.is_staging_sample(j):die('JOB_INVALID_AFTER_GENERATE')
        guide=json.loads(j.item_deep_dives or '{}').get(key)
        if (not isinstance(guide,dict) or not all(isinstance(guide.get(k),str) and guide[k].strip() for k in FIELDS)
             or '完成' not in str(j.status)):die('GRID_'+str(ix)+'_NOT_COMPLETE')
    print('FOUR_GRID_ITEM_'+str(ix)+'=PASS',flush=True)
with a.SessionLocal() as db:
    j=db.get(a.Job,JOB_ID)
    g=json.loads(j.item_deep_dives or '{}')
    if sum(1 for row in rows if isinstance(g.get(a.analysis_item_key(row)),dict) and all(isinstance(g[a.analysis_item_key(row)].get(k),str) and g[a.analysis_item_key(row)][k].strip() for k in FIELDS))!=4:die('FOUR_GRID_NOT_4_OF_4')
    ctx=a.build_report_context_from_job(j)
    if (not isinstance(ctx.get('deep_dives'),list) or len(ctx['deep_dives'])!=4 or
        any(not isinstance(x,dict) or not all(str(x.get(k,'')).strip() for k in FIELDS) for x in ctx['deep_dives'])):die('PDF_CONTEXT_MISSING_GRIDS')
    rendered=a.build_professional_report(ctx)
    if not isinstance(rendered,str) or len(rendered)<1000:die('PDF_HTML_INVALID')
print('FOUR_GRID=4/4 PASS',flush=True)
task=a.pdf_queue.submit(a.DATA_DIR,JOB_ID,rendered,'Judun_Professional_Report_QA.pdf')
key=task['key']
for step in range(150):
    t=a.pdf_queue.status(a.DATA_DIR,key)
    if t and t['status'] in ('complete','failed'):break
    time.sleep(2)
else:die('PDF_QUEUE_TIMEOUT')
if not t or t['status']!='complete':die('PDF_QUEUE_FAILED')
pdf=a.pdf_queue.cache_dir(a.DATA_DIR)/(key+'.pdf')
if not a.pdf_queue.pdf_is_usable(pdf):die('PDF_BYTES_INVALID')
size=pdf.stat().st_size
pages=None;tool='none'
if shutil.which('pdfinfo'):
    x=subprocess.run(['pdfinfo',str(pdf)],capture_output=True,text=True,timeout=20)
    m=re.search(r'^Pages:\s*(\d+)',x.stdout,re.M)
    if x.returncode==0 and m and int(m.group(1))>0:pages=int(m.group(1));tool='pdfinfo'
if pages is None:
    try:
        from pypdf import PdfReader
        pages=len(PdfReader(str(pdf),strict=True).pages);tool='pypdf'
    except ImportError:pass
    except Exception:die('PDF_STRUCTURE_BAD')
if pages is None:
    try:
        import fitz
        with fitz.open(str(pdf)) as doc:pages=len(doc)
        tool='pymupdf'
    except ImportError:pass
    except Exception:die('PDF_STRUCTURE_BAD')
if pages is None:
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf)) as doc:pages=len(doc.pages)
        tool='pdfplumber'
    except ImportError:pass
    except Exception:die('PDF_STRUCTURE_BAD')
if pages is None or pages<1:
    print('PDF_BYTES=PASS SIZE='+str(size),flush=True)
    print('PDF_STRUCTURE=NOT_VERIFIED_NO_READER',flush=True)
    print('RESULT=HOLD_PDF_STRUCTURE',flush=True)
else:
    print('PDF_BYTES=PASS SIZE='+str(size),flush=True)
    print('PDF_STRUCTURE=PASS PAGES='+str(pages)+' TOOL='+tool,flush=True)
    print('RESULT=STAGE_GRID_AND_PDF_STRUCTURE_PASS_VISUAL_QA_PENDING',flush=True)
'''

def main():
    jobid=preflight()
    _,cwd,cmd,env,uid,gid,groups,appdir,runners=stage_process()
    if uid==0:stop('STAGE_PROCESS_AS_ROOT_REQUIRES_REVIEW')
    env.update(PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
    chosen=None
    for candidate in runners:
        if not candidate.is_file() or not os.access(candidate,os.X_OK):continue
        try:
            pr=subprocess.run([str(candidate),'-I','-B','-c','import fastapi, sqlalchemy, google.genai'],cwd=str(appdir),env=env,user=uid,group=gid,extra_groups=groups,capture_output=True,text=True,timeout=12)
            if pr.returncode==0:chosen=candidate;break
        except Exception:continue
    if chosen is None:stop('STAGE_PYTHON_ENV_UNKNOWN')
    print('NATIVE_STAGE_PROCESS_AND_SOURCE=PASS',flush=True)
    r=subprocess.run([str(chosen),'-I','-B','-c',WORKER,str(appdir),jobid],cwd=str(appdir),env=env,user=uid,group=gid,extra_groups=groups,text=True,timeout=480)
    if r.returncode:stop('NATIVE_WORKER_FAILED_RC_'+str(r.returncode))
    b=get('/health/build');a=get('/health/artifact?deep=true');ready=get('/health/ready')
    if not (b.get('artifact_id')==a.get('artifact_id')==ART and a.get('files_verified')==98 and a.get('mismatch_count')==0 and ready.get('status')=='ready'):
        stop('STAGE_CHANGED_AFTER_QA')
    print('POST_QA_STAGE_98_98_READY=PASS',flush=True)
    print('PRODUCTION_NOT_TOUCHED=TRUE',flush=True)
if __name__=='__main__':main()