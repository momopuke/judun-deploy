#!/usr/bin/env python3
"""One exact stage-only retry before the first business checkpoint; never delete state."""
import json, os, re, runpy, subprocess, sys
from pathlib import Path
from contextlib import ExitStack

TREE="3ce58d45734dd0681903413f3b8639747215d4007573c2c24a50a0f3a50f9172"
COMMIT="3aba2e3bde097f5362d5ab582a88aae0e7766df2"
ARTIFACT="JUDUN-1.2.197-CORE-PREVIEW-TIMEOUT-RECOVERY-20261128"
IDENTITY=dict(version="1.2.197",artifact_id=ARTIFACT,build_instance_id=ARTIFACT.removeprefix("JUDUN-"),source_tree_sha256=TREE,count=98)
AUTO="/opt/judun-stage-qa-auto/auto.py"
AUTO_PIN="452ed674c51edf848c7bd4b90c2a5e0be318baa115487cdac4f4804728aeb108"

def need(ok,code):
    if not ok: raise ValueError(code)

def parse(s):
    try:
        d=json.loads(s)
        return d if isinstance(d,dict) else {}
    except (TypeError,ValueError): return {}

def early(rows,record):
    # The original native QA emits EXACT_STAGE_IDENTITY with flush=True before
    # writing a checkpoint. An exact final HOLD plus an explicit early failure
    # in the same retained invocation is required, not merely a missing file.
    groups={}
    for row in rows:
        inv=row.get("_SYSTEMD_INVOCATION_ID","")
        msg=row.get("MESSAGE")
        if isinstance(inv,str) and re.fullmatch("[0-9a-f]{32}",inv) and isinstance(msg,str):
            groups.setdefault(inv,[]).append(msg)
    matches=[g for g in groups.values() if any(parse(m)==record for m in g)]
    need(len(matches)==1,"EARLY_INVOCATION_NOT_PROVEN")
    g=matches[0]
    need(not any(parse(m).get("check")=="EXACT_STAGE_IDENTITY" for m in g),"PRIOR_NATIVE_IDENTITY_REACHED")
    pending=[parse(m) for m in g if parse(m).get("status")=="NATIVE_QA_PENDING"]
    need(all(d.get("commit")==COMMIT and d.get("identity")==IDENTITY for d in pending),"PRIOR_PENDING_IDENTITY")
    errors=[]
    # A missing EXACT_STAGE_IDENTITY log alone is not enough (journal loss).
    # Only a launcher HOLD before it emits NATIVE_QA_PENDING, or an explicit
    # native check unique to the pre-checkpoint path, is positive evidence.
    for m in g:
        d=parse(m)
        e=d.get("error") if d.get("check")=="HOLD" else m.removeprefix("HOLD: ") if m.startswith("HOLD: ") else None
        if isinstance(e,str) and re.fullmatch("(?:STOP_[A-Z0-9_]{1,100}|[A-Za-z][A-Za-z0-9_]{0,60})",e):
            errors.append((e,d.get("check")=="HOLD"))
    need(len(errors)==1,"EARLY_FAILURE_CODE_NOT_PROVEN")
    e,native=errors[0]
    print("ORIGINAL_SANITIZED_FAILURE="+e,flush=True)
    unique_native={"STOP_ROOT_REQUIRED","STOP_EXPECTED_IDENTITY_FORMAT","STOP_QA_DIR_UNSAFE"}
    need((not native and not pending and e in {"Stop","ValueError","FileNotFoundError","HTTPError","URLError","TimeoutExpired","PermissionError"}) or
         (native and len(pending)==1 and e in unique_native),"PRECHECKPOINT_CAUSE_NOT_PROVEN")
    return e

def self_test():
    record={"status":"HOLD","artifact":ARTIFACT,"tree":TREE,"reason":"QA_EXIT_2"}
    inv="1"*32
    def rows(*messages):
        return [{"_SYSTEMD_INVOCATION_ID":inv,"MESSAGE":m} for m in messages]
    end=json.dumps(record)
    good=rows("HOLD: Stop",end)
    assert early(good,record)=="Stop"
    for sample in (rows(end),rows("HOLD: Stop",json.dumps({"check":"EXACT_STAGE_IDENTITY"}),end),rows("HOLD: Stop"),rows("HOLD: Stop","HOLD: ValueError",end),rows("HOLD: Stop",json.dumps({"status":"NATIVE_QA_PENDING","commit":"0"*40}),end),rows(json.dumps({"check":"HOLD","error":"STOP_FREE_TIMEOUT"}),end),rows("HOLD: Stop",json.dumps({"status":"NATIVE_QA_PENDING","commit":COMMIT,"identity":IDENTITY}),end)):
        try: early(sample,record)
        except ValueError: pass
        else: raise AssertionError("unsafe replay accepted")
    print("PRECHECKPOINT_POLICY_SELF_TEST=8/8_PASS",flush=True)

