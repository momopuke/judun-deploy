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
        customer = {**target(), "item_name": source["item_name"]}
        result = render_report_public_price_sources([source], customer)
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


    def test_unrelated_same_category_but_different_item_hidden(self):
        source = dict(valid_case(), item_name="牆面油漆")
        source2 = dict(valid_case(), item_name="天花板油漆",
                       url="https://example.com.tw/taiwan/ceiling",
                       title="台灣室內裝修天花板油漆工程報價",
                       body="天花板油漆工程價格 NT$18,000／坪")
        result = render_report_public_price_sources([source, source2], target())
        self.assertEqual(result["reference_only"], 1)
        self.assertEqual(result["excluded"], 1)
        self.assertNotIn("天花板油漆", result["html"])

    def test_unrelated_category_hidden_even_if_page_contains_renovation(self):
        candidate = {**valid_case(), "category": "水電工程",
                     "url": "https://example.com.tw/taiwan/water",
                     "title": "室內裝修水電工程公開報價"}
        result = render_report_public_price_sources([candidate], target())
        self.assertEqual(result["reference_only"], 0)
        self.assertEqual(result["excluded"], 1)

    def test_renovation_item_match_normalizes_spaces_and_typography(self):
        source = dict(valid_case(), item_name="牆面　油漆", category="油漆工程")
        result = render_report_public_price_sources([source], target())
        self.assertEqual(result["reference_only"], 1)

    def test_reference_only_sources_are_collapsed_with_native_details(self):
        result = render_report_public_price_sources([valid_case()], target())
        html = result["html"]
        self.assertIn('<details class="judun-related-price-sources">', html)
        self.assertIn("<summary>展開相關公開參考來源（1 筆）</summary>", html)
        self.assertEqual(result["comparable"], 0)
        self.assertEqual(result["reference_only"], 1)
        self.assertNotIn("<details open", html)

    def test_report_section_has_no_duplicate_heading_id(self):
        a = render_report_public_price_sources([valid_case()], target())
        b = render_report_public_price_sources([valid_case()], target())
        both = a["html"] + b["html"]
        self.assertNotIn('id="judun-public-price-sources-heading"', both)
        self.assertEqual(both.count('aria-label="公開來源與價差依據"'), 2)

    def test_full_mode_preserves_all_qualified_sources(self):
        sources = [{**valid_case(),
                    "url": "https://example.com.tw/renovation/quote-" + str(n)}
                   for n in range(29)]
        compact = render_report_public_price_sources(sources, target())
        full = render_report_public_price_sources(sources, target(), view_mode="full")
        self.assertEqual(compact["displayed"], 20)
        self.assertTrue(compact["truncated"])
        self.assertEqual(full["reference_only"], 29)
        self.assertEqual(full["displayed"], 29)
        self.assertFalse(full["truncated"])
        self.assertIn("quote-28", full["html"])
        self.assertIn('<details class="judun-related-price-sources" open>', full["html"])
        self.assertNotIn('<details class="judun-related-price-sources" open>', compact["html"])

    def test_exclusion_audit_is_aggregated_and_has_no_personal_content(self):
        unrelated = {**valid_case(), "category": "其他工程"}
        wrong_item = {**valid_case(), "item_name": "不同工項"}
        no_price = {**valid_case(), "body": "台灣室內裝修說明，未公開報價"}
        malformed = {"category": "油漆工程", "item_name": "牆面油漆",
                     "quantity": object()}
        result = render_report_public_price_sources(
            [valid_case(), unrelated, wrong_item, no_price, malformed, None], target())
        self.assertEqual(result["excluded"], 5)
        self.assertEqual(result["excluded_breakdown"], {
            "CATEGORY_MISMATCH": 1,
            "INVALID_ROW": 1,
            "ITEM_MISMATCH": 1,
            "SOURCE_REJECTED_OR_UNVERIFIED": 1,
            "UNREADABLE_EVIDENCE": 1,
        })
        self.assertNotIn("台灣室內裝修說明", str(result["excluded_breakdown"]))
        self.assertEqual(result["reference_only"], 1)

    def test_missing_scope_and_unknown_mode_fail_closed(self):
        for item, kwargs in (({**target(), "item_name": ""}, {}),
                             ({**target(), "category": ""}, {}),
                             (target(), {"view_mode": "unknown"})):
            with self.subTest(item=item, kwargs=kwargs):
                result = render_report_public_price_sources(
                    [valid_case()], item, **kwargs)
                self.assertEqual(result["status"], "INVALID_INPUT")
                self.assertEqual(result["html"], "")

    def test_verified_sources_first_under_compact_limit(self):
        comparable = valid_case()
        refs = [{**valid_case(), "url": "https://example.com.tw/reference/" + str(n)}
                for n in range(22)]
        verified_sha = fingerprint_approval_source(comparable)
        def lookup(sha):
            return ({"state": "approved", "fingerprint": verified_sha,
                     "evidence_id": "evidence-verified"}
                    if sha == verified_sha else None)
        result = render_report_public_price_sources(
            refs + [comparable], target(), approved_record_lookup=lookup)
        self.assertEqual(result["comparable"], 1)
        self.assertEqual(result["reference_only"], 22)
        self.assertEqual(result["displayed"], 20)
        self.assertIn("11.1%", result["html"])
        self.assertTrue(result["truncated"])

    def test_invalid_input_does_not_render_personal_quote(self):
        for rows, quote in ((None, target()), ([], None), ("evil", target())):
            with self.subTest(rows=rows):
                result = render_report_public_price_sources(rows, quote)
                self.assertEqual(result["html"], "")
                self.assertEqual(result["status"], "INVALID_INPUT")


if __name__ == "__main__":
    unittest.main()
