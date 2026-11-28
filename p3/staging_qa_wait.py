"""Bounded, read-only QA receipt wait after an exact protected staging request.
No business requests, deployment, signing, or release approval. Original two-pass
attestation is retained; a summary is only a signal to collect review evidence.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError

READY = 'EVIDENCE_READY_NOT_RELEASE_APPROVAL'
HEX = re.compile(r'[0-9a-f]{64}\Z')
MAX_SECONDS = 70 * 60
POLL_SECONDS = 90


def need(ok, code):
    if not ok:
        raise ValueError(code)


def hash_ok(s):
    return type(s) is str and HEX.fullmatch(s) is not None


def summaries_ready(native, feature, count, plan_sha):
    if not (native.get('native_qa_status') == 'PASS' and
            hash_ok(native.get('native_qa_receipt_sha256')) and
            type(native.get('native_qa_file_count')) is int and
            native['native_qa_file_count'] == count):
        return False
    if plan_sha is None:
        return True
    return (feature.get('feature_qa_status') == READY and
            feature.get('feature_plan_sha256') == plan_sha and
            hash_ok(feature.get('feature_receipt_sha256')))


def build_ready(b, target, plan_sha):
    need(type(b) is dict and b.get('status') == 'ok' and
         b.get('manifest_status') == 'ok' and b.get('payment_mode') == 'test_unlock' and
         b.get('version') in (target['expected_display_version'], target['expected_display_version'].removeprefix('v')) and
         b.get('artifact_id') == target['target_artifact_id'] and
         b.get('build_instance_id') == target['target_build_instance_id'] and
         b.get('source_tree_sha256') == target['expected_source_tree_sha256'],
         'QA_WAIT_STAGE_IDENTITY_DRIFT')
    return summaries_ready(b, b, target['expected_managed_file_count'], plan_sha)


def receipt_ready(r, target, commit, plan_sha):
    count = target['expected_managed_file_count']
    expected = {'version': target['expected_display_version'],
                'artifact_id': target['target_artifact_id'],
                'build_instance_id': target['target_build_instance_id'],
                'source_tree_sha256': target['expected_source_tree_sha256'],
                'managed_files': count, 'payment_mode': 'test_unlock'}
    need(r.get('schema') == 'judun.staging-request-readback.v1' and
         r.get('result') == 'PASS' and r.get('candidate_commit') == commit and
         r.get('first') == r.get('second') == expected and
         type(r.get('observed_seconds')) in (int, float) and
         math.isfinite(r['observed_seconds']) and r['observed_seconds'] >= 60 and
         math.isfinite(r['first_at_epoch']) and math.isfinite(r['second_at_epoch']) and
         r['second_at_epoch'] - r['first_at_epoch'] >= r['observed_seconds'] - 1,
         'QA_WAIT_READBACK_IDENTITY')
    native = r['native_qa']; feature = r['feature_qa']
    if not summaries_ready(native, feature, count, plan_sha):
        return False
    need(r['native_qa_first'] == r['native_qa_second'] == native,
         'QA_WAIT_NATIVE_UNSTABLE')
    if plan_sha is not None:
        builds = r.get('feature_qa_builds')
        need(type(builds) is list and len(builds) == 2 and
             all(build_ready(b, target, plan_sha) and
                 b['native_qa_receipt_sha256'] == native['native_qa_receipt_sha256'] and
                 b['feature_receipt_sha256'] == feature['feature_receipt_sha256'] for b in builds),
             'QA_WAIT_FEATURE_UNSTABLE')
    return True


def wait(commit, target, plan_sha, initial, *, pointer, read_build, attest, clock=time.monotonic, sleep=time.sleep,
         max_seconds=MAX_SECONDS, interval=POLL_SECONDS):
    need(type(max_seconds) is int and 0 < max_seconds <= MAX_SECONDS and
         type(interval) is int and 1 <= interval <= POLL_SECONDS, 'QA_WAIT_BOUNDS')
    need(pointer() == commit, 'QA_WAIT_SUPERSEDED')
    if receipt_ready(initial, target, commit, plan_sha):
        return initial, 'INITIAL_RECEIPT_ALREADY_READY'
    deadline = clock() + max_seconds
    transient = 0
    while True:
        remaining = deadline - clock()
        if remaining <= 0:
            raise TimeoutError('QA_WAIT_RECEIPT_TIMEOUT_HOLD')
        sleep(min(interval, remaining))
        if clock() >= deadline:
            raise TimeoutError('QA_WAIT_RECEIPT_TIMEOUT_HOLD')
        try:
            need(pointer() == commit, 'QA_WAIT_SUPERSEDED')
            ready = build_ready(read_build(), target, plan_sha)
        except (HTTPError, URLError, TimeoutError) as e:
            # Retry only read-only transport failures, not identity/auth failures.
            if isinstance(e, HTTPError) and e.code not in (429, 502, 503, 504):
                raise
            transient += 1
            if transient >= 3:
                raise
            continue
        transient = 0
        if ready:
            r = attest()
            need(pointer() == commit, 'QA_WAIT_SUPERSEDED')
            if receipt_ready(r, target, commit, plan_sha):
                return r, 'FRESH_TWO_PASS_RECEIPT_READY'
            # A changing summary is not approval; wait for the next stable one.


def main(commit):
    import staging_request_readback as rb
    import stage_oidc_client as oidc
    import staging_deploy_request as agent
    import feature_gate_policy as policy
    from feature_qa_contract import decode
    target = rb.signed_target(commit)
    paths = policy.paths(target)
    plan_sha = None
    if policy.required(target, lambda p: Path(p).is_file()):
        raw = Path(paths[0]).read_bytes()
        need(0 < len(raw) <= 8192, 'QA_WAIT_PLAN_SIZE')
        policy.signed(raw, Path(paths[1]).read_bytes(), Path('keys/release_signing_public.pem').read_bytes(), policy.ORIGINAL_PIN)
        plan = decode(raw)
        need(plan.get('schema') == 'judun.feature-qa-plan.v1' and plan.get('identity') == policy.target_identity(target), 'QA_WAIT_PLAN_IDENTITY')
        plan_sha = hashlib.sha256(raw).hexdigest()
    initial_path = Path(os.environ['RUNNER_TEMP']) / 'judun-staging-readback.json'
    ready_path = Path(os.environ['RUNNER_TEMP']) / 'judun-staging-qa-ready.json'
    need(not ready_path.exists(), 'QA_WAIT_OUTPUT_ALREADY_EXISTS')
    def attest():
        rb.attest(commit)
        return json.loads(initial_path.read_bytes())
    result, reason = wait(commit, target, plan_sha, json.loads(initial_path.read_bytes()),
        pointer=lambda: agent.request_commit(agent.fetch),
        read_build=lambda: oidc.fetch_health('/health/build', oidc.github_id_token()),
        attest=attest)
    ready_path.write_text(json.dumps(result, sort_keys=True) + '\n', encoding='utf-8')
    print('QA_WAIT_RECEIPT_READY_NOT_RELEASE_APPROVAL', reason, flush=True)


if __name__ == '__main__':
    need(len(sys.argv) == 2 and re.fullmatch(r'[a-f0-9]{40}', sys.argv[1]) is not None, 'QA_WAIT_COMMIT')
    main(sys.argv[1])
