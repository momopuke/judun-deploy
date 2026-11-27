"""Verify a release PR from Git objects without checking out candidate code."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import direct_deploy_publish as release
import stage_oidc_client as oidc
import feature_gate_policy as feature_policy


MANIFEST = "channel/stable.json"
SIGNATURE = "channel/stable.json.sig.b64"
KEY = "keys/release_signing_public.pem"
CONTEXT = "judun/release-gate"
GIT_SHA = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_ROOTS = {"channel", "keys", "releases"}


def git(*args):
    return subprocess.check_output(
        ["git", "--no-replace-objects", *args], stderr=subprocess.DEVNULL, timeout=90
    )


def read_blob(commit, path, max_bytes):
    entry = git("ls-tree", "-z", commit, "--", path)
    if not entry.startswith(b"100644 blob ") or entry.count(b"\0") != 1:
        release.deny("PR_EXPECTED_REGULAR_FILE")
    object_name = f"{commit}:{path}"
    size = int(git("cat-file", "-s", object_name))
    if not 0 < size <= max_bytes:
        release.deny("PR_FILE_SIZE")
    return git("cat-file", "blob", object_name)


def read_signed_package(commit, public_key, *, historical=False):
    manifest = read_blob(commit, MANIFEST, 8192)
    metadata = json.loads(manifest)
    path = metadata.get("payload_path") if isinstance(metadata, dict) else None
    if not isinstance(path, str) or not release.PAYLOAD_PATH.fullmatch(path):
        release.deny("PR_INVALID_PAYLOAD_PATH")
    parsed = release.parse_signed_manifest(
        manifest, read_blob(commit, SIGNATURE, 1024),
        read_blob(commit, path, 30_000_000), public_key,
    )
    release.expected_target_integrity(parsed)
    release.expected_candidate_receipt(parsed, allow_v189=historical)
    return parsed


def classify_and_verify(base, head, same_repository, *,
                        check_live=True, check_stage=False):
    """Return the checked scope. Never execute files from head."""
    if not all(isinstance(sha, str) and GIT_SHA.fullmatch(sha) for sha in (base, head)):
        release.deny("PR_INVALID_COMMIT")
    fork_point = git("merge-base", base, head).decode("ascii").strip()
    if not GIT_SHA.fullmatch(fork_point):
        release.deny("PR_UNVERIFIED_MERGE_BASE")
    fields = git("diff", "--no-ext-diff", "--no-renames", "--name-status", "-z",
                 fork_point, head, "--").decode("utf-8").split("\0")
    if not fields or fields.pop() != "" or len(fields) % 2:
        release.deny("PR_UNREADABLE_FILE_CHANGES")
    changes = {path: status for status, path in zip(fields[::2], fields[1::2], strict=True)}
    if len(changes) != len(fields) // 2:
        release.deny("PR_DUPLICATE_FILE_CHANGE")
    if not any(path.split("/", 1)[0] in RELEASE_ROOTS for path in changes):
        return "non-release PR"
    if not same_repository:
        release.deny("PR_RELEASE_FORK_FORBIDDEN")
    if changes.get(MANIFEST) != "M" or changes.get(SIGNATURE) != "M" or len(changes) != 3:
        release.deny("PR_RELEASE_FILE_SET")
    new_payload = next(path for path in changes if path not in {MANIFEST, SIGNATURE})
    if (changes[new_payload] != "A" or not release.PAYLOAD_PATH.fullmatch(new_payload)
            or git("ls-tree", "-z", base, "--", new_payload)):
        release.deny("PR_RELEASE_PAYLOAD_MUST_BE_NEW")

    key = read_blob(base, KEY, 4096)
    if hashlib.sha256(key).hexdigest() != release.RELEASE_KEY_SHA256:
        release.deny("PR_INVALID_PINNED_KEY")
    with tempfile.TemporaryDirectory(prefix="judun-pr-gate-") as directory:
        public_key = Path(directory) / "public.pem"
        public_key.write_bytes(key)
        current = read_signed_package(base, public_key, historical=True)
        candidate = read_signed_package(head, public_key)
    if candidate["payload_path"] != new_payload:
        release.deny("PR_RELEASE_PAYLOAD_PATH_MISMATCH")
    if candidate["base_artifact_id"] != current["target_artifact_id"]:
        release.deny("PR_RELEASE_STALE_SIGNED_BASE")
    if check_live:
        release.verify_target_live(current, attempts=1)
    if check_stage:
        # Trust only a short-lived GitHub Actions OIDC identity accepted by
        # the isolated loopback-only stage health gateway, never a Sites owner
        # login bypass or an arbitrary bearer from untrusted PR code.
        feature_required = feature_policy.required(
            candidate, lambda path: bool(git("ls-tree", "-z", base, "--", path)))
        opts = {"include_native_qa": True}
        if feature_required:
            opts["include_feature_qa"] = True
        attested = oidc.verify_candidate(candidate, **opts)
        proof = oidc.native_qa_summary(attested.get("native_qa", {}),
                                      candidate["expected_managed_file_count"])
        if proof["native_qa_status"] != "PASS":
            release.deny("PR_NATIVE_QA_REQUIRED")
        if feature_required:
            digest = feature_policy.verify(candidate, lambda path, limit: read_blob(base, path, limit),
                                           key, attested, pin=release.RELEASE_KEY_SHA256)
            print("PR_FEATURE_INDEPENDENT_REVIEW_VERIFIED", digest, flush=True)
        print("PR_EXACT_CANDIDATE_STAGING_OIDC_VERIFIED", candidate["release_id"], flush=True)
        print("PR_NATIVE_QA_VERIFIED", proof["native_qa_receipt_sha256"],
              proof["native_qa_file_count"], flush=True)
    return "signed release PR"


def run():
    token = os.environ["GITHUB_TOKEN"]
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    request = event["pull_request"]
    number = request["number"]
    head = request["head"]["sha"]
    if (os.environ["GITHUB_REPOSITORY"] != release.REPO
            or request["base"]["ref"] != "main"
            or type(number) is not int or number < 1
            or not isinstance(head, str) or not GIT_SHA.fullmatch(head)):
        release.deny("PR_WRONG_EVENT")
    run_id = os.environ["GITHUB_RUN_ID"]
    if not re.fullmatch(r"[0-9]+", run_id):
        release.deny("PR_INVALID_RUN_ID")

    def status(state, description):
        release.github("POST", "/statuses/" + head, token, {
            "state": state, "context": CONTEXT, "description": description,
            "target_url": f"https://github.com/{release.REPO}/actions/runs/{run_id}",
        })

    status("pending", "Verifying the release boundary")
    try:
        # Pin the event head after fetching the base and head as objects only.
        git("fetch", "--no-tags", "origin", "+refs/heads/main:refs/judun/gate-base",
            f"+refs/pull/{number}/head:refs/judun/gate-head")
        base = git("rev-parse", "refs/judun/gate-base").decode("ascii").strip()
        observed = git("rev-parse", "refs/judun/gate-head").decode("ascii").strip()
        if observed != head:
            release.deny("PR_HEAD_CHANGED")
        head_repo = request["head"].get("repo") or {}
        scope = classify_and_verify(
            base, head, head_repo.get("full_name") == release.REPO,
            check_stage=True,
        )
        if scope == "signed release PR":
            git("fetch", "--no-tags", "origin", "+refs/heads/main:refs/judun/gate-base")
            latest = git("rev-parse", "refs/judun/gate-base").decode("ascii").strip()
            # Normal code/docs merges are fine. A concurrent release change
            # requires rerunning against the new, verified production base.
            target = json.loads(read_blob(head, MANIFEST, 8192))
            for path in (MANIFEST, SIGNATURE, KEY, *feature_policy.paths(target)):
                if git("ls-tree", "-z", latest, "--", path) != git("ls-tree", "-z", base, "--", path):
                    release.deny("PR_BASE_RELEASE_CHANGED")
    except Exception as error:
        status("failure", "Release boundary rejected; inspect verification run")
        if str(error).startswith("DIRECT_DEPLOY_"):
            print(str(error), flush=True)
        elif str(error) == "PR_NATIVE_QA_REQUIRED":
            print("PR_NATIVE_QA_REQUIRED", flush=True)
        elif isinstance(error, oidc.Denied):
            # Only fixed, non-secret codes from the trusted OIDC client.
            allowed = {"OIDC_RUNNER_BOOTSTRAP_MISSING", "OIDC_RUNNER_ORIGIN_REJECTED",
                       "OIDC_RUNNER_BOOTSTRAP_SIZE_REJECTED", "OIDC_RUNNER_BOOTSTRAP_CHARACTERS_REJECTED",
                       "JUDUN_STAGE_OIDC_UNVERIFIED"}
            code = str(error)
            print("PR_RELEASE_GATE_OIDC_DENIED", code if code in allowed else "UNKNOWN", flush=True)
        else:
            print("PR_RELEASE_GATE_ERROR", type(error).__name__, flush=True)
        return 1
    status("success", "Verified " + scope)
    print("PR_RELEASE_GATE_PASS", scope, head, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
