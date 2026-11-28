#!/usr/bin/env python3
"""Reconcile an existing, independently attested precheckpoint recovery receipt.
No business POST, replay, deployment, signing, or payment operation.
The original HOLD record is retained before the normal PASS record is reconciled.
"""
import hashlib, json, os, re, runpy, stat, subprocess, sys
from contextlib import ExitStack
from pathlib import Path

AUTO=Path("/opt/judun-stage-qa-auto/auto.py")
SUMMARY=Path("/srv/judun-stage-health-oidc/qa_receipt_summary.py")
AUTO_PIN="452ed674c51edf848c7bd4b90c2a5e0be318baa115487cdac4f4804728aeb108"
SUMMARY_PIN="b2443e0590b028e0efef9f8494e146bbf6d3f697507fc7c254f57efc22c866e7"
def need(ok,code):
    if not ok: raise ValueError(code)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def strict(raw):
    def pairs(items):
        d=dict(items); need(len(items)==len(d),"DUPLICATE_FIELD"); return d
    return json.loads(raw,object_pairs_hook=pairs)
def pinned(p,pin,private):
    s=p.lstat()
    need(stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1 and not s.st_mode&(0o077 if private else 0o022),"UNSAFE_TOOL")
    need(sha(p.read_bytes())==pin,"TOOL_PIN")
    return runpy.run_path(str(p),run_name="pinned_reconciliation")
def decision(artifact,tree,record,recovery,raw,proof):
    h=sha(raw)
    need(re.fullmatch(r"[a-f0-9]{64}",tree) is not None,"TREE")
    need(set(proof)=={"status","commit","identity","receipt_sha256"} and proof["status"]=="EXISTING_NATIVE_QA_PASS" and re.fullmatch(r"[a-f0-9]{40}",proof["commit"]) and proof["receipt_sha256"]==h,"SIGNED_PROBE")
    need(recovery=={"status":"PASS","tree":tree,"candidate_commit":proof["commit"],"receipt_sha256":h},"RECOVERY_BINDING")
    d=strict(raw); ident=d.get("identity")
    need(d.get("schema")=="judun.stage-native-business-qa.v1" and d.get("status")=="PASS" and ident==proof["identity"],"RECEIPT_BINDING")
    need(ident["artifact_id"]==artifact and ident["source_tree_sha256"]==tree and type(ident["count"]) is int and ident["count"]>0,"SNAPSHOT_BINDING")
    desired={"status":"PASS","artifact":artifact,"tree":tree,"receipt_sha256":h}
    if record==desired: return desired,False
    need(record=={"status":"HOLD","artifact":artifact,"tree":tree,"reason":record.get("reason")} and record.get("reason") in ("QA_EXIT_2","QA_EXIT_3"),"ORIGINAL_STATE")
    return desired,True
def self_test():
    import copy
    t="a"*64; c="b"*40; a="JUDUN-1.2.197-X"
    i={"artifact_id":a,"source_tree_sha256":t,"count":98,"version":"1.2.197","build_instance_id":"1.2.197-X"}
    raw=json.dumps({"schema":"judun.stage-native-business-qa.v1","status":"PASS","identity":i}).encode()
    h=sha(raw); old={"status":"HOLD","artifact":a,"tree":t,"reason":"QA_EXIT_2"}
    rec={"status":"PASS","tree":t,"candidate_commit":c,"receipt_sha256":h}
    proof={"status":"EXISTING_NATIVE_QA_PASS","commit":c,"identity":i,"receipt_sha256":h}
    inputs=[a,t,old,rec,raw,proof]
    new,changed=decision(*inputs); assert changed
    assert decision(a,t,new,rec,raw,proof)==(new,False)
    cases=[(2,{"status":"STARTED"}),(2,{**old,"reason":"TimeoutError"}),(3,{**rec,"status":"STARTED"}),(3,{**rec,"candidate_commit":"c"*40}),(3,{**rec,"receipt_sha256":"0"*64}),(4,raw+b" "),(5,{**proof,"status":"NATIVE_QA_PENDING"}),(5,{**proof,"identity":{**i,"count":97}}),(0,a+"OTHER"),(1,"d"*64)]
    for idx,val in cases:
        z=copy.deepcopy(inputs); z[idx]=val
        try: decision(*z)
        except (ValueError,KeyError,TypeError): pass
        else: raise AssertionError("unsafe case accepted")
    print("RECONCILE_SELF_TEST=12/12_PASS")
