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
from production_readiness import (
    public_json, assess_public_deep_integrity, assess_snapshot_stability,
    parse_public_build_identity,
)


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
    identity = parse_public_build_identity(build_r)
    if identity is None:
        raise ValueError("HTTPS_V3_FRESH_LIVE_IDENTITY_UNAVAILABLE")
    live_artifact = identity["artifact_id"]
    live_version = identity["version"]
    # Shared with read-only production readiness. Do not accept a shallow
    # probe, a missing SHA, an unverified manifest count or a stale artifact.
    integrity_decision = assess_public_deep_integrity(
        deep_r, live_artifact=live_artifact, live_version=live_version
    )
    if integrity_decision != "PASS" or not live_artifact.startswith(f"JUDUN-{live_version}-"):
        raise ValueError("HTTPS_V3_LIVE_IDENTITY_OR_INTEGRITY_DRIFT")
    live_formal = deep["formal_evidence_sha256"]
    result = inspect_bundle(
        bundle,
        expected_base_artifact=live_artifact,
        live_artifact=live_artifact,
        expected_target_artifact=expected_target_artifact,
        expected_version=expected_version,
        live_formal_sha256=live_formal,
        live_mismatches=deep["mismatch_count"],
    )
    # Bracket the expensive local ZIP hash audit with fresh public reads.
    # A release may be promoted while inspect_bundle() is hashing a ZIP.
    # Never permit a previously observed base artifact to authorize a
    # later upload against a changed or partially verified live release.
    final_build_r = public_json("/health/build")
    final_deep_r = public_json("/health/artifact?deep=true")
    if assess_snapshot_stability(
        final_build_r, initial_artifact=live_artifact,
        initial_version=live_version
    ) != "CONSISTENT":
        raise ValueError("HTTPS_V3_LIVE_CHANGED_DURING_PREFLIGHT")
    if assess_public_deep_integrity(
        final_deep_r, live_artifact=live_artifact,
        live_version=live_version
    ) != "PASS":
        raise ValueError("HTTPS_V3_FINAL_DEEP_INTEGRITY_UNVERIFIED")
    # Both reads must describe precisely the same public integrity state.
    # Matching artifact identity alone does not guarantee a stable manifest.
    final_deep = final_deep_r["data"]
    for field in (
        "version", "artifact_id", "formal_evidence_sha256",
        "source_tree_sha256", "files_verified",
        "manifest_file_count", "mismatch_count", "deep_verified",
    ):
        if final_deep.get(field) != deep.get(field):
            raise ValueError("HTTPS_V3_DEEP_SNAPSHOT_CHANGED_DURING_PREFLIGHT")
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
