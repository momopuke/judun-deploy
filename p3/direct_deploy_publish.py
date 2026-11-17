"""Publish an existing trusted, signed JUDUN release atomically to main.

Requires an already approved CMS release produced by the ORIGINAL private
source builder and Ed25519 signer; never creates or reads signing private keys.
The existing VPS pull-agent performs its own base match, backup, and deep SHA.
Default action is preflight only. --publish is an explicit write action.
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
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

REPO = "momopuke/judun-deploy"
API = "https://api.github.com/repos/" + REPO
LIVE = "https://judun.142-93-91-214.sslip.io"
STAGING = "https://judun-test.tony870490.chatgpt.site"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ARTIFACT = re.compile(r"JUDUN-1\.2\.\d+-[A-Za-z0-9_-]{6,80}\Z")
PAYLOAD_PATH = re.compile(r"releases/[A-Za-z0-9._-]+\.cms\.b64\Z")
RELEASE_KEY_SHA256 = "17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db"
V189_PAYLOAD_SHA256 = "7343b43890b80bb330e5d0a50053301e71c091ea7a791b4a683ba605d8496b42"
V189_TREE_SHA256 = "ca831e119db0ff9d35a114ef6ee52edc55c1ba4cf6598a9ddc0b986e2029ca4d"


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
        with urlopen(req, timeout=30) as res:
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
    """One fast-forward commit changes the 3 channel files simultaneously."""
    ref = github("GET", "/git/ref/heads/main", token)
    head = ref["object"]["sha"]
    commit = github("GET", "/git/commits/" + head, token)
    channel = github("GET", "/contents/channel/stable.json?ref=main", token)
    key_file = github("GET", "/contents/keys/release_signing_public.pem?ref=main", token)
    if _github_contents(key_file) != load(pubkey, 4096):
        deny("PUBLISH_KEY_NOT_PINNED_TO_MAIN")
    try:
        installed = json.loads(_github_contents(channel))
    except (UnicodeError, ValueError):
        deny("INSTALLED_CHANNEL_UNVERIFIED")
    if installed.get("target_artifact_id") != parsed["base_artifact_id"]:
        deny("CHANNEL_BASE_NOT_LIVE_BASE")
    if github("GET", "/contents/" + parsed["payload_path"] + "?ref=main",
              token, missing_ok=True) is not None:
        deny("RELEASE_PAYLOAD_PATH_EXISTS")
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
    release = github("POST", "/git/commits", token, {
        "message": "JUDUN signed release " + parsed["release_id"],
        "tree": tree["sha"], "parents": [head]})
    # force=false: any intervening branch movement rejects this publication.
    confirmed = github("PATCH", "/git/refs/heads/main", token,
                       {"sha": release["sha"], "force": False})
    if confirmed.get("object", {}).get("sha") != release["sha"]:
        deny("PUBLISH_REF_RESPONSE_UNVERIFIED")
    # A successful HTTP write is not enough. Re-read the canonical branch and
    # its immutable tree; verify all three files are in the SAME commit.
    published = github("GET", "/git/ref/heads/main", token)
    if published.get("object", {}).get("sha") != release["sha"]:
        deny("PUBLISH_REF_CHANGED_AFTER_UPDATE")
    actual_commit = github("GET", "/git/commits/" + release["sha"], token)
    if (actual_commit.get("tree", {}).get("sha") != tree["sha"]
            or [p.get("sha") for p in actual_commit.get("parents", [])] != [head]):
        deny("PUBLISH_COMMIT_IDENTITY_MISMATCH")
    indexed_tree = github("GET", "/git/trees/" + tree["sha"] + "?recursive=1", token)
    if indexed_tree.get("truncated") is not False:
        deny("PUBLISH_TREE_UNVERIFIABLE")
    index = {f.get("path"): f for f in indexed_tree.get("tree", [])
             if isinstance(f, dict)}
    for expected in tree_rows:
        actual = index.get(expected["path"], {})
        if (actual.get("sha") != expected["sha"]
                or actual.get("type") != "blob"
                or actual.get("mode") != "100644"):
            deny("PUBLISH_CHANNEL_NOT_ATOMIC")
    return release["sha"]


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
    if "expected_source_tree_sha256" not in target and target.get("payload_sha256") == V189_PAYLOAD_SHA256:
        if (target.get("release_id"), target.get("target_artifact_id"),
                target.get("target_build_instance_id"), count) == (
                "v1.2.189-startup-fix-20261117", "JUDUN-1.2.189-CODEX20261117",
                "1.2.189-CODEX-20261117-STARTUP-FIX", 98):
            tree = V189_TREE_SHA256
    if not isinstance(tree, str) or not HEX64.fullmatch(tree):
        deny("SIGNED_TARGET_SOURCE_TREE_REQUIRED")
    return count, tree


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
    operation = ap.add_mutually_exclusive_group()
    operation.add_argument("--publish", action="store_true")
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
        stage_base = site_get(STAGING, "/health/build", token=stage_token)
        if stage_base.get("payment_mode") != "test_unlock":
            deny("STAGING_TEST_PAYMENT_MODE_REQUIRED")
        new_sha = publish_atomic(manifest, sig, cms, parsed,
                                 a.public_key, token, check)
        print("DIRECT_DEPLOY_SIGNED_CHANNEL_PUBLISHED", new_sha, flush=True)
        verify_dual_site(parsed, stage_token)
        print("PAYMENT_AND_REPORT_PDF_E2E_STILL_REQUIRED")
        return 0
    except (ValueError, KeyError, TypeError) as exc:
        msg = str(exc)
        print(msg if msg.startswith("DIRECT_DEPLOY_") else "DIRECT_DEPLOY_BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())

