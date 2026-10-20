"""Regression suite for the archived Windows HTTPS v3 receiver ZIP format.

Fixtures are tiny synthetic data, never live source or payment credentials.
"""
from __future__ import annotations

import base64
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parent))
from https_receiver_bundle_audit import inspect_bundle, digest, MANIFEST_PATH, REQUIRED_EMBEDDED_FILES
from production_delta_patch import computed_tree_sha


BASE = "JUDUN-1.2.114-AA38F0567A4D"
TARGET = "JUDUN-1.2.115-21P3A85DF204"
VERSION = "1.2.115"
FORMAL = "c" * 64
INSTANCE = "1.2.115-20261021-TEST-FIXTURE"
SIGNATURE = "JUDUN_1.2.115_SYNTHETIC_FIXTURE"


def row(path: str, data: bytes) -> dict:
    return {"path": path, "size": len(data), "sha256": digest(data)}


def make_members() -> dict[str, bytes]:
    files = {"app.py": b"# synthetic application fixture; never used on VPS\n"}
    for path in sorted(REQUIRED_EMBEDDED_FILES):
        files[path] = (b"synthetic-source:" + path.encode("ascii") + b"\n")
    runtime = [row(name, data) for name, data in files.items()]
    manifest_inner = {
        "version": VERSION,
        "artifact_id": TARGET,
        "build_signature": SIGNATURE,
        "build_instance_id": INSTANCE,
        "source_tree_sha256": computed_tree_sha(runtime),
        "files": runtime,
    }
    memory = BytesIO()
    with ZipFile(memory, "w", ZIP_DEFLATED) as embedded:
        for name, data in files.items():
            embedded.writestr(name, data)
        embedded.writestr("DEPLOY_MANIFEST.json", json.dumps(manifest_inner).encode())
    blob = memory.getvalue()
    deploy_script = (
        b"#!/bin/bash\n# R3.3 embedded data-expansion runtime\n"
        + b"cat <<'JUDUN_RUNTIME_B64'\n"
        + base64.b64encode(blob) + b"\nJUDUN_RUNTIME_B64\n"
    )
    runtime_lock = {
        "artifact_id": TARGET,
        "version": VERSION,
        "build_instance_id": INSTANCE,
        "build_signature": SIGNATURE,
        "formal_evidence_sha256": FORMAL,
        "runtime_tree_sha256": computed_tree_sha(runtime),
        "runtime_bundle_sha256": digest(blob),
        "runtime_bundle_bytes": len(blob),
        "files": [
            {**item, "source_path": "system_files/" + item["path"]}
            for item in runtime
        ],
    }
    release = {
        "artifact_id": TARGET,
        "version": VERSION,
        "display_version": "v" + VERSION,
        "build_signature": SIGNATURE,
        "build_instance_id": INSTANCE,
    }
    members = {
        "RELEASE.json": json.dumps(release).encode(),
        "RUNTIME_RELEASE_LOCK.json": json.dumps(runtime_lock).encode(),
        "system_files/deploy_paid_test.sh": deploy_script,
        **{"system_files/" + name: data for name, data in files.items()},
    }
    outer_rows = [row(name, data) for name, data in members.items()]
    manifest = {
        "schema": "judun.deploy-manifest.v1",
        "artifact_id": TARGET,
        "version": VERSION,
        "display_version": "v" + VERSION,
        "build_signature": SIGNATURE,
        "build_instance_id": INSTANCE,
        "formal_evidence_sha256": FORMAL,
        "source_tree_sha256": computed_tree_sha(outer_rows),
        "deployment_policy": {
            "formal_seed_write_locked": True,
            "persistent_formal_db_additive_only": True,
            "post_deploy_deep_verification_required": True,
            "formal_backup_keep_versions": 3,
        },
        "files": outer_rows,
    }
    members[MANIFEST_PATH] = json.dumps(manifest).encode()
    return members


def save(path: Path, members: dict[str, bytes]):
    with ZipFile(path, "w", ZIP_DEFLATED) as zipfile:
        for name, contents in members.items():
            zipfile.writestr(name, contents)


