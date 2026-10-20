"""Synthetic local agent diagnostic tests; never reach the VPS."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_agent_diagnostic import classify_logs, config_summary, diagnose


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
