"""Tests for bounded, privacy-safe expansion status snapshots."""
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
from expansion_snapshot import write_event_snapshot, read_public_snapshot

NOW = "2026-10-20T00:00:00+00:00"
EPOCH = datetime.fromisoformat(NOW).timestamp()
SAMPLE = dict(status="running", phase="fetch", rounds_completed=10,
              validated_total=33, formal_records_added_total=490,
              checkpoint_verified=True, last_progress_at=NOW)

class SnapshotTests(unittest.TestCase):
    def test_alive_snapshot_is_fast_small_and_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            write_event_snapshot(path, {**SAMPLE, "source_url": "private URL",
                                        "token": "DO_NOT_EXPOSE"}, updated_at=NOW)
            self.assertLess(path.stat().st_size, 1000)
            saved=path.read_text()
            self.assertNotIn("DO_NOT_EXPOSE", saved)
            self.assertNotIn("source_url", saved)
            status=read_public_snapshot(path,now_epoch=EPOCH+30)
            self.assertEqual(status["status"],"running")
            self.assertEqual(status["validated_total"],33)
            self.assertFalse(status["automatic_restart_permitted"])

    def test_progress_stale_does_not_claim_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            write_event_snapshot(path,SAMPLE,updated_at=NOW)
            state=read_public_snapshot(path,now_epoch=EPOCH+210)
            self.assertEqual(state["status"],"progress_stale")
            self.assertEqual(state["last_known_status"],"running")
            self.assertTrue(state["checkpoint_verified"])
            self.assertFalse(state["automatic_restart_permitted"])

    def test_missing_file_fails_without_restarting(self):
        v=read_public_snapshot("/tmp/__nonexistent_judun_status_fake__.json")
        self.assertEqual(v["status"],"unknown")
        self.assertFalse(v["automatic_restart_permitted"])

    def test_corrupt_snapshot_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            path.write_text("{broken")
            self.assertEqual(read_public_snapshot(path)["status"],"unknown")

    def test_malicious_oversized_payload_not_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            data={**SAMPLE,"phase":"A"*20000}
            write_event_snapshot(path,data,updated_at=NOW)
            self.assertLess(path.stat().st_size,1024)

    def test_negative_or_boolean_count_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            for invalid in (-1,True,"50"):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        write_event_snapshot(path,{**SAMPLE,"rounds_completed":invalid})

    def test_steady_idle_not_misreported_stalled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            write_event_snapshot(path,{**SAMPLE,"status":"idle"},updated_at=NOW)
            state=read_public_snapshot(path,now_epoch=EPOCH+10000)
            self.assertEqual(state["status"],"idle")

    def test_only_complete_committed_snapshot_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            write_event_snapshot(path,{**SAMPLE,"rounds_completed":1},updated_at=NOW)
            write_event_snapshot(path,{**SAMPLE,"rounds_completed":2},updated_at=NOW)
            state=read_public_snapshot(path,now_epoch=EPOCH+5)
            self.assertEqual(state["rounds_completed"],2)
            self.assertFalse(list(Path(tmp).glob("*.tmp")))

if __name__ == "__main__":
    unittest.main()
