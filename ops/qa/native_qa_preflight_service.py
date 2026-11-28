#!/usr/bin/env python3
"""Native staging QA service entry: reuse original locks/state/receipt logic.
Installed original auto.py, launcher.py, native_qa.py and their trust pins are unchanged.
"""
import hashlib, json, os, re, runpy, stat, subprocess, sys
from pathlib import Path

ROOT=Path('/opt/judun-stage-qa-auto')
AUTO=ROOT/'auto.py'
AUTO_PIN='452ed674c51edf848c7bd4b90c2a5e0be318baa115487cdac4f4804728aeb108'
NEW=ROOT/'launcher_preflight_v2.py'
NEW_PIN='32191eda7dcb118033a844800fe738ea0a1419fc2d1708e7b87a2c5b99b115c9'

def need(ok,code):
    if not ok: raise ValueError(code)

def execute(a,invoke):
    # Same canonical state/locks and no separate recovery record. Original
    # systemd ExecStartPost still publishes the native summary after PASS.
    state=a['STATE']
    st=state.lstat()
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not(st.st_mode&0o077),'STATE_UNSAFE')
    result=a['once'](a['STAGE'],a['PULL'],state,a['RECEIPTS'],invoke)
    print(json.dumps(result,sort_keys=True),flush=True)
    return 2 if result.get('status')=='HOLD' else 0

def main():
    need(os.geteuid()==0,'ROOT_REQUIRED'); os.umask(0o077)
    st=ROOT.lstat()
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and not(st.st_mode&0o077),'TOOL_DIR_UNSAFE')
    st=AUTO.lstat()
    need(stat.S_ISREG(st.st_mode) and st.st_uid==0 and st.st_nlink==1 and not(st.st_mode&0o077),'AUTO_UNSAFE')
    need(hashlib.sha256(AUTO.read_bytes()).hexdigest()==AUTO_PIN,'AUTO_PIN')
    a=runpy.run_path(str(AUTO),run_name='judun_original_auto')
    for path,pin in ((ROOT/'launcher.py',a['LAUNCHER_SHA']),(ROOT/'native_qa.py',a['QA_SHA']),(NEW,NEW_PIN)):
        a['verify_tool'](path,pin)
    return execute(a,lambda:subprocess.run([sys.executable,'-I','-B',str(NEW),'--run'],stdin=subprocess.DEVNULL,check=False).returncode)

if __name__=='__main__':
    try: sys.exit(main())
    except Exception as e:
        msg=str(e) if type(e) is ValueError and re.fullmatch('[A-Z_]{1,100}',str(e)) else type(e).__name__
        print('NATIVE_QA_SERVICE_HOLD:'+msg,flush=True)
        sys.exit(2)
