"""Verify this commit's signed target and deep production integrity."""
import base64, hashlib, json, re, subprocess, sys, tempfile, time
import urllib.error, urllib.request
from pathlib import Path, PurePosixPath

BASE = "https://judun.142-93-91-214.sslip.io"

def verify_package():
    path = Path("channel/stable.json")
    m = json.loads(path.read_text())
    assert m["schema"] == "judun-autodeploy-v1"
    for key in ("release_id", "target_artifact_id", "target_build_instance_id", "expected_display_version"):
        assert isinstance(m.get(key), str) and m[key], key
    relative = PurePosixPath(m["payload_path"])
    assert not relative.is_absolute() and ".." not in relative.parts and relative.parts[0] == "releases"
    assert re.fullmatch(r"[0-9a-f]{64}", m["payload_sha256"])
    payload = base64.b64decode("".join(Path(relative).read_text().split()), validate=True)
    assert hashlib.sha256(payload).hexdigest() == m["payload_sha256"], "payload SHA256 mismatch"
    signature = base64.b64decode("".join(Path("channel/stable.json.sig.b64").read_text().split()), validate=True)
    with tempfile.NamedTemporaryFile() as sig:
        sig.write(signature); sig.flush()
        subprocess.run(["openssl", "pkeyutl", "-verify", "-pubin", "-inkey", "keys/release_signing_public.pem", "-rawin", "-in", str(path), "-sigfile", sig.name], check=True)
    print("SIGNED_RELEASE_PASS", m["release_id"], flush=True)
    return m

def get_json(path):
    req = urllib.request.Request(BASE + path, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)

def verify_live(m):
    deadline = time.monotonic() + 360
    last = "not checked"
    while time.monotonic() < deadline:
        try:
            b = get_json("/health/build")
            expected = m["target_artifact_id"]
            if b.get("artifact_id") != expected or b.get("build_instance_id") != m["target_build_instance_id"]:
                last = "Waiting for target; live=" + str(b.get("artifact_id"))
            else:
                assert b.get("display_version") == m["expected_display_version"], "display version mismatch"
                d = get_json("/health/artifact?deep=true")
                assert d.get("status") == "ok", "deep integrity failed"
                assert d.get("artifact_id") == expected, "deep artifact mismatch"
                assert d.get("build_instance_id") == m["target_build_instance_id"], "deep build mismatch"
                assert d.get("mismatch_count") == 0, "managed file drift"
                assert int(d.get("files_verified") or 0) == int(d.get("manifest_file_count") or 0) >= 52, "incomplete verification"
                assert get_json("/health/ready").get("status") == "ready", "runtime not ready"
                print("LIVE_DEEP_VERIFY_PASS", json.dumps({"version": b["display_version"], "artifact_id": expected, "files_verified": d["files_verified"]}), flush=True)
                return
        except (urllib.error.URLError, TimeoutError, AssertionError, ValueError) as exc:
            last = type(exc).__name__ + ": " + str(exc)
        print(last, flush=True)
        time.sleep(10)
    raise SystemExit("Production verification failed: " + last)

if __name__ == "__main__":
    target = verify_package()
    if sys.argv[1:] == ["live"]: verify_live(target)
    elif sys.argv[1:] != ["package"]: raise SystemExit("Usage: verify_release.py package|live")
