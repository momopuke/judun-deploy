"""One-command, GET-only live acceptance for original JUDUN HTTPS v3 ZIP releases.

NO POST, no token, no deployment.  Checks a proposed local ZIP against the
freshly observed public LIVE build and deep artifact IDs, then runs the exact
historical Windows ZIP packaging contract. Passing cannot unlock deployment.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from https_receiver_bundle_audit import inspect_bundle
from production_readiness import public_json


def audit_against_current_live(bundle: Path, *, expected_target_artifact: str,
                               expected_version: str) -> dict:
    build_r = public_json("/health/build")
    deep_r = public_json("/health/artifact?deep=true")
    if build_r.get("status") != "OK" or deep_r.get("status") != "OK":
        raise ValueError("HTTPS_V3_FRESH_LIVE_IDENTITY_UNAVAILABLE")
    build = build_r.get("data")
    deep = deep_r.get("data")
    if not isinstance(build, dict) or not isinstance(deep, dict):
        raise ValueError("HTTPS_V3_UNTRUSTED_LIVE_RESPONSE")
    live_artifact = build.get("artifact_id")
    if (not isinstance(live_artifact, str)
            or deep.get("artifact_id") != live_artifact
            or deep.get("deep_verified") is not True
            or deep.get("status") != "ok"
            or type(deep.get("mismatch_count")) is not int
            or deep.get("mismatch_count") != 0):
        raise ValueError("HTTPS_V3_LIVE_IDENTITY_OR_INTEGRITY_DRIFT")
    live_formal = deep.get("formal_evidence_sha256")
    if not isinstance(live_formal, str):
        raise ValueError("HTTPS_V3_LIVE_FORMAL_SNAPSHOT_UNAVAILABLE")
    result = inspect_bundle(
        bundle,
        expected_base_artifact=live_artifact,
        live_artifact=live_artifact,
        expected_target_artifact=expected_target_artifact,
        expected_version=expected_version,
        live_formal_sha256=live_formal,
        live_mismatches=deep["mismatch_count"],
    )
    result["live_deep_verified"] = True
    result["verified_live_artifact"] = live_artifact
    result["next_step"] = "AUTHORIZED_RECEIVER_UPLOAD_NOT_PERFORMED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit original HTTPS v3 ZIP against public live build; NEVER upload.")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--target-artifact", required=True)
    parser.add_argument("--target-version", required=True)
    args = parser.parse_args()
    try:
        result = audit_against_current_live(
            args.bundle,
            expected_target_artifact=args.target_artifact,
            expected_version=args.target_version,
        )
        print("P3_HTTPS_V3_OFFLINE_PREFLIGHT", json.dumps(result, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        # Exception codes are fixed, never print private ZIP paths or contents.
        reason = str(exc)
        if not reason.startswith("HTTPS_V3_"):
            reason = "HTTPS_V3_PREFLIGHT_UNVERIFIED"
        print("P3_HTTPS_V3_PREFLIGHT_BLOCKED", json.dumps({"error_code": reason[:100]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
