"""Submit an existing trusted, signed JUDUN release as an atomic pull request.

Requires an already approved CMS release produced by the ORIGINAL private
source builder and Ed25519 signer; never creates or reads signing private keys.
The existing VPS pull-agent performs its own base match, backup, and deep SHA.
Default action is preflight only. --publish opens a PR without merging it.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

REPO = "momopuke/judun-deploy"
API = "https://api.github.com/repos/" + REPO
LIVE = "https://judun.142-93-91-214.sslip.io"
STAGING = "https://judun-test.tony870490.chatgpt.site"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ARTIFACT = re.compile(r"JUDUN-1\.2\.\d+-[A-Za-z0-9_-]{6,80}\Z")
PAYLOAD_PATH = re.compile(r"releases/[A-Za-z0-9._-]+\.cms\.b64\Z")
RELEASE_KEY_SHA256 = "17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db"
V189_RELEASE = {
    "schema": "judun-autodeploy-v1",
    "release_id": "v1.2.189-startup-fix-20261117",
    "base_artifact_id": "JUDUN-1.2.188-RISKREVIEW20261115",
    "target_artifact_id": "JUDUN-1.2.189-CODEX20261117",
    "target_build_instance_id": "1.2.189-CODEX-20261117-STARTUP-FIX",
    "expected_display_version": "v1.2.189",
    "expected_managed_file_count": 98,
    "payload_path": "releases/v1.2.189-startup-fix-20261117.cms.b64",
    "payload_sha256": "7343b43890b80bb330e5d0a50053301e71c091ea7a791b4a683ba605d8496b42",
    "noop": False,
}
V189_TREE_SHA256 = "ca831e119db0ff9d35a114ef6ee52edc55c1ba4cf6598a9ddc0b986e2029ca4d"
CANDIDATE_CHECKS = frozenset({
    "isolated_startup", "quote_scoring", "basic_to_promax", "report_pdf",
    "rollback_after_migration",
})


def deny(reason):
    raise ValueError("DIRECT_DEPLOY_" + reason)


def load(path, size):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= size:
        deny("FILE_INVALID")
    return path.read_bytes()


def parse_signed_manifest(raw, sig_b64, cms_b64, pubkey):
    if not 0 < len(raw) <= 8192 or len(sig_b64) > 1024 or len(cms_b64) > 30000000:
        deny("SIGNED_INPUT_SIZE")
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result:
                deny("DUPLICATE_CONTROL_FIELD")
            result[k] = v
        return result
    try:
        m = json.loads(raw, object_pairs_hook=unique)
        sig = base64.b64decode(b"".join(sig_b64.split()), validate=True)
        cms = base64.b64decode(b"".join(cms_b64.split()), validate=True)
    except (UnicodeError, ValueError, TypeError) as err:
        if str(err).startswith("DIRECT_DEPLOY_"):
            raise
        deny("SIGNED_INPUT_PARSE")
    if not isinstance(m, dict) or m.get("schema") != "judun-autodeploy-v1":
        deny("MANIFEST_SCHEMA")
    base, target = m.get("base_artifact_id"), m.get("target_artifact_id")
    if (not isinstance(base, str) or not ARTIFACT.fullmatch(base)
            or not isinstance(target, str) or not ARTIFACT.fullmatch(target)
            or base == target):
        deny("ARTIFACT_IDENTITY")
    bver = tuple(map(int, base.split("-")[1].split(".")))
    tver = tuple(map(int, target.split("-")[1].split(".")))
    if (tver <= bver or m.get("expected_display_version") != "v" + ".".join(map(str, tver))
            or not isinstance(m.get("release_id"), str)
            or not re.fullmatch(r"v1\.2\.\d+-[A-Za-z0-9_-]{3,100}", m["release_id"])
            or not isinstance(m.get("target_build_instance_id"), str)
            or not m["target_build_instance_id"].startswith(".".join(map(str, tver)) + "-")
            or m.get("noop") is not False):
        deny("VERSION_OR_RELEASE")
    if (not isinstance(m.get("payload_path"), str)
            or not PAYLOAD_PATH.fullmatch(m["payload_path"])
            or not isinstance(m.get("payload_sha256"), str)
            or not HEX64.fullmatch(m["payload_sha256"])
            or hashlib.sha256(cms).hexdigest() != m["payload_sha256"]):
        deny("CMS_PAYLOAD_SHA")
    if len(sig) != 64 or not 0 < len(cms) <= 20000000:
        deny("CMS_OR_SIGNATURE_SIZE")
    if pubkey.is_symlink() or not pubkey.is_file():
        deny("PUBLIC_KEY_UNREADABLE")
    with tempfile.TemporaryDirectory(prefix="judun-direct-signature-") as td:
        original = Path(td) / "manifest"
        signature = Path(td) / "signature"
        original.write_bytes(raw)
        signature.write_bytes(sig)
        try:
            verified = subprocess.run([
                "openssl", "pkeyutl", "-verify", "-pubin",
                "-inkey", str(pubkey.resolve()), "-rawin",
                "-in", str(original), "-sigfile", str(signature)
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=8, check=False).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            deny("SIGNATURE_TOOL_UNAVAILABLE")
    if not verified:
        deny("ED25519_SIGNATURE_INVALID")
    return m


def check_live(build, deep, base, expected_tree):
    if (not isinstance(build, dict) or not isinstance(deep, dict)
            or build.get("artifact_id") != base or deep.get("artifact_id") != base):
        deny("LIVE_BASE_ARTIFACT_MISMATCH")
    expected_version = base.split("-")[1]
    # Compare all published release identities, not merely the artifact ID.
    # This refuses a build/deep split-brain during an overlapping rollout.
    for item in (build, deep):
        if (not isinstance(item.get("version"), str)
                or item["version"].removeprefix("v") != expected_version
                or item.get("source_tree_sha256") != expected_tree):
            deny("LIVE_BUILD_DEEP_RELEASE_DRIFT")
    instance = build.get("build_instance_id")
    if (not isinstance(instance, str) or not instance
            or deep.get("build_instance_id") != instance):
        deny("LIVE_BUILD_INSTANCE_DRIFT")
    count, total = deep.get("files_verified"), deep.get("manifest_file_count")
    if (deep.get("status") != "ok" or deep.get("deep_verified") is not True
            or type(deep.get("mismatch_count")) is not int
            or deep["mismatch_count"] != 0
            or type(count) is not int or type(total) is not int
            or count < 80 or count != total or
            deep.get("source_tree_sha256") != expected_tree):
        deny("LIVE_DEEP_SHA_NOT_VERIFIED")


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def site_get(origin, path, *, token=None):
    if origin not in (LIVE, STAGING) or not path.startswith("/") or path.startswith("//"):
        deny("SITE_OR_PATH_INVALID")
    if token and origin != STAGING:
        deny("STAGING_AUTH_ORIGIN_MISMATCH")
    url = origin + path
    headers = {"Cache-Control": "no-cache", "User-Agent": "JudunSignedPublish/1"}
    if token:
        headers["OAI-Sites-Authorization"] = "Bearer " + token
    req = Request(url, headers=headers)
    try:
        with build_opener(RejectRedirects()).open(req, timeout=10) as res:
            raw = res.read(1000001)
            if res.status != 200 or res.geturl() != url or len(raw) > 1000000:
                deny("LIVE_UNEXPECTED_RESPONSE")
        obj = json.loads(raw)
    except HTTPError as exc:
        deny(f"LIVE_HTTP_{exc.code}")
    except (URLError, OSError, json.JSONDecodeError, UnicodeError):
        deny("LIVE_RESPONSE_UNAVAILABLE")
    if not isinstance(obj, dict):
        deny("LIVE_RESPONSE_SHAPE")
    return obj


def live_get(path):
    return site_get(LIVE, path)


def github(method, path, token, body=None, missing_ok=False):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28",
               "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = Request(API + path, data=data, method=method, headers=headers)
    try:
        with build_opener(RejectRedirects()).open(req, timeout=30) as res:
            raw = res.read(3000001)
    except HTTPError as error:
        if missing_ok and error.code == 404:
            return None
        deny("GITHUB_REQUEST_REJECTED")
    except (OSError, URLError):
        deny("GITHUB_UNAVAILABLE")
    try:
        if len(raw) > 3000000:
            deny("GITHUB_RESPONSE_SIZE")
        return json.loads(raw)
    except (UnicodeError, ValueError):
        deny("GITHUB_RESPONSE_JSON")


def _github_contents(raw):
    try:
        return base64.b64decode("".join(raw["content"].split()), validate=True)
    except (KeyError, TypeError, ValueError):
        deny("GITHUB_CONTENT_UNREADABLE")


def publish_atomic(manifest, signature_b64, cms_b64, parsed, pubkey, token,
                   check_current_live):
    """Submit one candidate commit for review; never write the main ref."""
    ref = github("GET", "/git/ref/heads/main", token)
    head = ref["object"]["sha"]
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
        deny("PUBLISH_MAIN_REF_UNVERIFIED")
    channel = github("GET", "/contents/channel/stable.json?ref=" + head, token)
    key_file = github("GET", "/contents/keys/release_signing_public.pem?ref=" + head, token)
    if _github_contents(key_file) != load(pubkey, 4096):
        deny("PUBLISH_KEY_NOT_PINNED_TO_MAIN")
    try:
        installed = json.loads(_github_contents(channel))
    except (UnicodeError, ValueError):
        deny("INSTALLED_CHANNEL_UNVERIFIED")
    if installed.get("target_artifact_id") != parsed["base_artifact_id"]:
        deny("CHANNEL_BASE_NOT_LIVE_BASE")
    if github("GET", "/contents/" + parsed["payload_path"] + "?ref=" + head,
              token, missing_ok=True) is not None:
        deny("RELEASE_PAYLOAD_PATH_EXISTS")
    nonce = hashlib.sha256(manifest).hexdigest()[:24]
    branch = "release/" + parsed["release_id"] + "-" + nonce
    ref_path = "/git/ref/heads/" + branch
    ref_name = "refs/heads/" + branch
    candidate = github("GET", ref_path, token, missing_ok=True)
    parent = head
    if candidate is not None:
        sha = candidate.get("object", {}).get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            deny("PUBLISH_REF_RESPONSE_UNVERIFIED")
        actual = github("GET", "/git/commits/" + sha, token)
        parents = [p.get("sha") for p in actual.get("parents", [])]
        if len(parents) != 1 or not isinstance(parents[0], str) or not re.fullmatch(r"[0-9a-f]{40}", parents[0]):
            deny("PUBLISH_CANDIDATE_COMMIT_IDENTITY_MISMATCH")
        parent = parents[0]
    commit = github("GET", "/git/commits/" + parent, token)
    if check_current_live is not None:
        check_current_live()  # check again immediately before forming commit
    items = [
        (parsed["payload_path"], cms_b64),
        ("channel/stable.json.sig.b64", signature_b64),
        ("channel/stable.json", manifest),
    ]
    tree_rows = []
    for name, content in items:
        blob = github("POST", "/git/blobs", token, {
            "content": base64.b64encode(content).decode(), "encoding": "base64"})
        tree_rows.append({"path": name, "mode": "100644", "type": "blob",
                          "sha": blob["sha"]})
    tree = github("POST", "/git/trees", token, {
        "base_tree": commit["tree"]["sha"], "tree": tree_rows})
    for (_, content), row in zip(items, tree_rows, strict=True):
        if row["sha"] != git_blob_oid(content):
            deny("PUBLISH_BLOB_IDENTITY_MISMATCH")
    latest = github("GET", "/git/ref/heads/main", token)["object"]["sha"]
    if not isinstance(latest, str) or not re.fullmatch(r"[0-9a-f]{40}", latest):
        deny("PUBLISH_MAIN_REF_UNVERIFIED")
    if latest != head:
        def read_file(path):
            return _github_contents(github("GET", f"/contents/{path}?ref={latest}", token))
        if (read_file("channel/stable.json") != _github_contents(channel)
                or read_file("keys/release_signing_public.pem") != load(pubkey, 4096)
                or github("GET", "/contents/" + parsed["payload_path"] + "?ref=" + latest,
                          token, missing_ok=True) is not None):
            deny("PUBLISH_SIGNED_BASE_CHANGED")
    if candidate is None:
        release = github("POST", "/git/commits", token, {
            "message": "JUDUN signed release " + parsed["release_id"],
            "tree": tree["sha"], "parents": [head]})
        github("POST", "/git/refs", token, {"ref": ref_name, "sha": release["sha"]})
        candidate = github("GET", ref_path, token)
        if candidate.get("object", {}).get("sha") != release["sha"]:
            deny("PUBLISH_REF_RESPONSE_UNVERIFIED")
    sha = candidate.get("object", {}).get("sha")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        deny("PUBLISH_REF_RESPONSE_UNVERIFIED")
    actual = github("GET", "/git/commits/" + sha, token)
    if (actual.get("tree", {}).get("sha") != tree["sha"]
            or [p.get("sha") for p in actual.get("parents", [])] != [parent]):
        deny("PUBLISH_CANDIDATE_COMMIT_IDENTITY_MISMATCH")
    params = urlencode({"state": "open", "head": REPO.split("/")[0] + ":" + branch, "base": "main"})
    matches = github("GET", "/pulls?" + params, token)
    if not isinstance(matches, list) or len(matches) > 1:
        deny("PUBLISH_PULL_REQUEST_AMBIGUOUS")
    request = matches[0] if matches else github("POST", "/pulls", token, {
        "title": "Release " + parsed["expected_display_version"],
        "head": branch, "base": "main",
        "body": (
            "Signed channel manifest and encrypted release payload. "
            "Merge after the release gate passes to start deployment. "
            "Verify both sites after merge."
        ),
    })
    num = request.get("number")
    if (type(num) is not int or num < 1 or request.get("state") != "open"
            or request.get("head", {}).get("sha") != sha
            or request.get("head", {}).get("ref") != branch
            or request.get("base", {}).get("ref") != "main"):
        deny("PUBLISH_PULL_REQUEST_UNVERIFIED")
    return {"candidate_commit": sha, "pull_request": f"https://github.com/{REPO}/pull/{num}"}


def git_blob_oid(content):
    """Compute SHA-1 Git blob object ID without uploading or exposing bytes."""
    return hashlib.sha1(
        ("blob " + str(len(content)) + "\0").encode("ascii") + content
    ).hexdigest()


def verify_published_channel(manifest, signature_b64, cms_b64, target, pubkey, token=""):
    """Read-only recovery after a lost API response or interrupted publishing.

    Never retries a Git write. Exact original signed bytes must already exist
    on main as one commit. This does NOT assert that VPS deployment succeeded.
    """
    key_file = github("GET", "/contents/keys/release_signing_public.pem?ref=main", token)
    if _github_contents(key_file) != load(pubkey, 4096):
        deny("RECOVERY_PINNED_KEY_CHANGED")
    ref = github("GET", "/git/ref/heads/main", token)
    head = ref.get("object", {}).get("sha")
    if not isinstance(head, str) or not re.fullmatch(r"[0-9a-f]{40}", head):
        deny("RECOVERY_MAIN_REF_UNVERIFIED")
    latest = github("GET", "/contents/channel/stable.json?ref=" + head, token)
    if _github_contents(latest) != manifest:
        deny("RECOVERY_SIGNED_CHANNEL_MISMATCH")
    commit = github("GET", "/git/commits/" + head, token)
    tree_sha = commit.get("tree", {}).get("sha")
    if not isinstance(tree_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", tree_sha):
        deny("RECOVERY_COMMIT_TREE_MISSING")
    tree = github("GET", "/git/trees/" + tree_sha + "?recursive=1", token)
    if tree.get("truncated") is not False:
        deny("RECOVERY_TREE_UNVERIFIABLE")
    index = {item.get("path"): item for item in tree.get("tree", [])
             if isinstance(item, dict)}
    for path, content in (
        (target["payload_path"], cms_b64),
        ("channel/stable.json.sig.b64", signature_b64),
        ("channel/stable.json", manifest),
    ):
        item = index.get(path, {})
        if (item.get("sha") != git_blob_oid(content)
                or item.get("type") != "blob" or item.get("mode") != "100644"):
            deny("RECOVERY_SIGNED_BYTES_NOT_IN_SAME_COMMIT")
    return head


def expected_target_integrity(target):
    count = target.get("expected_managed_file_count")
    if type(count) is not int or count <= 0:
        deny("SIGNED_TARGET_FILE_COUNT_REQUIRED")
    tree = target.get("expected_source_tree_sha256")
    # v189 already shipped. Its exact signed CMS digest selects the recorded
    # tree from its release bundle. New packages must sign the tree themselves.
    if target == V189_RELEASE:
        tree = V189_TREE_SHA256
    if not isinstance(tree, str) or not HEX64.fullmatch(tree):
        deny("SIGNED_TARGET_SOURCE_TREE_REQUIRED")
    return count, tree


def expected_candidate_receipt(target, *, allow_v189=False):
    digest = target.get("candidate_acceptance_sha256")
    if isinstance(digest, str) and HEX64.fullmatch(digest):
        return digest
    if allow_v189 and target == V189_RELEASE:
        return None
    deny("SIGNED_CANDIDATE_ACCEPTANCE_REQUIRED")


def check_candidate_receipt(target, receipt):
    digest = expected_candidate_receipt(target)
    if hashlib.sha256(receipt).hexdigest() != digest:
        deny("CANDIDATE_ACCEPTANCE_SHA_MISMATCH")
    data = json.loads(receipt)
    count, tree = expected_target_integrity(target)
    expected = {
        "schema": "judun-candidate-acceptance-v1",
        "release_id": target["release_id"],
        "base_artifact_id": target["base_artifact_id"],
        "target_artifact_id": target["target_artifact_id"],
        "target_build_instance_id": target["target_build_instance_id"],
        "payload_sha256": target["payload_sha256"],
        "source_tree_sha256": tree,
        "managed_file_count": count,
    }
    if (not isinstance(data, dict)
            or any(data.get(key) != value for key, value in expected.items())):
        deny("CANDIDATE_ACCEPTANCE_IDENTITY_MISMATCH")
    checks = data.get("checks")
    if not isinstance(checks, dict) or not CANDIDATE_CHECKS <= checks.keys():
        deny("CANDIDATE_ACCEPTANCE_CHECK_MISSING")
    for name in sorted(CANDIDATE_CHECKS):
        result = checks[name]
        if (not isinstance(result, dict) or result.get("status") != "pass"
                or not isinstance(result.get("evidence"), str)
                or not result["evidence"].strip()):
            deny("CANDIDATE_ACCEPTANCE_CHECK_NOT_PASSED: " + name)


def check_target_build(build, target, tree, payment_mode):
    if (build.get("status") != "ok" or build.get("manifest_status") != "ok"
            or build.get("artifact_id") != target["target_artifact_id"]
            or build.get("build_instance_id") != target["target_build_instance_id"]
            or build.get("display_version") != target["expected_display_version"]
            or build.get("version") != target["expected_display_version"].removeprefix("v")
            or build.get("source_tree_sha256") != tree):
        deny("LIVE_TARGET_BUILD_MISMATCH")
    if build.get("payment_mode") != payment_mode:
        deny("LIVE_PAYMENT_MODE_MISMATCH")


def verify_target_live(target, *, getter=None, payment_mode="ecpay_live",
                       attempts=36, interval=10, timeout=420):
    """Verify the expected release against one site's health endpoints."""
    count, tree = expected_target_integrity(target)
    get = live_get if getter is None else getter
    deadline = time.monotonic() + timeout
    reason = "NOT_CHECKED"
    for attempt in range(attempts):
        try:
            build = get("/health/build")
            check_target_build(build, target, tree, payment_mode)
            deep = get("/health/artifact?deep=true")
            check_live(build, deep, target["target_artifact_id"], tree)
            if deep["files_verified"] != count:
                deny("LIVE_SIGNED_FILE_COUNT_MISMATCH")
            ready = get("/health/ready")
            if ready.get("status") != "ready" or ready.get("version") != build["version"]:
                deny("LIVE_READINESS_MISMATCH")
            check_target_build(get("/health/build"), target, tree, payment_mode)
            return {"artifact_id": target["target_artifact_id"],
                    "build_instance_id": target["target_build_instance_id"],
                    "version": target["expected_display_version"],
                    "source_tree_sha256": tree, "managed_files": count,
                    "payment_mode": payment_mode}
        except ValueError as exc:
            reason = str(exc)
            if reason in {"DIRECT_DEPLOY_LIVE_HTTP_401", "DIRECT_DEPLOY_LIVE_HTTP_403"}:
                break
        remaining = deadline - time.monotonic()
        if attempt + 1 == attempts or remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    deny("PUBLISHED_BUT_VPS_DEPLOYMENT_NOT_VERIFIED: " + reason)


