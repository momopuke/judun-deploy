"""Safety contract for lightweight public expansion status adapter."""
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime
import unittest

from expansion_snapshot import write_event_snapshot
from expansion_health_adapter import public_expansion_health

NOW = "2026-10-20T00:00:00+00:00"
EPOCH = datetime.fromisoformat(NOW).timestamp()

DATA = {
    "status": "running", "phase": "fetch",
    "rounds_completed": 3, "validated_total": 12,
    "formal_records_added_total": 1, "last_progress_at": NOW,
    "checkpoint_verified": True,
}


class ExpansionHealthAdapterTests(unittest.TestCase):
    def test_fresh_running_has_no_intervention_permission(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "current.json"
            write_event_snapshot(path, DATA, updated_at=NOW)
            view = public_expansion_health(path, now_epoch=EPOCH + 10)
            self.assertEqual(view["expansion_state"], "running")
            self.assertTrue(view["observation_trustworthy"])
            self.assertEqual(view["validated_total"], 12)
            self.assertEqual(view["manual_next_action"], "none")
            self.assertFalse(view["automatic_restart_permitted"])
            self.assertFalse(view["formal_import_permitted"])
            self.assertNotIn("token", str(view))

    def test_stale_running_needs_investigation_without_restart(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "current.json"
            write_event_snapshot(path, DATA, updated_at=NOW)
            view = public_expansion_health(path, now_epoch=EPOCH + 500)
            self.assertEqual(view["expansion_state"], "progress_stale")
            self.assertFalse(view["observation_trustworthy"])
            self.assertEqual(view["manual_next_action"],
                             "investigate_checkpoint_and_worker")

    def test_stale_idle_not_misreported_as_healthy(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "current.json"
            write_event_snapshot(path, {**DATA, "status": "idle"}, updated_at=NOW)
            view = public_expansion_health(path, now_epoch=EPOCH + 500)
            self.assertEqual(view["expansion_state"], "snapshot_stale")
            self.assertEqual(view["last_known_status"], "idle")
            self.assertFalse(view["observation_trustworthy"])

    def test_completed_with_no_proof_requires_formal_checkpoint(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "current.json"
            write_event_snapshot(
                path, {**DATA, "status": "completed", "checkpoint_verified": False},
                updated_at=NOW,
            )
            view = public_expansion_health(path, now_epoch=EPOCH + 10)
            self.assertEqual(view["expansion_state"], "completion_unverified")
            self.assertEqual(view["manual_next_action"], "verify_formal_checkpoint")
            self.assertFalse(view["formal_import_permitted"])

    def test_missing_state_is_sanitized_and_never_starts_work(self):
        with TemporaryDirectory() as folder:
            view = public_expansion_health(Path(folder) / "missing.json",
                                          now_epoch=EPOCH)
            self.assertEqual(view["expansion_state"], "unknown")
            self.assertEqual(view["manual_next_action"],
                             "investigate_checkpoint_and_worker")
            self.assertIsNone(view["last_known_status"])
            self.assertFalse(view["automatic_restart_permitted"])
            self.assertNotIn("missing.json", str(view))

    def test_phase_scrubbing_propagates_to_public_health(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "current.json"
            write_event_snapshot(
                path, {**DATA, "phase": "https://internal/?token=abcdef"},
                updated_at=NOW,
            )
            view = public_expansion_health(path, now_epoch=EPOCH + 10)
            self.assertEqual(view["phase"], "other")
            self.assertNotIn("abcdef", str(view))

if __name__ == "__main__":
    unittest.main()
