"""Cross-process serialization contract for Linux expansion health."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import stat
import unittest

from expansion_snapshot import read_public_snapshot, write_event_snapshot
from snapshot_write_lock import exclusive_status_lock


class SnapshotInterprocessLockTests(unittest.TestCase):
    def test_same_snapshot_cannot_be_locked_twice_concurrently(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "expansion.json"
            with exclusive_status_lock(target):
                with self.assertRaisesRegex(TimeoutError, "snapshot writer busy"):
                    with exclusive_status_lock(target, timeout_seconds=0.03):
                        self.fail("concurrent lock must not be acquired")
            with exclusive_status_lock(target, timeout_seconds=0.1):
                self.assertTrue((Path(str(target) + ".lock")).is_file())

    def test_writer_cannot_replace_under_concurrent_snapshot_lock(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "expansion.json"
            baseline = {
                "status": "running", "phase": "fetch",
                "rounds_completed": 5, "validated_total": 7,
                "formal_records_added_total": 1,
                "last_progress_at": "2026-10-20T00:00:00+00:00",
            }
            write_event_snapshot(path, baseline,
                                 updated_at="2026-10-20T00:00:00+00:00")
            original = path.read_bytes()
            with exclusive_status_lock(path):
                with self.assertRaises(TimeoutError):
                    write_event_snapshot(
                        path, {**baseline, "rounds_completed": 20},
                        updated_at="2026-10-20T00:01:00+00:00")
                self.assertEqual(path.read_bytes(), original)
            write_event_snapshot(
                path, {**baseline, "rounds_completed": 20},
                updated_at="2026-10-20T00:01:00+00:00")
            saved = json.loads(path.read_text())
            self.assertEqual(saved["rounds_completed"], 20)

    def test_invalid_timeout_never_enters_unbounded_lock_polling(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "expansion.json"
            for bad in (0, -1, float("nan"), float("inf"), True, "forever", 9):
                with self.subTest(value=repr(bad)):
                    with self.assertRaises(ValueError):
                        with exclusive_status_lock(path, timeout_seconds=bad):
                            self.fail("invalid timeout must not lock")

    def test_named_pipe_cannot_be_accepted_as_snapshot_lock(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "status.json"
            pipe = Path(str(target) + ".lock")
            os.mkfifo(pipe)
            with self.assertRaisesRegex(ValueError, "untrusted"):
                with exclusive_status_lock(target):
                    self.fail("FIFO is not a safe lock file")

    def test_preexisting_world_readable_lock_is_secured(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "status.json"
            lock = Path(str(target) + ".lock")
            lock.write_text("")
            os.chmod(lock, 0o666)
            with exclusive_status_lock(target):
                self.assertEqual(stat.S_IMODE(lock.stat().st_mode), 0o600)

    def test_lock_symlink_to_other_file_is_rejected(self):
        with TemporaryDirectory() as tmp:
            target = Path(tmp) / "status.json"
            pointed = Path(tmp) / "other.txt"
            pointed.write_text("must not touch")
            Path(str(target) + ".lock").symlink_to(pointed)
            with self.assertRaises(OSError):
                with exclusive_status_lock(target):
                    self.fail("symlink must not be accepted")
            self.assertEqual(pointed.read_text(), "must not touch")

    def test_lock_file_stays_private_and_persistent(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "expansion.json"
            with exclusive_status_lock(path):
                lock = Path(str(path) + ".lock")
                self.assertTrue(lock.exists())
                self.assertEqual(stat.S_IMODE(lock.stat().st_mode) & 0o077, 0)
            self.assertTrue(lock.exists())  # Do not unlink in-use lock inode.


if __name__ == "__main__":
    unittest.main()
