"""Verify source patch touches exactly one ProMax preferred destination."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_paid_preference import OLD, NEW, apply_one_statement


def sample() -> bytes:
    return ("<!doctype html><html><head><style>body{color:green}</style></head>"
            "<body><h1>用專業，守住家的每一個細節</h1><script>\n"
            "window.unlockTier = function(btn,jobId,tier){\n    " + OLD +
            "\n};\n</script></body></html>").encode("utf-8")


class ExactPatch(unittest.TestCase):
    def test_rewrites_only_one_statement_and_keeps_brand(self):
        source = sample()
        patched, report, diff = apply_one_statement(source)
        self.assertEqual(patched, source.replace(OLD.encode(), NEW.encode()))
        self.assertIn(b"<style>body{color:green}</style>", patched)
        self.assertIn("用專業，守住家的每一個細節".encode(), patched)
        self.assertIn("-    " + OLD, diff)
        self.assertIn("+    " + NEW, diff)
        self.assertFalse(report["production_deployed"])
        self.assertFalse(report["actual_payment_e2e_passed"])

    def test_rejects_version_drift_and_duplicate_match(self):
        for payload in [
            sample().replace(OLD.encode(), b"const preferred = 'report-five-themes';"),
            sample() + OLD.encode(),
            b"<script>window.unlockTier = function() {};</script>",
            sample().replace(b"window.unlockTier", b"window.notExpectedUnlock"),
        ]:
            with self.assertRaises(ValueError):
                apply_one_statement(payload)

    def test_never_accepts_non_utf8_or_unbounded_source(self):
        for payload in [b"\xff" + sample(), sample() + b" " * 3_000_000]:
            with self.assertRaises(ValueError):
                apply_one_statement(payload)


if __name__ == "__main__":
    unittest.main()
