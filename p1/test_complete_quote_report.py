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
        alerts = []
        while True:
            result = render_authorized_quote_items(
                quotes, sources, offset=offset, expected_quote_digest=snapshot,
                prior_source_alerts=alerts)
            snapshot = result["quote_digest"]
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
        self.assertEqual(out["source_alerts"],[1])

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

    def test_too_many_sources_are_not_silently_claimed_complete(self):
        rows=[{**valid_case(), "url":"https://example.com.tw/quote/"+str(i)}
              for i in range(1100)]
        out=render_authorized_quote_items([quote(0)],[rows])
        self.assertEqual(out["status"],"SOURCE_REVIEW_REQUIRED")
        self.assertFalse(out["complete"])
        self.assertEqual(out["source_alerts"],[0])
        self.assertIn("不能將此報告視為證據已完整呈現",out["html"])

    def test_quote_items_changing_between_pages_are_not_combined(self):
        quotes = [quote(i) for i in range(31)]
        sources = [[] for _ in quotes]
        first = render_authorized_quote_items(quotes, sources)
        self.assertEqual(first["status"], "MORE_ITEMS")
        edited = list(quotes)
        edited[2] = {**quotes[2], "amount": "30000"}
        mismatch = render_authorized_quote_items(
            edited, sources, offset=first["next_offset"],
            expected_quote_digest=first["quote_digest"], prior_source_alerts=[])
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
            expected_quote_digest=first["quote_digest"])
        self.assertEqual(without["status"], "CONTINUATION_STATE_REQUIRED")
        self.assertFalse(without["complete"])
        for alerts in ([30], [-1], [0, 0], [True], ["0"]):
            with self.subTest(alerts=alerts):
                out = render_authorized_quote_items(
                    quotes, sources, offset=30,
                    expected_quote_digest=first["quote_digest"],
                    prior_source_alerts=alerts)
                self.assertEqual(out["status"], "CONTINUATION_STATE_REQUIRED")

    def test_quote_continuation_requires_snapshot_identity(self):
        quotes = [quote(i) for i in range(31)]
        sources = [[] for _ in quotes]
        resumed = render_authorized_quote_items(
            quotes, sources, offset=30)
        self.assertEqual(resumed["status"], "QUOTE_SNAPSHOT_CHANGED")

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

    def test_empty_report_is_complete_but_contains_no_invented_items(self):
        out=render_authorized_quote_items([],[])
        self.assertEqual(out["status"],"COMPLETE")
        self.assertEqual(out["items_rendered"],0)
        self.assertEqual(out["html"].count('class="judun-quote-line"'),0)

if __name__=="__main__":
    unittest.main()
