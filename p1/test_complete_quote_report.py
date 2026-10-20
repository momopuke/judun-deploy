"""Contract: full reports preserve EVERY original customer quote line."""
import unittest

from complete_quote_report import (
    ITEMS_PER_PAGE, render_authorized_quote_items,
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
        while True:
            result = render_authorized_quote_items(quotes, sources, offset=offset)
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
        self.assertIn("報價金額待人工確認",out["html"])
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

    def test_misaligned_arrays_fail_closed(self):
        for src in ([], [[],[]]):
            out=render_authorized_quote_items([quote(0)],src)
            self.assertEqual(out["status"],"INVALID_INPUT")
            self.assertEqual(out["html"],"")

    def test_no_total_is_fabricated_from_unit_amounts(self):
        out=render_authorized_quote_items([quote(0),quote(1)],[[],[]])
        self.assertNotIn("估價總金額",out["html"])
        self.assertNotIn("自動推估總價",out["html"])

    def test_empty_report_is_complete_but_contains_no_invented_items(self):
        out=render_authorized_quote_items([],[])
        self.assertEqual(out["status"],"COMPLETE")
        self.assertEqual(out["items_rendered"],0)
        self.assertEqual(out["html"].count('class="judun-quote-line"'),0)

if __name__=="__main__":
    unittest.main()
