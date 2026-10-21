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
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO = "momopuke/judun-deploy"
API = "https://api.github.com/repos/" + REPO
LIVE = "https://judun.142-93-91-214.sslip.io"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
ARTIFACT = re.compile(r"JUDUN-1\.2\.\d+-[A-Za-z0-9_-]{6,80}\Z")
PAYLOAD_PATH = re.compile(r"releases/[A-Za-z0-9._-]+\.cms\.b64\Z")


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
    count, total = deep.get("files_verified"), deep.get("manifest_file_count")
    if (deep.get("status") != "ok" or deep.get("deep_verified") is not True
            or type(deep.get("mismatch_count")) is not int
            or deep["mismatch_count"] != 0
            or type(count) is not int or type(total) is not int
            or count < 80 or count != total or
            deep.get("source_tree_sha256") != expected_tree):
        deny("LIVE_DEEP_SHA_NOT_VERIFIED")


def live_get(path):
    req = Request(LIVE + path, headers={
        "Cache-Control": "no-cache", "User-Agent": "JudunSignedPublish/1"})
    try:
        with urlopen(req, timeout=20) as res:
            raw = res.read(1000001)
            if res.status != 200 or len(raw) > 1000000:
                deny("LIVE_UNEXPECTED_RESPONSE")
        obj = json.loads(raw)
    except (HTTPError, URLError, OSError, ValueError, UnicodeError):
        deny("LIVE_UNAVAILABLE")
    if not isinstance(obj, dict):
        deny("LIVE_RESPONSE_SHAPE")
    return obj


def github(method, path, token, body=None, missing_ok=False):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    req = Request(API + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json"})
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
    github("PATCH", "/git/refs/heads/main", token,
           {"sha": release["sha"], "force": False})
    return release["sha"]


def run():
    ap = argparse.ArgumentParser(description="JUDUN one-command signed channel publisher")
    for name in ("manifest", "signature", "payload", "public-key"):
        ap.add_argument("--" + name, required=True, type=Path)
    ap.add_argument("--expected-base-artifact", required=True)
    ap.add_argument("--expected-source-tree-sha256", required=True)
    ap.add_argument("--publish", action="store_true")
    a = ap.parse_args()
    try:
        if not HEX64.fullmatch(a.expected_source_tree_sha256):
            deny("EXPECTED_TREE_SHA_REQUIRED")
        manifest = load(a.manifest, 8192)
        sig = load(a.signature, 1024)
        cms = load(a.payload, 30000000)
        parsed = parse_signed_manifest(manifest, sig, cms, a.public_key)
        if parsed["base_artifact_id"] != a.expected_base_artifact:
            deny("EXPECTED_BASE_ARTIFACT")
        def check():
            check_live(live_get("/health/build"),
                       live_get("/health/artifact?deep=true"),
                       parsed["base_artifact_id"], a.expected_source_tree_sha256)
        check()
        if not a.publish:
            print("DIRECT_DEPLOY_SIGNED_PREFLIGHT_PASS; NO_PUBLICATION")
            return 0
        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            deny("GITHUB_TOKEN_ENV_REQUIRED")
        new_sha = publish_atomic(manifest, sig, cms, parsed,
                                 a.public_key, token, check)
        print("DIRECT_DEPLOY_SIGNED_CHANNEL_PUBLISHED", new_sha)
        print("VPS_DEPLOYMENT_NOT_YET_VERIFIED")
        return 0
    except (ValueError, KeyError, TypeError) as exc:
        msg = str(exc)
        print(msg if msg.startswith("DIRECT_DEPLOY_") else "DIRECT_DEPLOY_BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(run())
