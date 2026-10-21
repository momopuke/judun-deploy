"""Verify exact two-statement P3 production-source patch is reversible.

These are SOURCE patch tests. The real public browser regression in CI covers
execution of both the unchanged and patched full v1.2.114 HTML.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import patch_paid_preference as source_patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_paid_preference import (
    OLD, NEW, OLD_COMPLETION, NEW_COMPLETION, apply_one_statement,
    write_staging_artifacts,
)


def sample() -> bytes:
    return ("<!doctype html><html><head><style>body{color:green}</style></head>"
            "<body><h1>用專業，守住家的每一個細節</h1><script>\n"
            "window.unlockTier = function(btn,jobId,tier){\n    " + OLD
            + "\n};\n"
            "window.checkMicroStatus = function(jobId) {\n    " + OLD_COMPLETION
            + "\n console.log(jobId); }\n};\n"
            "</script></body></html>").encode("utf-8")


class ExactPatch(unittest.TestCase):
    def test_current_review_is_noop_and_historical_fixture_is_independently_pinned(self):
        before = sample()
        after, _, _ = apply_one_statement(before)
        with patch.object(source_patch, 'OBSERVED_PUBLIC_HTML_SHA256', source_patch.sha(before)), patch.object(source_patch, 'CURRENT_PUBLIC_HTML_SHA256', source_patch.sha(after)):
            unchanged, report, diff = source_patch.review_public_source(after)
            self.assertEqual(unchanged, after)
            self.assertEqual(report['statement_replacements'], 0)
            self.assertEqual(diff, '')
            self.assertTrue(report['live_source_already_contains_fixes'])
            self.assertEqual(source_patch.historical_regression_source(after), before)

    def test_unknown_current_source_is_never_accepted_or_rewritten(self):
        for fn in (source_patch.review_public_source, source_patch.historical_regression_source):
            with self.assertRaisesRegex(ValueError, 'PUBLIC_VERSION_SHA_MISMATCH'):
                fn(sample())

    def test_current_identity_without_guard_still_fails(self):
        broken = sample()
        with patch.object(source_patch, 'CURRENT_PUBLIC_HTML_SHA256', source_patch.sha(broken)):
            with self.assertRaisesRegex(ValueError, 'DEPLOYED_FIX_SOURCE_GUARD_MISMATCH'):
                source_patch.review_public_source(broken)

    def test_historical_fixture_must_match_independent_old_sha(self):
        after, _, _ = apply_one_statement(sample())
        with patch.object(source_patch, 'CURRENT_PUBLIC_HTML_SHA256', source_patch.sha(after)):
            with self.assertRaisesRegex(ValueError, 'HISTORICAL_FIXTURE_SHA_MISMATCH'):
                source_patch.historical_regression_source(after)

    def test_rewrites_only_two_statements_and_keeps_brand(self):
        source = sample()
        patched, report, diff = apply_one_statement(source)
        expected = source.decode().replace(OLD, NEW, 1).replace(
            OLD_COMPLETION, NEW_COMPLETION, 1
        ).encode()
        self.assertEqual(patched, expected)
        self.assertIn(b"<style>body{color:green}</style>", patched)
        self.assertIn("用專業，守住家的每一個細節".encode(), patched)
        self.assertIn("-    " + OLD, diff)
        self.assertIn("+    " + NEW, diff)
        self.assertIn("-    " + OLD_COMPLETION, diff)
        self.assertIn("+    " + NEW_COMPLETION, diff)
        self.assertEqual(report["statement_replacements"], 2)
        self.assertTrue(report["completion_status_gate_hardened"])
        self.assertFalse(report["production_deployed"])
        self.assertFalse(report["actual_payment_e2e_passed"])

    def test_rejects_version_drift_and_duplicate_target(self):
        for payload in [
            sample().replace(OLD.encode(), b"const preferred = 'report-five-themes';"),
            sample() + OLD.encode(),
            sample() + OLD_COMPLETION.encode(),
            sample().replace(OLD_COMPLETION.encode(), b"if (data.done === true) {"),
            b"<script>window.unlockTier = function() {};</script>",
            sample().replace(b"window.unlockTier", b"window.notExpectedUnlock"),
        ]:
            with self.subTest(payload_size=len(payload)):
                with self.assertRaises(ValueError):
                    apply_one_statement(payload)

    def test_staging_exclusive_create_and_atomic_failure_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "before.html", root / "after.html"
            existing = root / "existing.html"
            existing.write_bytes(b"original-safe-data")
            with self.assertRaisesRegex(ValueError, "STAGING_PATH_ALREADY_EXISTS"):
                write_staging_artifacts([(first, b"new-before"), (existing, b"bad")])
            self.assertFalse(first.exists(), "failed staging left partial first file")
            self.assertEqual(existing.read_bytes(), b"original-safe-data")
            link = root / "dangling.html"
            link.symlink_to(root / "nonexistent.html")
            with self.assertRaises(ValueError):
                write_staging_artifacts([(link, b"must-not-follow")])
            self.assertTrue(link.is_symlink())
            self.assertFalse((root / "nonexistent.html").exists())
            write_staging_artifacts([(first, b"safe-before"), (second, b"safe-after")])
            self.assertEqual(first.read_bytes(), b"safe-before")
            self.assertEqual(second.read_bytes(), b"safe-after")
            with self.assertRaisesRegex(ValueError, "STAGING_PATH_ALREADY_EXISTS"):
                write_staging_artifacts([(first, b"refuse-overwrite")])
            self.assertEqual(first.read_bytes(), b"safe-before")

    def test_never_accepts_non_utf8_or_unbounded_source(self):
        for payload in [b"\xff" + sample(), sample() + b" " * 3_000_000]:
            with self.assertRaises(ValueError):
                apply_one_statement(payload)


if __name__ == "__main__":
    unittest.main()
