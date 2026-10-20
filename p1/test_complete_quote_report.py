"""Contract: full reports preserve EVERY original customer quote line."""
import unittest

from complete_quote_report import (
    ITEMS_PER_PAGE, render_authorized_quote_items, render_complete_authorized_quote_report,
)
from test_evidence_gate import valid_case


def quote(index):
    s = valid_case()
    return {k: s[k] for k in ("category", "item_name", "unit", "spec", "locality",
                              "price_basis", "tax_included", "currency")} | {
        "amount": str(20000 + index)
    }


class CompleteQuoteReportTests(unittest.TestCase):
    def test_every_quote_line_survives_without_any_public_sources(self):
        quotes = [quote(i) for i in range(12)]
        out = render_authorized_quote_items(quotes, [[] for _ in quotes])
        self.assertTrue(out["complete"])
        self.assertEqual(out["items_rendered"], 12)
        self.assertEqual(out["html"].count('class="judun-quote-line"'), 12)
        self.assertIn("第 12 項", out["html"])
        self.assertIn("尚無可用公開來源", out["html"])

    def test_continuation_covers_all_67_items_without_silent_truncation(self):
        quotes = [quote(i) for i in range(67)]
        sources = [[] for _ in quotes]
        pages = []
        offset = 0
        snapshot = None
        src_snapshot = None
        alerts = []
        while True:
            result = render_authorized_quote_items(
                quotes, sources, offset=offset, expected_quote_digest=snapshot,
                expected_source_digest=src_snapshot, prior_source_alerts=alerts)
            snapshot = result["quote_digest"]
            src_snapshot = result["source_digest"]
            alerts = result["source_alerts"]
            pages.append(result)
            if result["next_offset"] is None:
                break
            self.assertEqual(result["status"], "MORE_ITEMS")
            self.assertFalse(result["complete"])
            offset = result["next_offset"]
        self.assertEqual([x["items_rendered"] for x in pages], [30,30,7])
        self.assertEqual(sum(x["items_rendered"] for x in pages),67)
        self.assertTrue(pages[-1]["complete"])
        self.assertIn("第 67 項", pages[-1]["html"])

    def test_invalid_row_is_preserved_with_warning_not_mislabeled(self):
        rows = [quote(0), None, {"item_name": "<img src=x>", "amount": "no price"}]
        out = render_authorized_quote_items(rows, [[], [], []])
        self.assertEqual(out["items_rendered"],3)
        self.assertIn("第 2 項：待核對原始資料",out["html"])
        self.assertIn("&lt;img",out["html"])
        self.assertNotIn("<img",out["html"])
        self.assertIn("原始金額：no price（幣別或金額待核對）",out["html"])
        self.assertFalse(out["complete"])
        self.assertEqual(out["source_alerts"],[1,2])

    def test_missing_source_list_does_not_erase_quote_line(self):
        out = render_authorized_quote_items([quote(0)], [None])
        self.assertIn("第 1 項",out["html"])
        self.assertIn("公開來源資料未就緒",out["html"])
        self.assertEqual(out["status"],"SOURCE_REVIEW_REQUIRED")
        self.assertFalse(out["complete"])

    def test_real_source_citation_is_attached_without_claiming_paid_price(self):
        out=render_authorized_quote_items([quote(0)], [[valid_case()]])
        self.assertEqual(out["status"],"COMPLETE")
        self.assertIn("公開來源與價差依據",out["html"])
        self.assertIn('target="_blank"',out["html"])
        self.assertNotIn("11.1%",out["html"])

    def test_more_than_1000_sources_are_all_rendered_across_continuations(self):
        rows=[{**valid_case(), "url":"https://example.com.tw/quote/"+str(i)}
              for i in range(1100)]
        out=render_authorized_quote_items([quote(0)],[rows])
        self.assertEqual(out["status"], "COMPLETE")
        self.assertTrue(out["complete"])
        self.assertEqual(out["source_alerts"], [])
        self.assertIn("/quote/1099", out["html"])
        self.assertEqual(out["html"].count('data-evidence-tier="REFERENCE_ONLY"'), 1100)
        self.assertNotIn("不能將此報告視為證據已完整呈現", out["html"])

    def test_more_than_supported_10000_sources_is_explicitly_incomplete(self):
        rows = [valid_case()] * 10001
        out = render_authorized_quote_items([quote(0)], [rows])
        self.assertEqual(out["status"], "SOURCE_REVIEW_REQUIRED")
        self.assertFalse(out["complete"])
        self.assertEqual(out["source_alerts"], [0])
        self.assertIn("不能將此報告視為證據已完整呈現", out["html"])

    def test_quote_items_changing_between_pages_are_not_combined(self):
        quotes = [quote(i) for i in range(31)]
        sources = [[] for _ in quotes]
        first = render_authorized_quote_items(quotes, sources)
        self.assertEqual(first["status"], "MORE_ITEMS")
        edited = list(quotes)
        edited[2] = {**quotes[2], "amount": "30000"}
        mismatch = render_authorized_quote_items(
            edited, sources, offset=first["next_offset"],
            expected_quote_digest=first["quote_digest"],
            expected_source_digest=first["source_digest"], prior_source_alerts=[])
        self.assertEqual(mismatch["status"], "QUOTE_SNAPSHOT_CHANGED")
        self.assertEqual(mismatch["html"], "")
        self.assertFalse(mismatch["complete"])

    def test_final_page_does_not_erase_prior_source_review_failure(self):
        quotes = [quote(i) for i in range(31)]
        sources = [[] for _ in quotes]
        sources[0] = None
        first = render_authorized_quote_items(quotes, sources)
        self.assertEqual(first["status"], "MORE_ITEMS")
        self.assertEqual(first["source_alerts"], [0])
        second = render_authorized_quote_items(
            quotes, sources, offset=first["next_offset"],
            expected_quote_digest=first["quote_digest"],
            expected_source_digest=first["source_digest"],
            prior_source_alerts=first["source_alerts"])
        self.assertEqual(second["status"], "SOURCE_REVIEW_REQUIRED")
        self.assertFalse(second["complete"])
        self.assertEqual(second["source_alerts"], [0])
        self.assertEqual(second["page_source_alerts"], [])
        self.assertIn("部分工項需補充來源", second["html"])

    def test_continuation_requires_verified_cumulative_review_state(self):
        quotes = [quote(i) for i in range(31)]
        sources = [[] for _ in quotes]
        first = render_authorized_quote_items(quotes, sources)
        without = render_authorized_quote_items(
            quotes, sources, offset=30,
            expected_quote_digest=first["quote_digest"],
            expected_source_digest=first["source_digest"])
        self.assertEqual(without["status"], "CONTINUATION_STATE_REQUIRED")
        self.assertFalse(without["complete"])
        for alerts in ([30], [-1], [0, 0], [True], ["0"]):
            with self.subTest(alerts=alerts):
                out = render_authorized_quote_items(
                    quotes, sources, offset=30,
                    expected_quote_digest=first["quote_digest"],
                    expected_source_digest=first["source_digest"],
                    prior_source_alerts=alerts)
                self.assertEqual(out["status"], "CONTINUATION_STATE_REQUIRED")

    def test_quote_continuation_requires_snapshot_identity(self):
        quotes = [quote(i) for i in range(31)]
        sources = [[] for _ in quotes]
        resumed = render_authorized_quote_items(
            quotes, sources, offset=30)
        self.assertEqual(resumed["status"], "QUOTE_SNAPSHOT_CHANGED")

    def test_source_association_changed_between_pages_does_not_cross_pair(self):
        quotes = [quote(i) for i in range(31)]
        records = [[] for _ in quotes]
        records[0] = [valid_case()]
        first = render_authorized_quote_items(quotes, records)
        changed = [list(items) for items in records]
        changed[0], changed[30] = changed[30], changed[0]
        second = render_authorized_quote_items(
            quotes, changed, offset=first["next_offset"],
            expected_quote_digest=first["quote_digest"],
            expected_source_digest=first["source_digest"],
            prior_source_alerts=first["source_alerts"])
        self.assertEqual(second["status"], "SOURCE_SNAPSHOT_CHANGED")
        self.assertFalse(second["complete"])
        self.assertEqual(second["html"], "")

    def test_extremely_large_source_map_keeps_original_quote_with_review(self):
        quotes = [quote(i) for i in range(31)]
        records = [[] for _ in quotes]
        records[0] = [valid_case()] * 20001
        result = render_complete_authorized_quote_report(quotes, records)
        self.assertEqual(result["status"], "SOURCE_REVIEW_REQUIRED")
        self.assertFalse(result["complete"])
        self.assertEqual(result["quote_items"], 31)
        self.assertEqual(result["html"].count('class="judun-quote-line"'), 31)
        self.assertNotIn("公開來源與價差依據", result["html"])
        self.assertEqual(result["source_alerts"], list(range(31)))

    def test_misaligned_evidence_arrays_preserve_original_quote_without_matching(self):
        for src in ([], [[], []]):
            out = render_authorized_quote_items([quote(0)], src)
            self.assertEqual(out["status"], "SOURCE_REVIEW_REQUIRED")
            self.assertIn("第 1 項：牆面油漆", out["html"])
            self.assertIn("公開來源資料未就緒", out["html"])
            self.assertEqual(out["source_alerts"], [0])
            self.assertNotIn("公開來源與價差依據", out["html"])

    def test_no_total_is_fabricated_from_unit_amounts(self):
        out=render_authorized_quote_items([quote(0),quote(1)],[[],[]])
        self.assertNotIn("估價總金額",out["html"])
        self.assertNotIn("自動推估總價",out["html"])

    def test_complete_report_orchestrator_preserves_all_lines_and_prior_review(self):
        quotes = [quote(i) for i in range(67)]
        rows = [[] for _ in quotes]
        rows[3] = None
        outcome = render_complete_authorized_quote_report(quotes, rows)
        self.assertEqual(outcome["status"], "SOURCE_REVIEW_REQUIRED")
        self.assertFalse(outcome["complete"])
        self.assertEqual(outcome["pages"], 3)
        self.assertEqual(outcome["quote_items"], 67)
        self.assertEqual(outcome["source_alerts"], [3])
        self.assertEqual(outcome["html"].count('class="judun-quote-line"'), 67)
        self.assertIn("第 67 項", outcome["html"])

    def test_complete_report_orchestrator_all_valid_pages(self):
        quotes = [quote(i) for i in range(67)]
        outcome = render_complete_authorized_quote_report(
            quotes, [[] for _ in quotes])
        self.assertEqual(outcome["status"], "COMPLETE")
        self.assertTrue(outcome["complete"])
        self.assertEqual(outcome["source_alerts"], [])
        self.assertEqual(outcome["quote_items"], 67)
        self.assertEqual(outcome["pages"], 3)

    def test_foreign_currency_is_preserved_not_relabelled_as_twd(self):
        foreign = {**quote(0), "amount": "25000", "currency": "USD"}
        result = render_authorized_quote_items([foreign], [[]])
        self.assertIn("原始金額：25000", result["html"])
        self.assertIn("幣別或金額待核對", result["html"])
        self.assertNotIn("NT$25,000", result["html"])

    def test_unknown_currency_and_malicious_original_amount_are_escaped(self):
        foreign = {**quote(0), "currency": "", "amount": "<img src=x>"}
        result = render_authorized_quote_items([foreign], [[]])
        self.assertIn("&lt;img", result["html"])
        self.assertNotIn("<img", result["html"])
        self.assertIn("幣別或金額待核對", result["html"])

    def test_partially_recognized_quote_line_must_never_be_marked_complete(self):
        row = {"category": "油漆工程", "item_name": "牆面油漆",
               "amount": "NT$15000", "currency": "TWD"}
        result = render_authorized_quote_items([row], [[]])
        self.assertEqual(result["status"], "SOURCE_REVIEW_REQUIRED")
        self.assertEqual(result["source_alerts"], [0])
        self.assertIn("第 1 項：牆面油漆", result["html"])

    def test_foreign_currency_requires_review_even_if_no_sources(self):
        row = {**quote(0), "currency": "USD"}
        result = render_authorized_quote_items([row], [[]])
        self.assertEqual(result["status"], "SOURCE_REVIEW_REQUIRED")
        self.assertEqual(result["source_alerts"], [0])
        self.assertIn("幣別或金額待核對", result["html"])

    def test_customer_precise_decimal_is_never_silently_rounded(self):
        row = {**quote(0), "amount": "NT$18000.125"}
        result = render_authorized_quote_items([row], [[]])
        self.assertEqual(result["status"], "COMPLETE")
        self.assertIn("NT$18,000.125", result["html"])

    def test_all_quote_items_can_be_rendered_without_claiming_price_evidence(self):
        quotes = [quote(0), quote(1)]
        report = render_complete_authorized_quote_report(quotes, [[], []])
        self.assertTrue(report["complete"])  # quote rows fully rendered
        self.assertEqual(report["source_coverage_status"], "NO_PUBLIC_SOURCES")
        self.assertEqual(report["quote_list_rendered"], 2)
        self.assertEqual(report["quote_items_without_sources"], 2)
        self.assertEqual(report["quote_items_with_source_candidates"], 0)
        self.assertFalse(report["source_price_verification_claimed"])
        self.assertIn("不代表價格已驗證", report["html"])

    def test_mixed_source_coverage_is_disclosed_independently(self):
        quotes = [quote(0), quote(1), quote(2)]
        report = render_complete_authorized_quote_report(
            quotes, [[valid_case()], [], []])
        self.assertTrue(report["complete"])
        self.assertEqual(report["source_coverage_status"], "PARTIAL_SOURCE_COVERAGE")
        self.assertEqual(report["quote_items_without_sources"], 2)
        self.assertEqual(report["quote_items_with_source_candidates"], 1)
        self.assertIn("部分工項尚無公開來源", report["html"])

    def test_source_rows_present_never_claim_all_prices_verified(self):
        report = render_complete_authorized_quote_report(
            [quote(0)], [[valid_case()]])
        self.assertEqual(report["source_coverage_status"], "SOURCE_CANDIDATES_PRESENT")
        self.assertFalse(report["source_price_verification_claimed"])
        self.assertIn("仍須查看原始證據與正式 QA", report["html"])

    def test_misaligned_source_coverage_is_not_silently_complete(self):
        report = render_complete_authorized_quote_report(
            [quote(0), quote(1)], [[]])
        self.assertEqual(report["source_coverage_status"], "SOURCE_MAPPING_INVALID")
        self.assertEqual(report["quote_items_without_sources"], 2)
        self.assertFalse(report["complete"])
        self.assertIn("全部來源配對暫停", report["html"])

    def test_whole_report_hashes_large_inputs_twice_not_once_per_page(self):
        from unittest.mock import patch
        import complete_quote_report as reports
        quotes = [quote(i) for i in range(95)]
        records = [[] for _ in quotes]
        orig_quotes = reports.quote_snapshot_digest
        orig_sources = reports.source_association_digest
        with (patch.object(reports, "quote_snapshot_digest",
                           wraps=orig_quotes) as quote_hash,
              patch.object(reports, "source_association_digest",
                           wraps=orig_sources) as source_hash):
            result = render_complete_authorized_quote_report(quotes, records)
        self.assertTrue(result["complete"])
        self.assertEqual(result["pages"], 4)
        self.assertEqual(quote_hash.call_count, 2)
        self.assertEqual(source_hash.call_count, 2)

    def test_report_discards_all_html_if_source_changes_during_render(self):
        from unittest.mock import patch
        import complete_quote_report as reports
        quotes = [quote(0)]
        sources = [[valid_case()]]
        original_render = reports.render_paged_public_price_sources

        def mutate_after_one_source_page(*args, **kwargs):
            result = original_render(*args, **kwargs)
            sources[0][0]["amount"] = "NT$19,000"
            return result

        with patch.object(reports, "render_paged_public_price_sources",
                          side_effect=mutate_after_one_source_page):
            report = render_complete_authorized_quote_report(quotes, sources)
        self.assertEqual(report["status"], "SOURCE_SNAPSHOT_CHANGED")
        self.assertFalse(report["complete"])
        self.assertEqual(report["html"], "")

    def test_empty_report_is_complete_but_contains_no_invented_items(self):
        out=render_authorized_quote_items([],[])
        self.assertEqual(out["status"],"COMPLETE")
        self.assertEqual(out["items_rendered"],0)
        self.assertEqual(out["html"].count('class="judun-quote-line"'),0)

if __name__=="__main__":
    unittest.main()
