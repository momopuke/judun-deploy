"""Release-channel comparison is read-only and never proves systemd state."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_readiness import assess_published_channel, assess_public_deep_integrity


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


def good_deep():
    return {
        "status": "OK",
        "data": {
            "status": "ok",
            "artifact_id": "JUDUN-1.2.122-C597F753F43B",
            "version": "1.2.122",
            "deep_verified": True,
            "files_verified": 81,
            "manifest_file_count": 81,
            "mismatch_count": 0,
            "formal_evidence_sha256": "a" * 64,
            "source_tree_sha256": "b" * 64,
        },
    }


class DeepIntegrityTests(unittest.TestCase):
    def check(self, payload, *, artifact="JUDUN-1.2.122-C597F753F43B",
              version="1.2.122"):
        return assess_public_deep_integrity(
            payload, live_artifact=artifact, live_version=version
        )

    def test_only_complete_deep_response_can_pass(self):
        self.assertEqual(self.check(good_deep()), "PASS")

    def test_public_success_without_deep_verified_is_not_pass(self):
        for status in (False, None, 0, "true"):
            with self.subTest(status=status):
                result = good_deep()
                result["data"]["deep_verified"] = status
                self.assertNotEqual(self.check(result), "PASS")

    def test_rejects_mismatched_version_or_artifact(self):
        payload = good_deep()
        self.assertEqual(
            self.check(payload, artifact="JUDUN-1.2.121-OLD"),
            "DEEP_IDENTITY_OR_VERIFICATION_MISMATCH",
        )
        self.assertEqual(
            self.check(payload, version="1.2.123"), "DEEP_VERSION_MISMATCH",
        )

    def test_rejects_incomplete_file_counts_and_mismatches(self):
        for key, value in (
            ("files_verified", 1),
            ("files_verified", True),
            ("manifest_file_count", None),
            ("manifest_file_count", 80),
            ("manifest_file_count", True),
            ("mismatch_count", 1),
            ("mismatch_count", False),
        ):
            with self.subTest(key=key, value=value):
                payload = good_deep()
                payload["data"][key] = value
                self.assertEqual(
                    self.check(payload), "DEEP_FILE_COUNT_OR_MISMATCH_INVALID"
                )

    def test_rejects_missing_or_malformed_sha(self):
        for name in ("formal_evidence_sha256", "source_tree_sha256"):
            for value in ("", None, "0" * 63, "g" * 64, 123):
                with self.subTest(name=name, value=value):
                    payload = good_deep()
                    payload["data"][name] = value
                    self.assertEqual(
                        self.check(payload), "DEEP_SHA256_MISSING_OR_INVALID"
                    )

    def test_rejects_missing_or_non_json_endpoint(self):
        for payload in ({"status": "NOT_VERIFIED"},
                        {"status": "OK", "data": None},
                        {"status": "OK", "data": []}):
            with self.subTest(payload=payload):
                self.assertEqual(self.check(payload), "DEEP_RESPONSE_UNVERIFIED")

    def test_public_pass_is_not_independent_hash_attestation(self):
        self.assertEqual(self.check(good_deep()), "PASS")
        # Integrity source is a public, self-reported endpoint: this module
        # deliberately does not fetch production files or verify a private
        # authoritative manifest. Full deployment acceptance is separate.



if __name__ == "__main__":
    unittest.main()
