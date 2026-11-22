#!/usr/bin/env python3
"""Fail-closed two-pass audit of an already signed Judun release.

Original signer, protected release PR, VPS pull-agent and rollback remain the
only deployment authority. This script cannot deploy, sign, pay or alter data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github' / 'scripts'))
import verify_release as trusted_verifier
import stage_oidc_client as stage_oidc

SCHEMA = 'judun-postrelease-two-pass.v1'
FIELDS = ('artifact_id', 'build_instance_id', 'version',
          'source_tree_sha256', 'managed_files')


class AttestationError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise AttestationError('POST_RELEASE_' + reason)


def strict_dict(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'RECEIPT_DUPLICATE_KEY')
        result[key] = value
    return result


def stable_hash():
    path = ROOT / 'channel' / 'stable.json'
    require(path.is_file() and not path.is_symlink(), 'CHANNEL_UNAVAILABLE')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(target, token, *, live=None, stage=None):
    """Read each site once, then reconfirm production to reject split-brain."""
    require(isinstance(token, str) and bool(token.strip()), 'STAGING_AUTH_MISSING')
    live = live or trusted_verifier.verify_target_live
    if stage is None:
        # This is OIDC identity from the *trusted* GitHub job, not a reusable
        # Sites SIWC owner bypass secret. No stage token is stored in Actions.
        stage = lambda item, unused, *, attempts: stage_oidc.verify_candidate(item)
    production = live(target, attempts=1)
    staging = stage(target, token, attempts=1)
    production_again = live(target, attempts=1)
    require(production == production_again, 'PRODUCTION_CHANGED_DURING_CHECK')
    require(isinstance(production, dict) and isinstance(staging, dict),
            'SITE_RECEIPT_INVALID')
    for name in FIELDS:
        require(production.get(name) == staging.get(name),
                'SITE_IDENTITY_MISMATCH_' + name.upper())
    require(production.get('payment_mode') == 'ecpay_live',
            'PRODUCTION_PAYMENT_MODE')
    require(staging.get('payment_mode') == 'test_unlock',
            'STAGING_PAYMENT_MODE')
    return {
        'production': {k: production[k] for k in (*FIELDS, 'payment_mode')},
        'staging': {k: staging[k] for k in (*FIELDS, 'payment_mode')},
    }


def receipt(target, token, *, now=None, verifier=None, collector=None):
    verifier = verifier or trusted_verifier.verify_package
    collector = collector or collect
    require(bool(token), 'STAGING_AUTH_MISSING')
    signed = verifier()
    require(isinstance(signed, dict) and signed.get('release_id') == target['release_id'],
            'SIGNED_CHANNEL_CHANGED')
    pinned_manifest = stable_hash()
    sites = collector(signed, token)
    require(stable_hash() == pinned_manifest, 'CHANNEL_CHANGED_DURING_READ')
    return {
        'schema': SCHEMA,
        'signed_manifest_sha256': pinned_manifest,
        'release_id': signed['release_id'],
        'checked_at_epoch': time.time() if now is None else now,
        'sites': sites,
    }


def validate_pair(first, second, hold_seconds=60):
    require(type(first) is dict and type(second) is dict, 'RECEIPT_NOT_OBJECT')
    fields = {'schema', 'signed_manifest_sha256', 'release_id',
              'checked_at_epoch', 'sites'}
    require(set(first) == fields and set(second) == fields, 'RECEIPT_FIELDS')
    require(first['schema'] == second['schema'] == SCHEMA, 'RECEIPT_SCHEMA')
    for field in ('signed_manifest_sha256', 'release_id', 'sites'):
        require(first[field] == second[field], 'ONE_MINUTE_DRIFT_' + field.upper())
    earlier, later = first['checked_at_epoch'], second['checked_at_epoch']
    require(type(earlier) in (int, float) and type(later) in (int, float),
            'RECEIPT_TIME_INVALID')
    require(0 <= earlier <= later <= earlier + 3600,
            'RECEIPT_TIME_OUT_OF_RANGE')
    require(later - earlier >= hold_seconds, 'ONE_MINUTE_NOT_ELAPSED')
    return True


def final_evidence(first, minute):
    """Only a verified second pass creates a durable nonsecret PASS artifact."""
    validate_pair(first, minute)
    return {
        'schema': 'judun-postrelease-final-evidence.v1',
        'result': 'PASS',
        'release_id': minute['release_id'],
        'signed_manifest_sha256': minute['signed_manifest_sha256'],
        'first': first,
        'minute': minute,
        'observed_seconds': round(
            minute['checked_at_epoch'] - first['checked_at_epoch'], 3),
    }


def write_receipt(path, data):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def read_receipt(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 32768
            and info.st_mode & 0o077 == 0, 'RECEIPT_FILE_UNTRUSTED')
    return json.loads(path.read_text('utf-8'), object_pairs_hook=strict_dict)


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=('initial', 'minute'), required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--final-receipt', type=Path)
    args = parser.parse_args()
    try:
        # The placeholder is only an internal API guard; never a credential.
        # The actual short-lived JWT is minted by stage_oidc_client from
        # ACTIONS_ID_TOKEN_REQUEST_URL/TOKEN inside each trusted CI job.
        token = 'OIDC_JOB_IDENTITY'
        target = trusted_verifier.verify_package()
        current = receipt(target, token, verifier=lambda: target)
        if args.phase == 'initial':
            require(args.final_receipt is None, 'FINAL_RECEIPT_ONLY_AFTER_RECHECK')
            write_receipt(args.receipt, current)
            print('JUDUN_SIGNED_DUAL_SITE_INITIAL_PASS', current['release_id'], flush=True)
        else:
            require(args.final_receipt is not None, 'FINAL_RECEIPT_PATH_REQUIRED')
            require(args.final_receipt != args.receipt, 'RECEIPT_PATH_COLLISION')
            first = read_receipt(args.receipt)
            final = final_evidence(first, current)
            write_receipt(args.final_receipt, final)
            print('JUDUN_SIGNED_DUAL_SITE_ONE_MINUTE_PASS', current['release_id'],
                  flush=True)
        return 0
    except (AttestationError, ValueError, OSError, KeyError, TypeError) as exc:
        # Print only fixed failure identifiers, never URLs, credentials or payloads.
        reason = str(exc)
        if reason.startswith(('POST_RELEASE_', 'DIRECT_DEPLOY_')):
            reason = reason.split(':', 1)[0].split(' ', 1)[0][:120]
            if not reason.replace('_', '').isalnum() or not reason.isascii():
                reason = 'POST_RELEASE_UNVERIFIED'
        else:
            reason = 'POST_RELEASE_UNVERIFIED'
        print(reason, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(run())