def main():
    need(os.geteuid()==0,"ROOT_REQUIRED")
    os.umask(0o077)
    import hashlib,stat
    p=Path(AUTO)
    st=p.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and not(st.st_mode&0o077),"AUTO_UNSAFE")
    need(hashlib.sha256(p.read_bytes()).hexdigest()==AUTO_PIN,"AUTO_PIN")
    a=runpy.run_path(AUTO,run_name="judun_pinned_auto")
    stage,pull,state,receipts,tools=(a[k] for k in ("STAGE","PULL","STATE","RECEIPTS","TOOLS"))
    for directory in (state,receipts,tools):
        st=directory.lstat()
        need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not(st.st_mode&0o077),"PRIVATE_DIRECTORY")
    launch=tools/"launcher.py"
    a["verify_tool"](launch,a["LAUNCHER_SHA"])
    a["verify_tool"](tools/"native_qa.py",a["QA_SHA"])
    with ExitStack() as locks:
        a["existing_lock"](locks,pull/".lock")
        a["existing_lock"](locks,stage/".lock")
        artifact,tree,key=a["snapshot"](stage)
        need((artifact,tree)==(ARTIFACT,TREE),"STAGE_IDENTITY")
        mark=state/(key+".json")
        retry=state/(key+".precheckpoint-v1.json")
        receipt=receipts/(TREE+".receipt.json")
        checkpoint=receipts/(TREE+".json")
        if os.path.lexists(receipt):
            d=json.loads(a["secure_read"](receipt))
            need(d.get("status")=="PASS" and d.get("identity")==IDENTITY,"RECEIPT_IDENTITY")
            print("EXACT_NATIVE_RECEIPT_ALREADY_PASS",flush=True);return
        need(not os.path.lexists(checkpoint) and not os.path.lexists(checkpoint.with_name(checkpoint.name+".tmp")),"CHECKPOINT_EXISTS_NO_REPLAY")
        need(not os.path.lexists(retry),"ONE_RETRY_ALREADY_RECORDED")
        record=json.loads(a["secure_read"](mark))
        need(record=={"status":"HOLD","artifact":ARTIFACT,"tree":TREE,"reason":record.get("reason")} and record.get("reason") in ("QA_EXIT_2","QA_EXIT_3"),"ORIGINAL_ATTEMPT_NOT_SAFE")
        j=subprocess.check_output(["journalctl","-u","judun-stage-native-qa-auto.service","--since","2026-11-28 07:39:00 UTC","--no-pager","-o","json","--output-fields=MESSAGE,_SYSTEMD_INVOCATION_ID"],timeout=20)
        need(0<len(j)<=4_000_000,"JOURNAL_SIZE")
        code=early([parse(line) for line in j.decode().splitlines()],record)
        print("ORIGINAL_PRECHECKPOINT_FAILURE="+code,flush=True)
        pre=subprocess.run([sys.executable,"-I","-B",AUTO,"--probe"],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=120)
        rows=[parse(m) for m in pre.stdout.splitlines()]
        ready=any(d.get("status")=="NATIVE_QA_PENDING" and d.get("commit")==COMMIT and d.get("identity")==IDENTITY and d.get("noninteractive_code_ready") is True and d.get("run_requested") is False for d in rows)
        if not (pre.returncode==0 and ready and "NONINTERACTIVE_STAGE_CODE=READY" in pre.stdout):
            for m in pre.stdout.splitlines():
                if re.fullmatch("HOLD: (?:STOP_[A-Z0-9_]{1,100}|[A-Za-z][A-Za-z0-9_]{0,60})",m): print("PREFLIGHT_"+m,flush=True)
            raise ValueError("CURRENT_READONLY_PREFLIGHT_HOLD")
        need(a["snapshot"](stage)==(artifact,tree,key) and not os.path.lexists(checkpoint) and not os.path.lexists(receipt),"STATE_CHANGED")
        need(json.loads(a["secure_read"](mark))==record,"ORIGINAL_STATE_CHANGED")
        a["atomic"](retry,{"status":"STARTED","tree":TREE,"candidate_commit":COMMIT,"original_early_code":code})
        print("ONE_EXACT_STAGE_ONLY_RETRY_STARTED",flush=True)
        rc=subprocess.run([sys.executable,"-I","-B",str(launch),"--run"],stdin=subprocess.DEVNULL,check=False,timeout=2700).returncode
        if rc==0 and os.path.lexists(receipt):
            d=json.loads(a["secure_read"](receipt))
            need(d.get("status")=="PASS" and d.get("identity")==IDENTITY,"RECEIPT_IDENTITY")
            a["atomic"](retry,{"status":"PASS","tree":TREE,"candidate_commit":COMMIT,"receipt_sha256":a["receipt_at"](receipts,ARTIFACT,TREE)})
            print("EXACT_NATIVE_QA_PASS_FEATURE_REVIEW_STILL_REQUIRED",flush=True);return
        a["atomic"](retry,{"status":"HOLD","tree":TREE,"candidate_commit":COMMIT,"exit_code":rc})
        raise ValueError("NATIVE_RETRY_HOLD_NO_REPEAT")

if __name__=="__main__":
    if sys.argv[1:]==["--self-test"]: self_test()
    elif not sys.argv[1:]:
        try: self_test();main()
        except (ValueError,BlockingIOError,FileNotFoundError,subprocess.SubprocessError,OSError) as e:
            msg=str(e) if type(e) is ValueError and re.fullmatch("[A-Z0-9_]{1,100}",str(e)) else type(e).__name__
            print("HOLD:"+msg,flush=True);sys.exit(2)
    else: sys.exit(2)