def main():
    need(os.geteuid()==0,"ROOT_REQUIRED"); os.umask(0o077)
    a=pinned(AUTO,AUTO_PIN,True); s=pinned(SUMMARY,SUMMARY_PIN,False)
    stage,pull,state,receipts,tools=(a[k] for k in ("STAGE","PULL","STATE","RECEIPTS","TOOLS"))
    for p in (state,receipts,tools):
        st=p.lstat(); need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not st.st_mode&0o077,"PRIVATE_DIRECTORY")
    a["verify_tool"](tools/"launcher.py",a["LAUNCHER_SHA"])
    a["verify_tool"](tools/"native_qa.py",a["QA_SHA"])
    with ExitStack() as locks:
        a["existing_lock"](locks,pull/".lock")
        a["existing_lock"](locks,stage/".lock")
        artifact,tree,key=a["snapshot"](stage)
        mark=state/(key+".json"); recovered=state/(key+".precheckpoint-v1.json")
        if not os.path.lexists(recovered):
            print("NO_PRECHECKPOINT_RECOVERY_RECORD"); return
        read=a["secure_read"]
        record=strict(read(mark)); recovery=strict(read(recovered))
        raw=read(receipts/(tree+".receipt.json"))
        # Original read-only launcher verifies the live signed pointer and receipt.
        p=subprocess.run([sys.executable,"-I","-B",str(tools/"launcher.py")],stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=120)
        need(p.returncode==0,"SIGNED_PROBE_FAILED")
        proofs=[]
        for line in p.stdout.splitlines():
            try: d=strict(line)
            except (ValueError,TypeError): continue
            if isinstance(d,dict) and d.get("status")=="EXISTING_NATIVE_QA_PASS": proofs.append(d)
        need(len(proofs)==1,"SIGNED_PROBE_MISSING")
        desired,changed=decision(artifact,tree,record,recovery,raw,proofs[0])
        archive=state/(key+".precheckpoint-original-hold.json")
        if changed:
            if os.path.lexists(archive): need(strict(read(archive))==record,"ARCHIVE_CONFLICT")
            else: a["atomic"](archive,record)
        else:
            need(os.path.lexists(archive),"ORIGINAL_HOLD_ARCHIVE_MISSING")
            prior=strict(read(archive))
            need(decision(artifact,tree,prior,recovery,raw,proofs[0])==(desired,True),"ARCHIVE_BINDING")
        need(a["snapshot"](stage)==(artifact,tree,key) and strict(read(mark))==record and strict(read(recovered))==recovery and read(receipts/(tree+".receipt.json"))==raw,"STATE_CHANGED")
        # A successful recovery is an actual original QA PASS, not a synthetic receipt.
        if changed: a["atomic"](mark,desired)
        result=s["publish"]()
        need(result["receipt_sha256"]==desired["receipt_sha256"],"SUMMARY_HASH")
        print("RECOVERED_NATIVE_QA_SUMMARY_PUBLISHED="+desired["receipt_sha256"],flush=True)
        print("FEATURE_AND_INDEPENDENT_QA_STILL_REQUIRED",flush=True)
if __name__=="__main__":
    if sys.argv[1:]==["--self-test"]: self_test()
    elif not sys.argv[1:]:
        try: self_test(); main()
        except (OSError,ValueError,TypeError,KeyError,subprocess.SubprocessError) as e:
            print("RECONCILIATION_HOLD:"+(str(e) if type(e) is ValueError and re.fullmatch("[A-Z_]{1,100}",str(e)) else type(e).__name__),flush=True)
            sys.exit(2)
    else: sys.exit(2)
