"""No-VPS, no-delete regressions for release-archive retention."""
import hashlib
import tempfile
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_retention_plan import plan, verify_release_files

CURRENT = "JUDUN-1.2.122-C597F753F43B"
PREVIOUS = "JUDUN-1.2.120-9ABCDEF0"
OLD = "JUDUN-1.2.114-AA38F0567A4D"


def item(artifact, suffix, **kw):
    return {
        "kind": "release_rollback_archive",
        "artifact_id": artifact,
        "name": f"judun-release-{suffix}.tar.gz",
        "sha256": ("a" if suffix == "now" else "b" if suffix == "prev" else "c") * 64,
        "size_bytes": 150000,
        "regular_file_verified": True,
        "digest_verified": True,
        **kw,
    }


def sample():
    return {"schema": "judun.release-backup-inventory.v1", "entries": [
        item(CURRENT, "now"), item(PREVIOUS, "prev"), item(OLD, "old"),
        {"kind": "formal_data_backup", "name": "customers.sqlite.bak"},
        {"kind": "droplet_snapshot", "name": "DO-provider-snapshot"},
    ]}


class ReleaseRetentionSafetyTests(unittest.TestCase):
    def test_preserves_current_previous_and_unrelated_formal_data(self):
        output = plan(sample(), current_artifact=CURRENT, previous_artifact=PREVIOUS)
        self.assertEqual(output["decision"], "REVIEW_ONLY_NOT_EXECUTED")
        self.assertEqual(
            {x["artifact_id"] for x in output["retain_release_archives"]},
            {CURRENT, PREVIOUS},
        )
        self.assertEqual(
            [x["artifact_id"] for x in output["older_release_archives_for_manual_review"]],
            [OLD],
        )
        self.assertEqual(output["unrelated_or_formal_data_entries_untouched"], 2)
        self.assertFalse(output["formal_backup_policy_changed"])
        self.assertEqual(output["releases_auto_deleted"], 0)
        self.assertFalse(output["delete_command_generated"])

    def test_no_current_archive_is_required_when_live_is_installed(self):
        inventory = sample()
        inventory["entries"].pop(0)
        p = plan(inventory, current_artifact=CURRENT, previous_artifact=PREVIOUS)
        self.assertEqual([x["artifact_id"] for x in p["retain_release_archives"]],
                         [PREVIOUS])

    def test_missing_or_unverified_previous_blocks_cleanup(self):
        for modifier in (
            lambda inv: inv["entries"].pop(1),
            lambda inv: inv["entries"][1].update(digest_verified=False),
            lambda inv: inv["entries"][1].update(regular_file_verified=False),
            lambda inv: inv["entries"][1].update(sha256="not-a-sha"),
            lambda inv: inv["entries"][1].update(size_bytes=0),
        ):
            inv = sample()
            modifier(inv)
            with self.assertRaises(ValueError):
                plan(inv, current_artifact=CURRENT, previous_artifact=PREVIOUS)

    def test_duplicate_release_artifact_or_filename_fails_closed(self):
        for duplicate in (item(PREVIOUS, "extra"), item(OLD, "prev")):
            inv = sample()
            inv["entries"].append(duplicate)
            with self.assertRaises(ValueError):
                plan(inv, current_artifact=CURRENT, previous_artifact=PREVIOUS)

    def test_invalid_names_and_file_identity_never_enter_review_plan(self):
        for bad in ("../escape", "/tmp/file", ".hidden", "folder/backup.zip",
                    "release..old", "filename with spaces"):
            inv = sample()
            inv["entries"][2]["name"] = bad
            with self.subTest(name=bad), self.assertRaises(ValueError):
                plan(inv, current_artifact=CURRENT, previous_artifact=PREVIOUS)

    def test_identity_and_registry_schema_required(self):
        with self.assertRaises(ValueError):
            plan(sample(), current_artifact=PREVIOUS, previous_artifact=PREVIOUS)
        with self.assertRaises(ValueError):
            plan({"entries": []}, current_artifact=CURRENT, previous_artifact=PREVIOUS)
        with self.assertRaises(ValueError):
            plan({"schema": "judun.release-backup-inventory.v1", "entries": []},
                 current_artifact=CURRENT, previous_artifact=PREVIOUS)

    def test_rejects_newer_or_same_version_as_previous_release(self):
        current = "JUDUN-1.2.122-C597F753F43B"
        candidates = (
            "JUDUN-1.2.123-NEXT",
            "JUDUN-1.2.122-PREVIOUS-BUILD",
        )
        for previous in candidates:
            with self.subTest(previous=previous), self.assertRaisesRegex(
                ValueError, "PREVIOUS_RELEASE_NOT_OLDER"
            ):
                plan(sample(), current_artifact=current, previous_artifact=previous)

    def test_no_paths_data_or_customer_tokens_in_output(self):
        inv = sample()
        inv["entries"].append({"kind": "formal_data_backup",
                               "name": "/secrets/customer-data-payment.sql",
                               "token": "private-token"})
        output = plan(inv, current_artifact=CURRENT, previous_artifact=PREVIOUS)
        self.assertNotIn("private-token", str(output))
        self.assertNotIn("/secrets", str(output))
        self.assertEqual(output["unrelated_or_formal_data_entries_untouched"], 3)


class ArchiveByteVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inventory = sample()
        for entry in self.inventory["entries"]:
            if entry.get("kind") != "release_rollback_archive":
                continue
            data = ("verified-archive-content:" + entry["artifact_id"]).encode()
            (self.root / entry["name"]).write_bytes(data)
            entry["size_bytes"] = len(data)
            entry["sha256"] = hashlib.sha256(data).hexdigest()
            entry["regular_file_verified"] = False
            entry["digest_verified"] = False

    def test_current_previous_are_verified_from_real_bytes_before_plan(self):
        verified = verify_release_files(self.root, self.inventory)
        output = plan(verified, current_artifact=CURRENT, previous_artifact=PREVIOUS)
        self.assertEqual(len(output["retain_release_archives"]), 2)
        self.assertEqual(len(output["older_release_archives_for_manual_review"]), 1)
        self.assertEqual(output["releases_auto_deleted"], 0)
        self.assertFalse(self.inventory["entries"][0]["digest_verified"])

    def test_tampered_archive_never_qualifies_for_review(self):
        entry = self.inventory["entries"][2]
        (self.root / entry["name"]).write_bytes(b"tampered-release")
        with self.assertRaises(ValueError):
            verify_release_files(self.root, self.inventory)

    def test_symlink_never_read_as_release_archive(self):
        entry = self.inventory["entries"][1]
        target = self.root / entry["name"]
        target.unlink()
        target.symlink_to(self.root / self.inventory["entries"][0]["name"])
        with self.assertRaises(ValueError):
            verify_release_files(self.root, self.inventory)

    def test_special_files_and_wrong_archive_size_block(self):
        entry = self.inventory["entries"][1]
        target = self.root / entry["name"]
        target.unlink()
        target.mkdir()
        with self.assertRaises(ValueError):
            verify_release_files(self.root, self.inventory)
        target.rmdir()
        target.write_bytes(b"X")
        with self.assertRaises(ValueError):
            verify_release_files(self.root, self.inventory)

    def test_not_open_formal_db_or_snapshots(self):
        unrelated = self.inventory["entries"][3]
        unrelated["name"] = "/sensitive/protected-customer.db"
        verified = verify_release_files(self.root, self.inventory)
        self.assertEqual(verified["entries"][3], unrelated)
        self.assertEqual(
            plan(verified, current_artifact=CURRENT, previous_artifact=PREVIOUS)
                ["unrelated_or_formal_data_entries_untouched"], 2
        )

    def test_root_symlink_and_nonexistent_directory_block(self):
        root_link = self.root / "other-root"
        root_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "BACKUP_ROOT"):
            verify_release_files(root_link, self.inventory)
        with self.assertRaisesRegex(ValueError, "BACKUP_ROOT"):
            verify_release_files(self.root / "missing", self.inventory)



if __name__ == "__main__":
    unittest.main()
