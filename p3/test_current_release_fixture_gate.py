"""Offline regressions for historical fixture routing; never contact production."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from current_release_fixture_gate import PINNED, assess
from patch_paid_preference import NEW, NEW_COMPLETION, OLD, OLD_COMPLETION


def build(version="1.2.122", *, artifact=None):
    return {"status": "OK", "data": {
        "version": version,
        "artifact_id": artifact if artifact is not None else f"JUDUN-{version}-TEST",
    }}


def page(body: bytes):
    return {"status": "OK", "content": body}


class LiveFixtureRoutingTests(unittest.TestCase):
    def test_exact_known_historical_release_can_run_legacy_regression(self):
        raw = b"synthetic v114 fixture"
        with patch.dict(PINNED, {"1.2.114": hashlib.sha256(raw).hexdigest()}):
            result = assess(build("1.2.114"), page(raw))
        self.assertEqual(result["decision"], "RUN")

    def test_known_release_html_drift_always_blocks(self):
        for version in ("1.2.120", "1.2.124"):
            result = assess(build(version), page(b"unreviewed changed live HTML"))
            self.assertEqual(result, {"decision": "BLOCK", "reason": "PINNED_RELEASE_SHA_DRIFT"})

    def test_current_release_pin_is_distinct_from_retained_historical_pin(self):
        self.assertNotEqual(PINNED["1.2.120"], PINNED["1.2.124"])

    def test_newer_site_with_existing_fixes_skips_obsolete_fixture_only(self):
        content = f"<script>\n{NEW}\n{NEW_COMPLETION}\n</script>".encode()
        result = assess(build(), page(content))
        self.assertEqual(result["decision"], "SKIP")
        self.assertEqual(result["live_version"], "1.2.122")
        self.assertEqual(result["reason"], "SUPERSEDED_PINNED_FIXTURE_WITH_GUARDS")

    def test_newer_site_without_both_exact_fixes_is_blocked(self):
        for content in (
            NEW.encode(), NEW_COMPLETION.encode(),
            f"{OLD}\n{NEW_COMPLETION}".encode(),
            f"{NEW}\n{OLD_COMPLETION}".encode(),
            f"{NEW}\n{NEW}\n{NEW_COMPLETION}".encode(),
        ):
            with self.subTest(content=content[:30]):
                self.assertEqual(
                    assess(build(), page(content))["reason"],
                    "NEWER_LIVE_GUARDS_NOT_PROVEN",
                )

    def test_unverified_network_does_not_convert_to_skip(self):
        self.assertEqual(
            assess({"status": "NOT_VERIFIED"}, page(b"fine"))["reason"],
            "LIVE_BUILD_UNVERIFIED",
        )
        self.assertEqual(
            assess(build(), {"status": "NOT_VERIFIED"})["reason"],
            "PUBLIC_HOMEPAGE_UNVERIFIED",
        )

    def test_version_and_artifact_identity_must_match(self):
        self.assertEqual(
            assess(build(artifact="JUDUN-1.2.120-OLD"), page(b""))["reason"],
            "ARTIFACT_VERSION_MISMATCH",
        )
        self.assertEqual(
            assess(build("1.2.119"), page(b""))["reason"],
            "UNKNOWN_OLDER_VERSION",
        )

    def test_no_private_or_customer_content_in_gate_output(self):
        token = "customer-sensitive-token"
        result = assess(build(), page((NEW + NEW_COMPLETION + token).encode()))
        self.assertEqual(result["decision"], "SKIP")
        self.assertNotIn(token, str(result))


if __name__ == "__main__":
    unittest.main()
