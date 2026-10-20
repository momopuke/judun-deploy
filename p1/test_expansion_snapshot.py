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
            self.assertNotIn("AAAAAAA", path.read_text())
            self.assertEqual(read_public_snapshot(path,now_epoch=EPOCH)["phase"],"other")

    def test_url_token_and_exception_never_appear_in_public_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            raw_phase = "https://private.internal/key?token=CONFIDENTIAL"
            write_event_snapshot(path, {**SAMPLE, "phase":raw_phase},
                                 updated_at=NOW)
            content = path.read_text()
            self.assertNotIn("CONFIDENTIAL", content)
            self.assertNotIn("private.internal", content)
            self.assertEqual(read_public_snapshot(path, now_epoch=EPOCH)["phase"], "other")

    def test_corrupt_non_object_json_does_not_crash_status_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            for raw in ("[]", "null", "99", '"hello"'):
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    status = read_public_snapshot(path, now_epoch=EPOCH)
                    self.assertEqual(status["status"], "unknown")
                    self.assertFalse(status["automatic_restart_permitted"])

    def test_tampered_public_phase_rejected_on_read(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, SAMPLE, updated_at=NOW)
            payload = json.loads(path.read_text())
            payload["phase"] = "PASSWORD=1234"
            path.write_text(json.dumps(payload), encoding="utf-8")
            result = read_public_snapshot(path, now_epoch=EPOCH)
            self.assertEqual(result["status"], "unknown")
            self.assertNotIn("PASSWORD", str(result))

    def test_unhashable_status_fails_with_controlled_validation_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                write_event_snapshot(Path(tmp)/"status.json",
                                     {**SAMPLE, "status": {"running": True}},
                                     updated_at=NOW)

    def test_negative_or_boolean_count_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            for invalid in (-1,True,"50"):
                with self.subTest(invalid=invalid):
                    with self.assertRaises(ValueError):
                        write_event_snapshot(path,{**SAMPLE,"rounds_completed":invalid})

    def test_heartbeat_writes_cannot_reset_real_progress_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            # Controller emits a new status heartbeat, but no new checkpoint.
            update = "2026-10-20T00:10:00+00:00"
            write_event_snapshot(path, SAMPLE, updated_at=update)
            observed = read_public_snapshot(path, now_epoch=EPOCH+620, stale_after=180)
            self.assertEqual(observed["status"], "progress_stale")
            self.assertEqual(observed["last_progress_age_seconds"], 620)
            self.assertEqual(observed["snapshot_age_seconds"], 20)
            self.assertFalse(observed["snapshot_stale"])
            self.assertFalse(observed["automatic_restart_permitted"])

    def test_missing_real_progress_timestamp_is_not_running_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            without = {key:value for key,value in SAMPLE.items()
                       if key != "last_progress_at"}
            write_event_snapshot(path, without, updated_at=NOW)
            snap = read_public_snapshot(path, now_epoch=EPOCH+10)
            self.assertEqual(snap["status"], "progress_unknown")
            self.assertIsNone(snap["last_progress_age_seconds"])
            self.assertFalse(snap["automatic_restart_permitted"])

    def test_status_age_separate_from_real_progress_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, SAMPLE, updated_at=NOW)
            snap = read_public_snapshot(path, now_epoch=EPOCH+250)
            self.assertEqual(snap["status"], "progress_stale")
            self.assertTrue(snap["snapshot_stale"])
            self.assertEqual(snap["snapshot_age_seconds"], 250)

    def test_future_progress_and_status_cannot_claim_current_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            future = "2026-10-20T00:05:00+00:00"
            write_event_snapshot(path, {**SAMPLE, "last_progress_at": future},
                                 updated_at=NOW)
            snap = read_public_snapshot(path, now_epoch=EPOCH)
            self.assertEqual(snap["status"], "unknown")
            self.assertFalse(snap["automatic_restart_permitted"])
            write_event_snapshot(path, SAMPLE, updated_at=future)
            self.assertEqual(read_public_snapshot(path, now_epoch=EPOCH)["status"], "unknown")

    def test_tampered_snapshot_negative_count_fails_closed(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, SAMPLE, updated_at=NOW)
            snapshot = json.loads(path.read_text())
            snapshot["validated_total"] = -99
            path.write_text(json.dumps(snapshot), encoding="utf-8")
            self.assertEqual(read_public_snapshot(path, now_epoch=EPOCH)["status"], "unknown")

    def test_steady_idle_not_misreported_stalled(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"status.json"
            write_event_snapshot(path,{**SAMPLE,"status":"idle"},updated_at=NOW)
            state=read_public_snapshot(path,now_epoch=EPOCH+10000)
            self.assertEqual(state["status"],"snapshot_stale")
            self.assertEqual(state["last_known_status"],"idle")
            self.assertFalse(state["status_confident"])

    def test_idle_status_without_progress_never_invents_checkpoint_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            no_progress = {key: value for key, value in SAMPLE.items()
                           if key != "last_progress_at"}
            write_event_snapshot(path, {**no_progress, "status":"idle"},
                                 updated_at=NOW)
            state = read_public_snapshot(path, now_epoch=EPOCH+10)
            self.assertEqual(state["status"], "idle")
            self.assertIsNone(state["last_progress_at"])
            self.assertIsNone(state["last_progress_age_seconds"])

    def test_recent_idle_remains_idle_and_confident(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, {**SAMPLE, "status":"idle"}, updated_at=NOW)
            state = read_public_snapshot(path, now_epoch=EPOCH+10)
            self.assertEqual(state["status"], "idle")
            self.assertTrue(state["status_confident"])

    def test_completed_without_verified_checkpoint_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, {**SAMPLE, "status":"completed",
                                        "checkpoint_verified":False}, updated_at=NOW)
            state = read_public_snapshot(path, now_epoch=EPOCH+15)
            self.assertEqual(state["status"], "completion_unverified")
            self.assertEqual(state["last_known_status"], "completed")
            self.assertFalse(state["status_confident"])
            self.assertFalse(state["automatic_restart_permitted"])

    def test_valid_recent_completed_checkpoint_is_confident(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, {**SAMPLE, "status":"completed"}, updated_at=NOW)
            state = read_public_snapshot(path, now_epoch=EPOCH+15)
            self.assertEqual(state["status"], "completed")
            self.assertTrue(state["status_confident"])

    def test_last_progress_must_not_be_later_than_observation_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            stamp = "2026-10-20T00:03:00+00:00"
            write_event_snapshot(path, {**SAMPLE, "last_progress_at":stamp},
                                 updated_at=NOW)
            outcome = read_public_snapshot(path, now_epoch=EPOCH+220)
            self.assertEqual(outcome["status"],"unknown")

    def test_invalid_observation_clock_never_crashes_health_reader(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, SAMPLE, updated_at=NOW)
            for invalid in (float("nan"), float("inf"), -float("inf"),
                            True, "2026-10-20", {}, []):
                with self.subTest(invalid=repr(invalid)):
                    result = read_public_snapshot(path, now_epoch=invalid)
                    self.assertEqual(result["status"], "unknown")
                    self.assertFalse(result["automatic_restart_permitted"])

    def test_bool_stale_threshold_is_invalid(self):
        with self.assertRaises(ValueError):
            read_public_snapshot("/tmp/nonexistent.json", stale_after=True)

    def test_sequential_older_event_cannot_erase_newer_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            later = "2026-10-20T00:04:00+00:00"
            write_event_snapshot(path, {**SAMPLE,"rounds_completed":19},
                                 updated_at=later)
            prior = path.read_bytes()
            with self.assertRaisesRegex(ValueError,"regressed"):
                write_event_snapshot(path, {**SAMPLE,"rounds_completed":7},
                                     updated_at=NOW)
            self.assertEqual(path.read_bytes(), prior)
            self.assertEqual(read_public_snapshot(path,now_epoch=EPOCH+250)["rounds_completed"],19)

    def test_invalid_prior_clock_can_be_replaced_with_valid_snapshot(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_event_snapshot(path, SAMPLE, updated_at=NOW)
            old = json.loads(path.read_text())
            old["updated_at"]="invalid"
            path.write_text(json.dumps(old),encoding="utf-8")
            write_event_snapshot(path, SAMPLE,updated_at=NOW)
            self.assertEqual(read_public_snapshot(path,now_epoch=EPOCH+10)["status"],"running")

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
