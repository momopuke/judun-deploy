#!/usr/bin/env python3
"""Zero-write, no-secrets inventory of the original v190 production installer.

Only read three health endpoints on both existing sites, systemd service state,
and allowlisted release metadata in the original production deploy directories.
Never run install, decrypt, restart, write production files, or read private keys.
"""
from pathlib import Path
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
import hashlib
import json
import os
import subprocess

PROD = 'https://judun.142-93-91-214.sslip.io'
STAGE = 'http://127.0.0.1:8011'
V190 = ('1.2.190', 'JUDUN-1.2.190-SINGLEPASS-RC1-UNSIGNED',
        '1d5a73989525643a4da6c58b36263bdcc644a3f3780fb335b968e33e7de7866a', 'ecpay_live')
V191 = ('1.2.191', 'JUDUN-1.2.191-PIPELINE-CANARY-20261124',
        '141654ca761a07e3ec56cf8417403adfa69f4414098e890a860338532dbe1fd8', 'test_unlock')
PIN = '17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None

OPENER = build_opener(ProxyHandler({}), NoRedirect())

def get_json(origin, path):
    url = origin + path
    with OPENER.open(Request(url, headers={'Cache-Control':'no-cache'}), timeout=8) as response:
        raw = response.read(65537)
        if response.status != 200 or response.geturl() != url or len(raw) > 65536:
            raise ValueError('http_status_origin_or_size')
        obj = json.loads(raw)
        if type(obj) is not dict:
            raise ValueError('invalid_json_shape')
        return obj

def health(origin, expected):
    version, artifact, tree, mode = expected
    try:
        b = get_json(origin, '/health/build')
        d = get_json(origin, '/health/artifact?deep=true')
        ready = get_json(origin, '/health/ready')
        fields_ok = all(x.get('version', '').removeprefix('v') == version and
                        x.get('artifact_id') == artifact and
                        x.get('source_tree_sha256') == tree for x in (b, d))
        files_ok = d.get('deep_verified') is True and d.get('files_verified') == 98 and \
            d.get('manifest_file_count') == 98 and d.get('mismatch_count') == 0
        ready_ok = ready.get('status') == 'ready'
        mode_ok = b.get('payment_mode') == mode
        return {'result':'PASS' if all((fields_ok,files_ok,ready_ok,mode_ok)) else 'HOLD',
                'version': b.get('version'), 'deep_files':d.get('files_verified'),
                'payment_mode':b.get('payment_mode'), 'identity_match':fields_ok,
                'ready':ready_ok}
    except Exception as e:
        return {'result':'NOT_VERIFIED','reason':type(e).__name__}

def sha_limited(p, limit=2_000_000):
    if p.is_symlink() or not p.is_file() or p.stat().st_size > limit:
        return None
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(262144), b''):
            h.update(block)
    return h.hexdigest()

def systemd_state(unit):
    result = subprocess.run(['systemctl', 'is-active', unit],
                            capture_output=True, text=True, timeout=8, check=False)
    return result.stdout.strip()[:30] or 'unavailable'

def inventory_contract():
    # No global filesystem search: avoid customer storage, credentials and large recordings.
    roots = (Path('/opt/judun-autodeploy'), Path('/var/lib/judun-autodeploy'))
    matches=[]
    directories=0
    for base in roots:
        if not base.is_dir() or base.is_symlink():
            continue
        for current, subdirs, names in os.walk(base, followlinks=False):
            directories += 1
            if directories > 1000:
                break
            here=Path(current)
            depth=len(here.relative_to(base).parts)
            subdirs[:] = [n for n in subdirs if depth < 7 and n not in
                          ('keys','private','secrets','venv','.git','node_modules','cache')
                          and not (here/n).is_symlink()]
            if 'release.json' not in names:
                continue
            p=here/'release.json'
            if not (p.is_file() and not p.is_symlink() and p.stat().st_size < 16_384):
                continue
            try:
                item=json.loads(p.read_bytes())
            except (ValueError, OSError):
                continue
            if not isinstance(item,dict) or item.get('target_artifact_id')!=V190[1]:
                continue
            inspect={}
            for n in ('release.json','apply.sh','runtime_apply_v190.py','runtime_apply_v189.py','base_manifest.json'):
                f=here/n
                digest=sha_limited(f)
                if digest:
                    inspect[n]={'sha256':digest,'size':f.stat().st_size}
            matches.append({'source_directory':str(here), 'files':inspect,
                            'release_id':item.get('release_id'),
                            'base_artifact_id':item.get('base_artifact_id'),
                            'target_artifact_id':item.get('target_artifact_id'),
                            'target_source_tree_sha256':item.get('target_source_tree_sha256'),
                            'target_file_count':item.get('target_file_count'),
                            'changed_paths':item.get('changed_paths'),
                            'new_paths':item.get('new_paths')})
            if len(matches)>=5:
                break
    return {'v190_original_contract_count':len(matches),
            'v190_original_contracts':matches}

def main():
    # Guard: this is a read-only metadata probe, never a deployment entrypoint.
    public=Path('/opt/judun-autodeploy/keys/release_signing_public.pem')
    out={
        'schema':'judun.v191.production-original-contract-readonly.v1',
        'production':health(PROD,V190),
        'staging':health(STAGE,V191),
        'production_timer':systemd_state('judun-autodeploy.timer'),
        'stage_pull_timer':systemd_state('judun-staging-pull.timer'),
        'original_public_key_pin':'PASS' if sha_limited(public,4096)==PIN else 'NOT_VERIFIED',
        'original_agent_sha256':sha_limited(Path('/opt/judun-autodeploy/agent.sh'),256000),
    }
    out.update(inventory_contract())
    out['gate']='CONTRACT_FOUND' if (out['v190_original_contract_count'] and
        out['production']['result']=='PASS' and out['staging']['result']=='PASS' and
        out['original_public_key_pin']=='PASS') else 'HOLD_NEED_EXACT_INSTALLER_SOURCE'
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, indent=2))

if __name__=='__main__':
    main()