"""Check the signed package or confirm its deployment over HTTPS."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "p3"))

from direct_deploy_publish import (
    PAYLOAD_PATH,
    RELEASE_KEY_SHA256,
    deny,
    expected_candidate_receipt,
    expected_target_integrity,
    load,
    parse_signed_manifest,
    verify_dual_site,
    verify_target_live,
)


def verify_package():
    raw = load(ROOT / "channel/stable.json", 8192)
    manifest = json.loads(raw)
    path = manifest.get("payload_path") if isinstance(manifest, dict) else None
    if not isinstance(path, str) or not PAYLOAD_PATH.fullmatch(path):
        deny("SIGNED_PAYLOAD_PATH_INVALID")
    key = ROOT / "keys/release_signing_public.pem"
    if hashlib.sha256(load(key, 4096)).hexdigest() != RELEASE_KEY_SHA256:
        deny("PINNED_RELEASE_KEY_MISMATCH")
    target = parse_signed_manifest(
        raw,
        load(ROOT / "channel/stable.json.sig.b64", 1024),
        load(ROOT / path, 30000000),
        key,
    )
    expected_target_integrity(target)
    expected_candidate_receipt(target, allow_v189=True)
    print("SIGNED_RELEASE_PASS", target["release_id"], flush=True)
    return target


def run():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("package", "live", "dual"))
    args = parser.parse_args()
    try:
        target = verify_package()
        if args.mode == "package":
            return 0
        if args.mode == "dual":
            verify_dual_site(target, os.environ.get("JUDUN_STAGE_AUTH_TOKEN"))
        else:
            print("LIVE_DEEP_VERIFY_PASS", json.dumps(verify_target_live(target)), flush=True)
        return 0
    except (ValueError, OSError) as exc:
        message = str(exc)
        print(message if message.startswith("DIRECT_DEPLOY_") else "RELEASE_VERIFICATION_FAILED",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(run())
