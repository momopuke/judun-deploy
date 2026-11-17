"""Offline regression tests for the separate staging store and rollback."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from staging_release import (
    MANIFEST, Release, initialize, prepare, process_state, recover, selection,
    store_lock, verify_snapshot,
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


if __name__ == "__main__":
    unittest.main()
