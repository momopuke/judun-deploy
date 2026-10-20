"""Release-channel comparison is read-only and never proves systemd state."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_readiness import assess_published_channel


class SignedChannelBaselineTests(unittest.TestCase):
    def test_stale_channel_reports_mismatch_without_agent_claim(self):
        old = {
            "base_artifact_id": "JUDUN-1.2.106-533633BE72D7",
            "target_artifact_id": "JUDUN-1.2.106-EFAFFF20D305",
        }
        self.assertEqual(
            assess_published_channel(old, "JUDUN-1.2.114-AA38F0567A4D"),
            "BASE_MISMATCH_IF_AGENT_ACTIVE",
        )
        self.assertEqual(
            assess_published_channel(old, "JUDUN-1.2.106-533633BE72D7"),
            "BASE_MATCH_IF_AGENT_ACTIVE",
        )
        self.assertEqual(
            assess_published_channel(old, "JUDUN-1.2.106-EFAFFF20D305"),
            "TARGET_ALREADY_LIVE_IF_AGENT_ACTIVE",
        )
        self.assertEqual(
            assess_published_channel(old, None), "LIVE_IDENTITY_NOT_VERIFIED",
        )


if __name__ == "__main__":
    unittest.main()
