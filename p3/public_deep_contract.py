"""Public JUDUN deep-health schema inventory (field names only; no values or secrets)."""
from __future__ import annotations

import json
from production_readiness import public_json

FIELDS = (
    "status", "artifact_id", "mismatch_count", "files_verified",
    "manifest_file_count", "deep_verified", "formal_evidence_sha256",
    "formal_data_sha256", "formal_seed_sha256", "formal_snapshot_sha256",
    "source_tree_sha256", "build_signature", "version", "display_version",
    "manifest_sha256", "manifest", "files", "managed_files", "critical_files",
    "app_sha256", "app_py_sha256", "file_hashes", "file_integrity",
)


def summary(public_result: dict) -> dict:
    if public_result.get("status") != "OK" or not isinstance(public_result.get("data"), dict):
        return {"status": "PUBLIC_SCHEMA_UNAVAILABLE", "field_types": {}}
    source = public_result["data"]
    fields = {
        k: ("bool" if isinstance(source[k], bool) else
            "int" if type(source[k]) is int else
            "str" if isinstance(source[k], str) else
            "null" if source[k] is None else "other")
        for k in FIELDS if k in source
    }
    return {
        "status": "PUBLIC_FIELD_NAMES_ONLY",
        "field_types": fields,
        "no_values_recorded": True,
        "no_credential_or_payment_actions": True,
    }


def main() -> int:
    result = summary(public_json("/health/artifact?deep=true"))
    print("P3_PUBLIC_DEEP_SCHEMA", json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
