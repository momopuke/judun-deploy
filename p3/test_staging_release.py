"""Offline regression tests for the separate staging store and rollback."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from staging_release import (
    MANIFEST, KNOWN_R1_SANDBOX_IDENTITY, Release, check_running,
    initialize, prepare, process_state, recover, selection, store_lock,
    verify_snapshot,
)


class StagingReleaseTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name)
        self.root = self.work / "stage-code"

    def artifact(self, patch, *, alter=False):
        content = f"# Synthetic fixture {patch}\n".encode()
        digest = hashlib.sha256(content).hexdigest()
        size = len(content)
        tree = hashlib.sha256(f"app.py\t{digest}\t{size}\n".encode()).hexdigest()
        release = Release(f"1.2.{patch}", f"FIXTURE-{patch}", f"BUILD-{patch}", tree, 1)
        manifest = {
            "schema": "judun.deploy-manifest.v1",
            "version": release.version,
            "artifact_id": release.artifact_id,
            "build_instance_id": release.build_instance_id,
            "source_tree_sha256": tree,
            "files": [{"path": "app.py", "sha256": digest, "size": size}],
        }
        source = self.work / f"{patch}.zip"
        with ZipFile(source, "w") as archive:
            archive.writestr("payload/" + MANIFEST, json.dumps(manifest))
            archive.writestr("payload/app.py", b"!" + content[1:] if alter else content)
            archive.writestr("payload/extra.py", "must not be extracted")
        return release, source

    def test_only_verified_manifest_files_are_copied(self):
        release, source = self.artifact(901)
        before = source.read_bytes()
        self.assertEqual(prepare(self.root, source, release), release)
        initialize(self.root, release.name)
        look = selection(self.root)
        self.assertEqual(verify_snapshot(look), release)
        self.assertFalse((look / "extra.py").exists())
        self.assertEqual(before, source.read_bytes())

    def test_modified_package_leaves_no_release_snapshot(self):
        release, source = self.artifact(901, alter=True)
        with self.assertRaisesRegex(ValueError, "Candidate contents mismatch"):
            prepare(self.root, source, release)
        self.assertEqual(list((self.root / "releases").iterdir()), [])
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            prepare(self.root, source, replace(release, source_tree_sha256="0" * 64))

    def test_failed_candidate_restarts_previous_and_does_not_leave_pending(self):
        old, new = (prepare(self.root, source, release)
                    for release, source in (self.artifact(901), self.artifact(902)))
        initialize(self.root, old.name)
        restarted = []

        def restart():
            restarted.append(selection(self.root).name)

        def wait(release):
            if release == new:
                raise RuntimeError("synthetic candidate failure")

        with store_lock(self.root), self.assertRaisesRegex(RuntimeError, "candidate failure"):
            process_state(self.root, new.name, restart, wait)
        self.assertEqual(restarted, [new.name, old.name])
        self.assertEqual(selection(self.root).name, old.name)
        self.assertFalse((self.root / ".switch-pending.json").exists())

    def test_interrupted_switch_preserves_verified_recovery_target(self):
        old, new = (prepare(self.root, source, release)
                    for release, source in (self.artifact(901), self.artifact(902)))
        initialize(self.root, new.name)
        (self.root / ".switch-pending.json").write_text(
            json.dumps({"previous": old.name, "target": new.name}), encoding="utf-8")
        with store_lock(self.root):
            with self.assertRaisesRegex(ValueError, "switch was interrupted"):
                process_state(self.root, old.name, lambda: None, lambda release: None)
            recover(self.root, lambda: None, lambda target: self.assertEqual(target, old))
        self.assertEqual(selection(self.root).name, old.name)



class StagingPaymentModeGateTest(unittest.TestCase):
    """Live stage proof must accept the pinned R1, never another sandbox."""

    def setUp(self):
        self.r1 = Release(*KNOWN_R1_SANDBOX_IDENTITY)
        self.rc1 = Release(
            "1.2.190", "JUDUN-1.2.190-SINGLEPASS-RC1-UNSIGNED",
            "1.2.190-SINGLEPASS-RC1-20261118",
            "1d5a73989525643a4da6c58b36263bdcc644a3f3780fb335b968e33e7de7866a", 98)

    def verify(self, release, payment_mode, accepted):
        common = dict(
            version=release.version, artifact_id=release.artifact_id,
            build_instance_id=release.build_instance_id,
            source_tree_sha256=release.source_tree_sha256,
        )
        responses = {
            "/health/build": {**common, "payment_mode": payment_mode, "status": "ok"},
            "/health/artifact?deep=true": {
                **common, "status": "ok", "deep_verified": True,
                "mismatch_count": 0, "files_verified": release.file_count,
                "manifest_file_count": release.file_count,
            },
            "/health/ready": {"status": "ready", "version": release.version},
        }
        with patch("staging_release.fetch_health",
                   side_effect=lambda port, endpoint, timeout: responses[endpoint]):
            if accepted:
                self.assertIsNone(check_running(release, timeout=0))
            else:
                with self.assertRaisesRegex(RuntimeError, "Staging health did not match"):
                    check_running(release, timeout=0)

    def test_existing_exact_r1_sandbox_is_a_valid_pre_switch_and_rollback_base(self):
        self.verify(self.r1, "ecpay_stage", True)

    def test_r1_cannot_silently_claim_test_unlock(self):
        self.verify(self.r1, "test_unlock", False)

    def test_rc1_remains_test_unlock_only(self):
        self.verify(self.rc1, "test_unlock", True)
        self.verify(self.rc1, "ecpay_stage", False)

    def test_r1_tree_drift_is_not_allowed_to_claim_sandbox(self):
        self.verify(replace(self.r1, source_tree_sha256="0" * 64), "ecpay_stage", False)

    def test_no_live_ecpay_mode_is_accepted(self):
        self.verify(self.r1, "ecpay_live", False)
        self.verify(self.rc1, "ecpay_live", False)



if __name__ == "__main__":
    unittest.main()
