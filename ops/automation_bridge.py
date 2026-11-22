#!/usr/bin/env python3
"""Read-only proof of the existing Judun staging pull link. No deployment rights.

This probe intentionally does not certify the private signer, independent QA,
production deployment, or a completed release. It never prints credentials.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path('/srv/judun-staging')
CONF = Path('/etc/judun-staging-pull')
KEY_PIN = '17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'
REQUEST = 'https://raw.githubusercontent.com/momopuke/judun-deploy/main/ops/staging-request.json'

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def regular_root_file(path, *, secret=False, pin=None):
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
            return False
        if info.st_mode & (0o077 if secret else 0o022):
            return False
        if not 0 < info.st_size <= (4096 if secret or pin else 256 * 1024):
            return False
        if pin:
            return hashlib.sha256(path.read_bytes()).hexdigest() == pin
        return True
    except (OSError, ValueError):
        return False

def root_marker(path):
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not (info.st_mode & 0o022)
    except OSError:
        return False

def unit_ok(name, operation, run=subprocess.run):
    try:
        result = run(['systemctl', operation, '--quiet', name], timeout=6,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False

def unique_dict(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result

def request_channel_ok(opener=None):
    try:
        if opener is None:
            opener = build_opener(ProxyHandler({}), NoRedirect())
        response = opener.open(Request(REQUEST, headers={
            'Cache-Control': 'no-cache',
        }), timeout=8)
        with response:
            if response.status != 200 or response.geturl() != REQUEST:
                return False
            raw = response.read(2049)
        if len(raw) > 2048 or not raw:
            return False
        data = json.loads(raw, object_pairs_hook=unique_dict)
        if not isinstance(data, dict) or set(data) != {'candidate_commit'}:
            return False
        commit = data['candidate_commit']
        return commit is None or (isinstance(commit, str) and
                re.fullmatch(r'[0-9a-f]{40}', commit) is not None)
    except (OSError, ValueError, UnicodeError, TypeError):
        return False

def check(root=ROOT, conf=CONF, service_check=unit_ok, channel_check=request_channel_ok):
    checks = {
        'original_prod_timer_enabled': service_check('judun-autodeploy.timer', 'is-enabled'),
        'original_prod_timer_active': service_check('judun-autodeploy.timer', 'is-active'),
        'isolated_stage_service_active': service_check('judun-staging-isolated.service', 'is-active'),
        'isolated_stage_marker': root_marker(root / 'isolated.enabled'),
        'stage_request_agent_installed': regular_root_file(root / 'staging_deploy_request.py'),
        'stage_snapshot_manager_installed': regular_root_file(root / 'staging_release.py'),
        'stage_pull_timer_enabled': service_check('judun-staging-pull.timer', 'is-enabled'),
        'stage_pull_timer_active': service_check('judun-staging-pull.timer', 'is-active'),
        'stage_signing_public_key_pinned': regular_root_file(conf / 'release_signing_public.pem', pin=KEY_PIN),
        'stage_recipient_cert_installed': regular_root_file(conf / 'recipient.pem'),
        'stage_recipient_private_key_protected': regular_root_file(conf / 'recipient-key.pem', secret=True),
        'github_staging_request_reachable': channel_check(),
    }
    # A correct pull link is a necessary condition only: it is not Gate 0 PASS.
    return {
        'schema': 'judun.automation-bridge-readiness.v1',
        'bridge': 'READY' if all(checks.values()) else 'BLOCKED',
        'checks': {key: 'PASS' if value else 'FAIL' for key, value in checks.items()},
        'full_release_gate0': 'NOT_VERIFIED',
        'not_proven': ['private_signer_real_self_test', 'staging_paid_e2e_and_independent_qa',
                       'production_agent_authorized_install', 'dual_site_live_and_rollback'],
    }

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='print a machine-readable sanitized report')
    args = parser.parse_args()
    result = check()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        print('JUDUN_AUTOMATION_BRIDGE=' + result['bridge'])
        for name, state in result['checks'].items():
            print(f'{name}={state}')
        print('FULL_RELEASE_GATE0=NOT_VERIFIED')
    return 0 if result['bridge'] == 'READY' else 2

if __name__ == '__main__':
    raise SystemExit(main())
