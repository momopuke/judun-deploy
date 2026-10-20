"""End-to-end synthetic contract: source -> formal QA -> customer HTML."""
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evidence_display import fingerprint_approval_source
from formal_registry_adapter import REQUIRED_SCHEMA, ReadOnlyFormalApprovalRegistry
from report_evidence_section import render_report_public_price_sources
from test_evidence_gate import valid_case


def target():
    source = valid_case()
    keys = ("category", "item_name", "unit", "spec", "locality",
            "currency", "price_basis", "tax_included")
    return {**{name: source[name] for name in keys}, "amount": "NT$20,000"}


class ReportEvidenceSectionTests(unittest.TestCase):
    def test_without_authoritative_approval_public_price_is_only_reference(self):
        result = render_report_public_price_sources([valid_case()], target())
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["reference_only"], 1)
        self.assertEqual(result["comparable"], 0)
        self.assertNotIn("11.1%", result["html"])
        self.assertIn("不得將參考行情解讀", result["html"])

    def test_true_formal_registry_record_enables_end_to_end_price_evidence(self):
        source = valid_case()
        with TemporaryDirectory() as folder:
            path = Path(folder) / "formal.sqlite3"
            with sqlite3.connect(path) as db:
                db.executescript(REQUIRED_SCHEMA)
                db.execute(
                    "INSERT INTO judun_formal_evidence_approvals_v1 VALUES(?,?,?,?,?)",
                    (fingerprint_approval_source(source), "approved:18", "approved",
                     "2026-10-20T00:00:00+00:00", None)
                )
            registry = ReadOnlyFormalApprovalRegistry(path)
            result = render_report_public_price_sources(
                [source], target(), approved_record_lookup=registry)
            self.assertEqual(result["comparable"], 1)
            self.assertEqual(result["reference_only"], 0)
            self.assertEqual(result["displayed"], 1)
            self.assertIn("NT$20,000", result["html"])
            self.assertIn("11.1%", result["html"])
            self.assertIn('target="_blank"', result["html"])
            self.assertIn('rel="noopener noreferrer"', result["html"])

    def test_unrelated_and_fake_price_disappear_before_rendering(self):
        unrelated = {**valid_case(), "title": "醫療器材採購",
                     "body": "醫療器材單價 NT$18,000"}
        no_price = {**valid_case(), "body": "裝修步驟說明，沒有價格"}
        result = render_report_public_price_sources([unrelated, no_price], target())
        self.assertEqual(result["comparable"], 0)
        self.assertEqual(result["reference_only"], 0)
        self.assertEqual(result["excluded"], 2)
        self.assertNotIn("醫療器材", result["html"])

    def test_exact_duplicates_reduced_without_removing_distinct_cases_same_url(self):
        a = valid_case()
        b = dict(a, title="台北室內裝修油漆工程另一筆公開報價",
                 amount="NT$16,000", body="台北室內裝修油漆工程報價 NT$16,000／坪")
        result = render_report_public_price_sources([a, dict(a), b], target())
        self.assertEqual(result["reference_only"], 2)
        self.assertEqual(result["displayed"], 2)
        self.assertIn("NT$16,000", result["html"])

    def test_quote_specs_mismatch_never_produces_gap_even_with_fake_registry(self):
        source = valid_case()
        fake = lambda digest: {"state": "approved", "fingerprint": digest,
                               "evidence_id": "demo:1"}
        bad_quote = {**target(), "tax_included": False}
        result = render_report_public_price_sources(
            [source], bad_quote, approved_record_lookup=fake)
        self.assertEqual(result["comparable"], 0)
        self.assertNotIn("11.1%", result["html"])

    def test_html_escaping_and_direct_source(self):
        source = dict(valid_case(), item_name="<img src=x onerror=alert(1)>")
        result = render_report_public_price_sources([source], target())
        self.assertEqual(result["displayed"], 1)
        self.assertNotIn("<img", result["html"])
        self.assertIn("&lt;img", result["html"])
        self.assertIn('href="https://example.com.tw/renovation/quote-11"',
                      result["html"])

    def test_too_many_records_fails_closed_without_processing(self):
        result = render_report_public_price_sources([valid_case()] * 201, target())
        self.assertEqual(result["status"], "INVALID_INPUT")
        self.assertEqual(result["html"], "")

    def test_visible_list_is_bounded_and_total_is_disclosed(self):
        sources = []
        for n in range(23):
            sources.append({**valid_case(),
                            "url": "https://example.com.tw/renovation/" + str(n)})
        result = render_report_public_price_sources(sources, target())
        self.assertEqual(result["reference_only"], 23)
        self.assertEqual(result["displayed"], 20)
        self.assertTrue(result["truncated"])
        self.assertIn("本區僅顯示前 20 筆", result["html"])

    def test_invalid_rows_are_excluded_safely(self):
        result = render_report_public_price_sources(
            [valid_case(), None, "bad", {"quantity": object()}], target())
        self.assertEqual(result["reference_only"], 1)
        self.assertEqual(result["excluded"], 3)

    def test_invalid_input_does_not_render_personal_quote(self):
        for rows, quote in ((None, target()), ([], None), ("evil", target())):
            with self.subTest(rows=rows):
                result = render_report_public_price_sources(rows, quote)
                self.assertEqual(result["html"], "")
                self.assertEqual(result["status"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
