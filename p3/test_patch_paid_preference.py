"""Verify exact two-statement P3 production-source patch is reversible.

These are SOURCE patch tests. The real public browser regression in CI covers
execution of both the unchanged and patched full v1.2.114 HTML.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_paid_preference import (
    OLD, NEW, OLD_COMPLETION, NEW_COMPLETION, apply_one_statement,
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

    def test_never_accepts_non_utf8_or_unbounded_source(self):
        for payload in [b"\xff" + sample(), sample() + b" " * 3_000_000]:
            with self.assertRaises(ValueError):
                apply_one_statement(payload)


if __name__ == "__main__":
    unittest.main()