def audit(path: Path, **overrides):
    params = dict(
        expected_base_artifact=BASE, live_artifact=BASE,
        expected_target_artifact=TARGET, expected_version=VERSION,
        live_formal_sha256=FORMAL, live_mismatches=0,
    )
    params.update(overrides)
    return inspect_bundle(path, **params)


class OriginalHttpsReceiverPackageTests(unittest.TestCase):
    def test_valid_synthetic_package_audits_both_separate_trees(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"
            save(path, make_members())
            result = audit(path)
            self.assertEqual(result["status"], "BUNDLE_VALIDATED_OFFLINE_ONLY")
            self.assertEqual(result["managed_package_files"], 13)
            self.assertEqual(result["locked_runtime_files"], 10)
            self.assertTrue(result["embedded_runtime_sha256_verified"])
            self.assertFalse(result["receiver_authentication_verified"])
            self.assertFalse(result["actual_vps_deployment"])

    def test_rejects_live_drift_and_existing_target_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"
            save(path, make_members())
            for altered in (
                {"live_artifact": "JUDUN-1.2.113-STALE"},
                {"live_artifact": TARGET},
                {"live_mismatches": 1},
                {"live_formal_sha256": "d" * 64},
            ):
                with self.subTest(altered=altered), self.assertRaises(ValueError):
                    audit(path, **altered)

    def test_rejects_drifted_payload_and_untracked_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"
            members = make_members()
            members["system_files/app.py"] = b"unreviewed change"
            save(path, members)
            with self.assertRaisesRegex(ValueError, "UNREVIEWED_PACKAGE_FILE_DRIFT"):
                audit(path)
            members = make_members()
            members["other_secret.txt"] = b"not approved"
            save(path, members)
            with self.assertRaisesRegex(ValueError, "UNTRACKED_OR_MISSING_PACKAGE_MEMBER"):
                audit(path)

    def test_rejects_runtime_lock_and_release_identity_spoofs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"
            members = make_members()
            release = json.loads(members["RELEASE.json"])
            release["version"] = "1.2.999"
            members["RELEASE.json"] = json.dumps(release).encode()
            save(path, members)
            with self.assertRaisesRegex(ValueError, "PACKAGE_TARGET_IDENTITY_MISMATCH"):
                audit(path)
            members = make_members()
            # Must re-sign the outer fingerprint in test only: otherwise outer
            # SHA gate also rightly blocks the changed runtime lock.
            lock = json.loads(members["RUNTIME_RELEASE_LOCK.json"])
            lock["runtime_tree_sha256"] = "f" * 64
            members["RUNTIME_RELEASE_LOCK.json"] = json.dumps(lock).encode()
            manifest = json.loads(members[MANIFEST_PATH])
            manifest["files"] = [
                row(n, v) for n, v in members.items() if n != MANIFEST_PATH
            ]
            manifest["source_tree_sha256"] = computed_tree_sha(manifest["files"])
            members[MANIFEST_PATH] = json.dumps(manifest).encode()
            save(path, members)
            with self.assertRaisesRegex(ValueError, "RUNTIME_TREE_DIGEST_MISMATCH"):
                audit(path)

    def test_rejects_invalid_zip_paths_and_non_zip_cms_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"
            path.write_bytes(b"CMS encrypted payload, not HTTPS application/zip")
            with self.assertRaisesRegex(ValueError, "UNREADABLE_OR_INVALID_ZIP"):
                audit(path)
            members = make_members()
            members["../escape.txt"] = b"unsafe"
            save(path, members)
            with self.assertRaisesRegex(ValueError, "UNSAFE_OR_NONCANONICAL_ZIP_PATH"):
                audit(path)

    def test_rejects_missing_snapshot_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"
            members = make_members()
            manifest = json.loads(members[MANIFEST_PATH])
            manifest["deployment_policy"]["formal_backup_keep_versions"] = 0
            members[MANIFEST_PATH] = json.dumps(manifest).encode()
            save(path, members)
            with self.assertRaisesRegex(ValueError, "BACKUP_OR_FORMAL_DATA_POLICY_MISMATCH"):
                audit(path)


    def test_embedded_runtime_mutations_do_not_bypass_outer_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"

            def resync_outer(members):
                outer = json.loads(members[MANIFEST_PATH])
                outer["files"] = [row(n, content) for n, content in members.items()
                                  if n != MANIFEST_PATH]
                outer["source_tree_sha256"] = computed_tree_sha(outer["files"])
                members[MANIFEST_PATH] = json.dumps(outer).encode()
                save(path, members)

            members = make_members()
            members.pop("system_files/deploy_paid_test.sh")
            resync_outer(members)
            with self.assertRaisesRegex(ValueError, "MISSING_EMBEDDED_DEPLOY_SCRIPT"):
                audit(path)

            members = make_members()
            script = members["system_files/deploy_paid_test.sh"]
            members["system_files/deploy_paid_test.sh"] = script.replace(
                b"R3.3 embedded", b"R3.2 embedded")
            resync_outer(members)
            with self.assertRaisesRegex(ValueError, "MISSING_RUNTIME_EMBED_MARKER"):
                audit(path)

            members = make_members()
            lock = json.loads(members["RUNTIME_RELEASE_LOCK.json"])
            lock["runtime_bundle_bytes"] += 1
            members["RUNTIME_RELEASE_LOCK.json"] = json.dumps(lock).encode()
            resync_outer(members)
            with self.assertRaisesRegex(ValueError, "EMBEDDED_RUNTIME_LOCK_DIGEST_MISMATCH"):
                audit(path)

    def test_original_windows_crlf_embedded_marker_is_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.zip"
            members = make_members()
            name = "system_files/deploy_paid_test.sh"
            members[name] = members[name].replace(b"\n", b"\r\n")
            manifest = json.loads(members[MANIFEST_PATH])
            manifest["files"] = [row(n, v) for n, v in members.items() if n != MANIFEST_PATH]
            manifest["source_tree_sha256"] = computed_tree_sha(manifest["files"])
            members[MANIFEST_PATH] = json.dumps(manifest).encode()
            save(path, members)
            result = audit(path)
            self.assertTrue(result["embedded_runtime_sha256_verified"])


    def test_inner_zip_cannot_omit_or_invent_members_even_when_outer_digests_match(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "release.zip"
            for mode, rejection in (
                ("missing", "EMBEDDED_FILE_INVENTORY_MISMATCH"),
                ("extra", "EMBEDDED_FILE_INVENTORY_MISMATCH"),
                ("changed", "EMBEDDED_FILE_BYTES_MISMATCH"),
            ):
                with self.subTest(mode=mode):
                    members = make_members()
                    script_name = "system_files/deploy_paid_test.sh"
                    script = members[script_name]
                    head, marker, tail = script.partition(b"cat <<'JUDUN_RUNTIME_B64'\n")
                    assert marker
                    encoded, endmarker, suffix = tail.partition(b"\nJUDUN_RUNTIME_B64")
                    assert endmarker
                    original_zip = base64.b64decode(encoded)
                    with ZipFile(BytesIO(original_zip)) as archive:
                        entries = {n: archive.read(n) for n in archive.namelist()}
                    if mode == "missing":
                        del entries["app.py"]
                    elif mode == "extra":
                        entries["untracked.py"] = b"unreviewed"
                    else:
                        entries["app.py"] = b"tampered source"
                    buffer = BytesIO()
                    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
                        for name, content in entries.items():
                            archive.writestr(name, content)
                    nested = buffer.getvalue()
                    members[script_name] = head + marker + base64.b64encode(nested) + endmarker + suffix
                    lock = json.loads(members["RUNTIME_RELEASE_LOCK.json"])
                    lock["runtime_bundle_bytes"] = len(nested)
                    lock["runtime_bundle_sha256"] = digest(nested)
                    members["RUNTIME_RELEASE_LOCK.json"] = json.dumps(lock).encode()
                    manifest = json.loads(members[MANIFEST_PATH])
                    manifest["files"] = [
                        row(name, content) for name, content in members.items()
                        if name != MANIFEST_PATH
                    ]
                    manifest["source_tree_sha256"] = computed_tree_sha(manifest["files"])
                    members[MANIFEST_PATH] = json.dumps(manifest).encode()
                    save(output, members)
                    with self.assertRaisesRegex(ValueError, rejection):
                        audit(output)


if __name__ == "__main__":
    unittest.main()
