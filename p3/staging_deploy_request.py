"""Install a signed, encrypted candidate requested through GitHub on staging."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import ProxyHandler, Request, build_opener
from zipfile import BadZipFile

if __name__ == "__main__":
    # The systemd unit uses Python's isolated mode. Both scripts are installed
    # together in the existing root-owned staging directory.
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from staging_release import (
    HEX, STAGE_ROOT, NoRedirect, Release, check_name, check_running,
    enforce_service, prepare, process_state, read_regular, recover,
    restart_service, selection, store_lock, sync_directory, verify_snapshot,
)


GITHUB = "https://raw.githubusercontent.com/momopuke/judun-deploy/"
REQUEST = "main/ops/staging-request.json"
SCHEMA = "judun.staging-deploy.v1"
KEY_SHA256 = "17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db"
CONFIG = Path("/etc/judun-staging-pull")
STATE = Path("/var/lib/judun-staging-pull")
MAX_CMS = 64 * 1024 * 1024


def strict_json(raw):
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Duplicate JSON field")
        return result

    return json.loads(raw, object_pairs_hook=unique)


def fetch(path, limit, destination=None):
    headers = {"Cache-Control": "no-cache"}
    # Main is PR-protected. Candidate content remains cryptographically verified
    # with the pinned Ed25519 key; a mutable request can never bypass signature.
    url = GITHUB + path
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(url, headers=headers), timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("Unexpected GitHub response")
        if destination is None:
            data = response.read(limit + 1)
            if not 0 < len(data) <= limit:
                raise ValueError("Unexpected staging channel file size")
            return data
        remaining = limit
        with destination.open("xb") as file:
            for chunk in iter(lambda: response.read(min(1024 * 1024, remaining + 1)), b""):
                remaining -= len(chunk)
                if remaining < 0:
                    raise ValueError("Staging package exceeds download limit")
                file.write(chunk)


def request_commit(get):
    request = strict_json(get(REQUEST, 2048))
    if not isinstance(request, dict) or set(request) != {"candidate_commit"}:
        raise ValueError("Invalid GitHub staging request")
    commit = request["candidate_commit"]
    if commit is not None and (not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit)):
        raise ValueError("A request must name one immutable candidate commit")
    return commit


def openssl(*args):
    result = subprocess.run(["openssl", *args], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, timeout=45, check=False)
    if result.returncode:
        raise ValueError("Staging signature or CMS verification failed")


def signed_candidate(raw, signature, work, public_key):
    key = read_regular(public_key, 4096)
    if hashlib.sha256(key).hexdigest() != KEY_SHA256:
        raise ValueError("Staging signing key does not match the pinned key")
    signature = base64.b64decode(b"".join(signature.split()), validate=True)
    if len(signature) != 64:
        raise ValueError("Invalid Ed25519 signature length")
    manifest_path, signature_path = work / "manifest", work / "signature"
    manifest_path.write_bytes(raw)
    signature_path.write_bytes(signature)
    openssl("pkeyutl", "-verify", "-pubin", "-inkey", str(public_key),
            "-rawin", "-in", str(manifest_path), "-sigfile", str(signature_path))
    data = strict_json(raw)
    if (not isinstance(data, dict)
            or set(data) != {"schema", "base_snapshot", "target", "cms_sha256", "zip_sha256"}
            or data["schema"] != SCHEMA
            or not isinstance(data["target"], dict)
            or set(data["target"]) != {
                "version", "artifact_id", "build_instance_id", "source_tree_sha256", "file_count"
            }
            or any(not isinstance(data[name], str) or not HEX.fullmatch(data[name])
                   for name in ("cms_sha256", "zip_sha256"))):
        raise ValueError("Invalid signed staging manifest")
    return data, Release(**data["target"]), check_name(data["base_snapshot"])


def verify_sha(path, expected):
    with path.open("rb") as file:
        digest = hashlib.sha256()
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError("Staging package SHA-256 mismatch")


def record_attempt(state, commit, target):
    with tempfile.NamedTemporaryFile(mode="w", dir=state, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump({"commit": commit, "target": target}, file)
            file.flush()
            os.fsync(file.fileno())
            temporary.replace(state / f"attempt-{commit}.json")
            sync_directory(state)
        finally:
            temporary.unlink(missing_ok=True)


def install_request(root, state, config, get, restart, health):
    commit = request_commit(get)
    if commit is None:
        return {"status": "no_request"}
    prefix = f"{commit}/staging/candidate"
    with store_lock(state), tempfile.TemporaryDirectory(dir=state) as temporary:
        work = Path(temporary)
        raw = get(prefix + ".json", 8192)
        signature = get(prefix + ".json.sig.b64", 1024)
        data, target, expected_current = signed_candidate(
            raw, signature, work, config / "release_signing_public.pem")
        with store_lock(root):
            if (root / ".switch-pending.json").exists():
                recover(root, restart, health)
            current = verify_snapshot(selection(root))
            if current == target:
                health(target)
                return {"status": "already_active", "commit": commit, "snapshot": target.name}
            if current.name != expected_current:
                raise ValueError("Requested candidate has a stale staging baseline")
        if os.path.lexists(state / f"attempt-{commit}.json"):
            raise ValueError("This candidate was already attempted; inspect the staging journal")
        envelope, package = work / "candidate.cms", work / "candidate.zip"
        get(prefix + ".cms", MAX_CMS, envelope)
        verify_sha(envelope, data["cms_sha256"])
        openssl("cms", "-decrypt", "-binary", "-inform", "DER", "-in", str(envelope),
                "-recip", str(config / "recipient.pem"),
                "-inkey", str(config / "recipient-key.pem"), "-out", str(package))
        verify_sha(package, data["zip_sha256"])
        # The original signature and exact decrypted ZIP SHA are verified above.
        prepare(root, package, target, allow_signed_root_zip=True)
        with store_lock(root):
            if verify_snapshot(selection(root)).name != expected_current:
                raise ValueError("Staging baseline changed before switching")
            if request_commit(get) != commit:
                return {"status": "superseded", "commit": commit}
            process_state(root, target.name, restart, health,
                          before_switch=lambda: record_attempt(state, commit, target.name))
        return {"status": "installed", "commit": commit, "snapshot": target.name}


def main():
    try:
        enforce_service(STAGE_ROOT)
        result = install_request(STAGE_ROOT, STATE, CONFIG, fetch, restart_service, check_running)
        print(json.dumps(result), flush=True)
    except (OSError, ValueError, RuntimeError, BadZipFile, subprocess.SubprocessError) as error:
        raise SystemExit(f"Staging request failed: {error}") from None


if __name__ == "__main__":
    main()
