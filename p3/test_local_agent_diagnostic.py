"""Synthetic local agent diagnostic tests; never reach the VPS."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_agent_diagnostic import classify_logs, config_summary, diagnose, latest_agent_event, safe_local_identity, collect


class LocalAgentDiagnosticTests(unittest.TestCase):
    def test_only_allowlisted_configuration_escapes(self):
        sample = (
            "REPO=momopuke/judun-deploy\nBRANCH=main\n"
            "CHANNEL=channel/stable.json\n"
            "DEPLOY_TOKEN=DO_NOT_EXPORT\n"
            "PAYLOAD_DECRYPT_PRIVATE=TOP_SECRET\n"
            "BRANCH=$(malicious-command)\n"
        )
        result = config_summary(sample)
        self.assertEqual(result["REPO"], "momopuke/judun-deploy")
        self.assertEqual(result["BRANCH"], "main")
        self.assertEqual(result["CHANNEL"], "channel/stable.json")
        self.assertEqual(set(result), {"REPO", "BRANCH", "CHANNEL"})
        self.assertNotIn("TOP_SECRET", str(result))
        self.assertNotIn("DO_NOT_EXPORT", str(result))

    def test_only_log_category_counts_leave_process(self):
        raw = (
            "path=/private/customer-data; Base artifact mismatch\n"
            "secret=never print [ROLLBACK]\n"
            "User token: 123 [SUCCESS] Auto-deployed and verified\n"
        )
        stats = classify_logs(raw)
        self.assertEqual(stats["base_artifact_mismatch"], 1)
        self.assertEqual(stats["rollback"], 1)
        self.assertEqual(stats["success"], 1)
        self.assertNotIn("/private/", str(stats))
        self.assertNotIn("123", str(stats))

    def test_last_observed_success_supersedes_older_failure(self):
        raw = (
            "previous run: Encrypted payload SHA256 mismatch; token=never-export\n"
            "[SUCCESS] Auto-deployed and verified\n"
        )
        latest = latest_agent_event(raw)
        self.assertEqual(latest, "success")
        stats = classify_logs(raw)
        self.assertEqual(stats["encrypted_payload_sha_mismatch"], 1)
        self.assertEqual(stats["success"], 1)
        status = diagnose({
            "agent_installed": True, "timer_enabled": "enabled",
            "timer_active": "active", "agent_log_categories": stats,
            "agent_last_observed_event": latest,
        })
        self.assertEqual(status, "RECORDED_SUCCESS_BUT_LIVE_UNVERIFIED")
        self.assertNotIn("never-export", str(stats))
        self.assertNotIn("never-export", status)

    def test_last_observed_failure_supersedes_older_success(self):
        raw = (
            "[SUCCESS] Auto-deployed and verified\n"
            "another run: Encrypted payload SHA256 mismatch\n"
        )
        stats = classify_logs(raw)
        self.assertEqual(latest_agent_event(raw), "encrypted_payload_sha_mismatch")
        status = diagnose({
            "agent_installed": True, "timer_enabled": "enabled",
            "timer_active": "active", "agent_log_categories": stats,
            "agent_last_observed_event": latest_agent_event(raw),
        })
        self.assertEqual(status, "RECORDED_ENCRYPTED_PAYLOAD_SHA_MISMATCH")

    def test_success_is_not_a_proof_of_current_release(self):
        self.assertEqual(latest_agent_event("ordinary journal line"), "NONE")
        self.assertEqual(
            latest_agent_event("Release already processed: v1.2.114"),
            "release_already_processed",
        )
        info = {
            "agent_installed": True, "timer_enabled": "enabled",
            "timer_active": "active", "agent_log_categories": {"success": 1},
            "agent_last_observed_event": "release_already_processed",
        }
        self.assertEqual(
            diagnose(info), "RECORDED_ALREADY_PROCESSED_LIVE_UNVERIFIED"
        )

    def test_local_build_and_artifact_identity_must_agree(self):
        a = {"display_version": "v1.2.122", "artifact_id": "JUDUN-1.2.122-AABB"}
        self.assertEqual(safe_local_identity(a), a)
        for bad in (
            {"display_version": "1.2.122", "artifact_id": "JUDUN-1.2.121-AABB"},
            {"display_version": "1.2.122", "artifact_id": "JUDUN-1.2.122"},
            {"display_version": "1.2.122", "artifact_id": "x"},
            {"display_version": "1.2.122", "artifact_id": None},
            {"display_version": None, "artifact_id": "JUDUN-1.2.122-AABB"},
            {"display_version": "v1.2.122-rc1", "artifact_id": "JUDUN-1.2.122-AABB"},
            [],
            None,
        ):
            with self.subTest(bad=bad):
                self.assertIsNone(safe_local_identity(bad))

    def test_last_agent_event_comes_from_journal_tail_not_initial_bytes(self):
        from unittest.mock import patch, MagicMock
        import local_agent_diagnostic as diag
        massive_prefix = "Channel signature verification failed\n" + ("private-log-noise\n" * 10000)
        latest = "[SUCCESS] Auto-deployed and verified\n"
        fake = MagicMock(returncode=0, stdout=massive_prefix + latest)
        with (patch.object(diag, "CONFIG") as config,
              patch.object(diag, "run_status", return_value="active"),
              patch.object(diag.subprocess, "run", return_value=fake),
              patch.object(diag, "urlopen", side_effect=OSError("offline"))):
            config.is_file.return_value = False
            collected = collect()
        self.assertEqual(collected["agent_last_observed_event"], "success")
        self.assertEqual(collected["service_success_observed_in_sample"], True)
        self.assertEqual(collected["service_ever_successful"], "OBSERVED_IN_RECENT_SAMPLE")
        self.assertFalse(collected["pull_agent_required_for_https_v3"])

    def test_stop_states_precede_logs(self):
        sample = {
            "agent_installed": False, "timer_enabled": "enabled",
            "timer_active": "active", "agent_log_categories": {"base_artifact_mismatch": 2},
        }
        self.assertEqual(diagnose(sample), "AGENT_NOT_INSTALLED_OR_CONFIG_MISSING")
        sample["agent_installed"] = True
        sample["timer_active"] = "inactive"
        self.assertEqual(diagnose(sample), "AGENT_TIMER_NOT_ENABLED_OR_INACTIVE")
        sample["timer_active"] = "active"
        self.assertEqual(diagnose(sample), "RECORDED_BASE_ARTIFACT_MISMATCH")
        sample["agent_log_categories"] = {"signature_failure": 1}
        self.assertEqual(diagnose(sample), "SIGNED_CHANNEL_VERIFICATION_FAILED")
        sample["agent_log_categories"] = {}
        self.assertEqual(diagnose(sample), "AGENT_RUN_STATE_NOT_PROVEN_BY_STATIC_CHECKS")


if __name__ == "__main__":
    unittest.main()
