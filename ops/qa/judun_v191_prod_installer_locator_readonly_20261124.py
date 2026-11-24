#!/usr/bin/env python3
"""Read-only, bounded locator for original Judun production installer contracts.

Does not execute releases, access DB/customer data or secrets, decrypt CMS,
read private keys, modify files, or print executable contents/env values.
"""
from pathlib import Path
import hashlib
import json
import os
import stat

ORIGINAL_AGENT_PIN = '403145fdbefc0d634d61d23ec5a9861e318927fc454ce4c32862eaaca6bf2d3c'
ROOTS = [
 '/opt/judun-autodeploy',
 '/var/lib/judun-autodeploy',
 '/srv/judun-staging/releases',
 '/root/judun-v190-signer-recovery',
]
SKIP = {'keys','private','secrets','.git','venv','.venv','node_modules','__pycache__','mail-outbox','customer','customers','database','databases','uploads','recordings','logs','log','cache'}
INSTALLER_FILES = {'release.json','apply.sh','runtime_apply_v189.py','runtime_apply_v190.py','runtime_apply_v191.py','verify_live_v189.py','verify_live_v190.py','verify_live_v191.py','base_manifest.json'}
ALLOW_FIELDS = ('release_id','base_artifact_id','target_artifact_id','target_build_instance_id','target_source_tree_sha256','target_file_count','status')

def digest(path,limit=3_000_000):
    try:
        st=path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_size>limit or st.st_nlink!=1:
            return None
        h=hashlib.sha256()
        with path.open('rb') as f:
            while True:
                chunk=f.read(65536)
                if not chunk:break
                h.update(chunk)
        return {'sha256':h.hexdigest(),'size':st.st_size}
    except (OSError,PermissionError):
        return None

def main():
    agent=Path('/opt/judun-autodeploy/agent.sh')
    a=digest(agent,300000)
    out={
      'schema':'judun.v191.production-installer-locator-readonly.v1',
      'original_agent_pin':'PASS' if a and a['sha256']==ORIGINAL_AGENT_PIN else 'HOLD_AGENT_SHA_MISMATCH',
      'roots':{},
      'installer_candidates':[],
      'agent_contract_tokens':{},
    }
    if out['original_agent_pin']!='PASS':
        out['gate']='HOLD_AGENT_CHANGED'
        print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True));return
    content=agent.read_text(encoding='utf-8',errors='replace')
    # Only token presence is output, never source lines, shell env values or secrets.
    for word in ('release.json','apply.sh','runtime_apply','JUDUN_APP_DIR','JUDUN_RELEASE_DIR','JUDUN_RELEASE_ID',
                 'JUDUN_TARGET_ARTIFACT_ID','JUDUN_BASE_ARTIFACT_ID','JUDUN_TARGET_BUILD_INSTANCE_ID',
                 'cms','openssl','rollback','systemctl'):
        out['agent_contract_tokens'][word]=bool(word in content)
    count=0
    for origin in ROOTS:
        base=Path(origin)
        info={'exists':base.is_dir() and not base.is_symlink(),'directories_examined':0,'files_matched':0,'limited':False}
        out['roots'][origin]=info
        if not info['exists']:continue
        for current,subdirs,names in os.walk(base,followlinks=False):
            info['directories_examined']+=1
            count+=1
            if count>1600:
                info['limited']=True
                break
            here=Path(current)
            depth=len(here.relative_to(base).parts)
            subdirs[:]=[s for s in subdirs if depth<8 and s not in SKIP and not (here/s).is_symlink()]
            for name in sorted(INSTALLER_FILES.intersection(names)):
                p=here/name
                identity=digest(p)
                if not identity:continue
                item={'path':str(p),'name':name,**identity}
                if name=='release.json' and identity['size']<=16384:
                    try:
                        raw=json.loads(p.read_bytes())
                        if isinstance(raw,dict):
                            item['contract']={key:raw.get(key) for key in ALLOW_FIELDS if key in raw}
                            for k in ('changed_paths','new_paths'):
                                v=raw.get(k)
                                if isinstance(v,list) and len(v)<=100 and all(isinstance(s,str) and len(s)<150 for s in v):
                                    item[k]=v
                    except (ValueError,OSError):item['contract_parse']='INVALID'
                out['installer_candidates'].append(item)
                info['files_matched']+=1
                if len(out['installer_candidates'])>=80:
                    info['limited']=True
                    break
            if info['limited']:break
        if count>1600 or len(out['installer_candidates'])>=80:break
    out['v190_contract_matches']=sum(1 for o in out['installer_candidates'] if
       o.get('name')=='release.json' and o.get('contract',{}).get('target_artifact_id')=='JUDUN-1.2.190-SINGLEPASS-RC1-UNSIGNED')
    out['gate']='READONLY_LOCATOR_COMPLETE_NO_AUTHORIZATION_TO_DEPLOY'
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
if __name__=='__main__':main()
