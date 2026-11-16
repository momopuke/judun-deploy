#!/usr/bin/env python3
"""Read-only JUDUN signed-channel/live identity probe. No form submissions or deployment."""
import base64
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://judun.142-93-91-214.sslip.io"
ROOT = Path(__file__).resolve().parents[1]
channel_bytes = (ROOT / "channel/stable.json").read_bytes()
sig = base64.b64decode((ROOT / "channel/stable.json.sig.b64").read_bytes(), validate=True)
assert len(sig) == 64, "SIGNATURE_INVALID_SIZE"
public_key = (ROOT / "keys/release_signing_public.pem").read_bytes()
assert hashlib.sha256(public_key).hexdigest() == "17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db", "TRUST_ROOT_CHANGED"
with tempfile.TemporaryDirectory() as d:
    p = Path(d)
    (p / "channel").write_bytes(channel_bytes)
    (p / "sig").write_bytes(sig)
    (p / "pub.pem").write_bytes(public_key)
    subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(p/"pub.pem"),
                    "-rawin", "-in", str(p/"channel"), "-sigfile", str(p/"sig")],
                   check=True, capture_output=True, timeout=10)
channel = json.loads(channel_bytes)
assert re.fullmatch(r"v\d+\.\d+\.\d+",channel["expected_display_version"])
print("SIGNED_CHANNEL_PASS",channel["expected_display_version"],channel["target_artifact_id"],flush=True)

def get(path):
    errors = []
    for attempt in range(2):
        try:
            req = urllib.request.Request(BASE+path, headers={"User-Agent":"JUDUN-GitHub-readonly-audit/20261117","Cache-Control":"no-cache"})
            with urllib.request.urlopen(req, timeout=20) as res:
                body = res.read(6_000_000)
                assert res.status == 200
                return body
        except (urllib.error.URLError,TimeoutError,ValueError,AssertionError) as exc:
            errors.append(str(exc)[:250])
            if attempt == 0:
                time.sleep(2)
    raise RuntimeError("GET "+path+" FAILED "+repr(errors))

home = get("/").decode("utf-8","replace")
assert "居盾" in home, "BRAND_MISSING"
print("HOMEPAGE_HTTPS_200",len(home),flush=True)
build = json.loads(get("/health/build"))
print("LIVE_BUILD",json.dumps({k:build.get(k) for k in ("version","artifact_id","source_tree_sha256")},ensure_ascii=False),flush=True)
expected_version = channel["expected_display_version"].lstrip("v")
assert str(build.get("version","")).lstrip("v") == expected_version, "LIVE_VERSION_DIFFERENT_FROM_SIGNED_CHANNEL"
assert build.get("artifact_id") == channel["target_artifact_id"], "LIVE_ARTIFACT_DIFFERENT_FROM_SIGNED_CHANNEL"
deep = json.loads(get("/health/artifact?deep=true"))
print("LIVE_DEEP",json.dumps({k:deep.get(k) for k in ("status","artifact_id","files_verified","manifest_file_count","mismatch_count")},ensure_ascii=False),flush=True)
assert deep.get("status") == "ok" and deep.get("artifact_id") == build.get("artifact_id"),"DEEP_ARTIFACT_MISMATCH"
assert int(deep.get("mismatch_count",-1)) == 0, "DEEP_MISMATCH"
assert int(deep.get("files_verified",-1)) == int(channel["expected_managed_file_count"]),"FILE_COUNT_MISMATCH"
for path in ("/matching/","/matching/?role=company","/cooperation/"):
    body=get(path)
    assert body, "EMPTY_ROUTE "+path
    print("ROUTE_HTTPS_200",path,len(body),flush=True)
print("PUBLIC_READONLY_VERIFICATION_PASS; NOT A DEPLOYMENT OR PAYMENT TEST",flush=True)