def verify_staging_live(target, token, *, attempts=36):
    if not token:
        deny("STAGING_AUTH_REQUIRED")
    try:
        return verify_target_live(
            target, getter=lambda path: site_get(STAGING, path, token=token),
            payment_mode="test_unlock", attempts=attempts,
        )
    except ValueError as exc:
        deny("STAGING_NOT_VERIFIED: " + str(exc))


def verify_dual_site(target, token):
    if not token:
        deny("STAGING_AUTH_REQUIRED")
    production = verify_target_live(target)
    print("LIVE_DEEP_VERIFY_PASS", json.dumps(production), flush=True)
    staging = verify_staging_live(target, token)
    # The second site may take longer to start. Reconfirm production before
    # reporting a successful check of both sites.
    verify_target_live(target, attempts=1)
    print("DUAL_SITE_HEALTH_PASS",
          json.dumps({"production": production, "staging": staging}), flush=True)


def run():
    ap = argparse.ArgumentParser(description="JUDUN one-command signed channel publisher")
    for name in ("manifest", "signature", "payload", "public-key"):
        ap.add_argument("--" + name, required=True, type=Path)
    ap.add_argument("--expected-base-artifact", required=True)
    ap.add_argument("--expected-source-tree-sha256", required=True)
    ap.add_argument("--candidate-acceptance", type=Path,
                    help="Private candidate QA receipt required for a new publication")
    operation = ap.add_mutually_exclusive_group()
    operation.add_argument("--publish", action="store_true",
                           help="Open a signed release PR without merging or deploying")
    operation.add_argument("--verify-published", action="store_true",
                           help="Read back a previously published signed channel and check the VPS")
    a = ap.parse_args()
    try:
        if not HEX64.fullmatch(a.expected_source_tree_sha256):
            deny("EXPECTED_TREE_SHA_REQUIRED")
        manifest = load(a.manifest, 8192)
        sig = load(a.signature, 1024)
        cms = load(a.payload, 30000000)
        if hashlib.sha256(load(a.public_key, 4096)).hexdigest() != RELEASE_KEY_SHA256:
            deny("PINNED_RELEASE_KEY_MISMATCH")
        parsed = parse_signed_manifest(manifest, sig, cms, a.public_key)
        if parsed["base_artifact_id"] != a.expected_base_artifact:
            deny("EXPECTED_BASE_ARTIFACT")
        expected_target_integrity(parsed)
        if a.publish and not a.candidate_acceptance:
            deny("CANDIDATE_ACCEPTANCE_FILE_REQUIRED")
        if a.candidate_acceptance:
            check_candidate_receipt(parsed, load(a.candidate_acceptance, 32768))
            print("CANDIDATE_ACCEPTANCE_IDENTITY_PASS", flush=True)
        elif expected_candidate_receipt(parsed, allow_v189=True) and not a.verify_published:
            deny("CANDIDATE_ACCEPTANCE_FILE_REQUIRED")
        stage_token = os.environ.get("JUDUN_STAGE_AUTH_TOKEN")
        if (a.publish or a.verify_published) and not stage_token:
            deny("STAGING_AUTH_REQUIRED")
        if a.verify_published:
            verified_commit = verify_published_channel(
                manifest, sig, cms, parsed, a.public_key,
                os.environ.get("GITHUB_TOKEN", ""))
            print("DIRECT_DEPLOY_SIGNED_CHANNEL_RECOVERED", verified_commit, flush=True)
            verify_dual_site(parsed, stage_token)
            print("PAYMENT_AND_REPORT_PDF_E2E_STILL_REQUIRED")
            return 0
        def check():
            check_live(live_get("/health/build"),
                       live_get("/health/artifact?deep=true"),
                       parsed["base_artifact_id"], a.expected_source_tree_sha256)
            ready = live_get("/health/ready")
            if (ready.get("status") != "ready"
                    or ready.get("version") != parsed["base_artifact_id"].split("-")[1]):
                deny("LIVE_BASE_READINESS_MISMATCH")
        check()
        if not a.publish:
            print("DIRECT_DEPLOY_SIGNED_PREFLIGHT_PASS; NO_PUBLICATION")
            return 0
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            deny("GITHUB_TOKEN_ENV_REQUIRED")
        stage_result = verify_staging_live(parsed, stage_token, attempts=1)
        print("STAGING_RELEASE_CANDIDATE_PASS", json.dumps(stage_result), flush=True)
        request = publish_atomic(manifest, sig, cms, parsed, a.public_key, token, check)
        print("DIRECT_DEPLOY_RELEASE_PR_OPENED_NOT_DEPLOYED", json.dumps(request), flush=True)
        return 0
    except (ValueError, KeyError, TypeError) as exc:
        msg = str(exc)
        print(msg if msg.startswith("DIRECT_DEPLOY_") else "DIRECT_DEPLOY_BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())

