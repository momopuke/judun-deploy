"""Regression tests: rejected sources do not appear and QA gates price gaps."""
import unittest

from evidence_display import build_public_evidence_view, render_public_evidence_html
from test_evidence_gate import valid_case


def customer_quote(source=None):
    source = source or valid_case()
    keys = ("category", "item_name", "unit", "spec", "locality",
            "currency", "price_basis", "tax_included")
    return {**{k: source[k] for k in keys}, "amount": "NT$20,000"}


class EvidencePresentationTests(unittest.TestCase):
    def test_unrelated_candidate_is_not_publicly_displayed(self):
        source = dict(valid_case(), title="醫療器材採購", body="診所醫療器材價格")
        view = build_public_evidence_view(source, customer_quote(), formal_qa_approved=True,
                                          formal_evidence_id="formal-11")
        self.assertEqual(view["tier"], "EXCLUDED")
        self.assertIsNone(view["source_url"])
        self.assertIsNone(view["difference_twd"])
        self.assertEqual(render_public_evidence_html(view), "")

    def test_fabricated_price_not_found_on_source_is_suppressed(self):
        source = dict(valid_case(), body="室內裝修工程施工說明；無公開價格。")
        view = build_public_evidence_view(source, customer_quote())
        self.assertFalse(view["visible"])

    def test_valid_public_source_without_customer_quote_has_no_difference(self):
        view = build_public_evidence_view(valid_case())
        self.assertTrue(view["visible"])
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIsNone(view["difference_percent"])
        self.assertIsNone(view["reference_amount_twd"])
        html = render_public_evidence_html(view)
        self.assertNotIn("NT$18,000", html)
        self.assertIn("區間", html)
        self.assertIn('target="_blank"', html)
        html = render_public_evidence_html(view)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn("https://example.com.tw/renovation/quote-11", html)

    def test_matching_fields_alone_cannot_create_price_gap(self):
        view = build_public_evidence_view(valid_case(), customer_quote())
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIn("正式覆核", view["label"])
        self.assertIsNone(view["difference_twd"])

    def test_unidentified_formal_approval_must_not_upgrade(self):
        for approved, evidence_id in ((True, None), (True, ""), (True, "   "),
                                      ("true", "formal-1"), (1, "formal-1"),
                                      (True, "X" * 129)):
            with self.subTest(approved=approved, evidence_id=evidence_id):
                view = build_public_evidence_view(
                    valid_case(), customer_quote(),
                    formal_qa_approved=approved, formal_evidence_id=evidence_id)
                self.assertEqual(view["tier"], "REFERENCE_ONLY")
                self.assertIsNone(view["difference_twd"])

    def test_formally_approved_and_exact_pair_has_transparent_difference(self):
        view = build_public_evidence_view(
            valid_case(), customer_quote(), formal_qa_approved=True,
            formal_evidence_id="evidence-18")
        self.assertEqual(view["tier"], "COMPARABLE")
        self.assertEqual(view["reference_amount_twd"], "18000")
        self.assertEqual(view["customer_amount_twd"], "20000")
        self.assertEqual(view["difference_twd"], "2000")
        self.assertEqual(view["difference_percent"], "11.1")
        self.assertEqual(view["formal_evidence_id"], "evidence-18")
        self.assertFalse(view["transaction_confirmed"])
        self.assertIn("不等於實際成交價", view["explanation"])
        html = render_public_evidence_html(view)
        self.assertIn("NT$18,000", html)
        self.assertIn("NT$20,000", html)
        self.assertIn("11.1%", html)

    def test_no_gap_when_spec_tax_basis_or_quantity_mismatches(self):
        source = valid_case()
        for change in ({"spec": "其他工法"},
                       {"tax_included": False},
                       {"price_basis": "total_price"},
                       {"unit": "式"}):
            with self.subTest(change=change):
                quote = {**customer_quote(), **change}
                view = build_public_evidence_view(
                    source, quote, formal_qa_approved=True,
                    formal_evidence_id="evidence-18")
                self.assertNotEqual(view["tier"], "COMPARABLE")
                self.assertIsNone(view["difference_twd"])

    def test_estimate_or_range_never_generates_exact_difference(self):
        source = dict(valid_case(), body="室內裝修油漆工程估價約 NT$18,000／坪")
        view = build_public_evidence_view(
            source, customer_quote(source), formal_qa_approved=True,
            formal_evidence_id="evidence-18")
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIsNone(view["difference_percent"])

    def test_benchmark_is_reference_only_even_with_formal_approval(self):
        source = dict(valid_case(), evidence_type="ESTIMATOR_BENCHMARK")
        view = build_public_evidence_view(
            source, customer_quote(source), formal_qa_approved=True,
            formal_evidence_id="evidence-18")
        self.assertEqual(view["tier"], "REFERENCE_ONLY")

    def test_source_content_is_html_escaped(self):
        view = build_public_evidence_view(valid_case(), customer_quote())
        html = render_public_evidence_html(view, '<img src=x onerror=alert(1)>')
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertNotIn("onerror=alert(1)>", html)

    def test_bad_final_redirect_is_not_displayed(self):
        source = dict(valid_case(), redirected=True,
                      resolved_url="http://127.0.0.1:8000/private")
        view = build_public_evidence_view(source, customer_quote(),
                                          formal_qa_approved=True,
                                          formal_evidence_id="evidence-18")
        self.assertFalse(view["visible"])
        self.assertEqual(render_public_evidence_html(view), "")

    def test_valid_redirect_links_to_final_public_source(self):
        source = dict(valid_case(), redirected=True,
                      resolved_url="https://public.example.org/quote/final",
                      redirect_chain_urls=[
                          valid_case()["url"],
                          "https://public.example.org/quote/final"
                      ], redirect_chain_verified=True)
        view = build_public_evidence_view(source, customer_quote(source))
        self.assertTrue(view["visible"])
        html = render_public_evidence_html(view)
        self.assertIn('href="https://public.example.org/quote/final"', html)

    def test_empty_input_fails_closed(self):
        view = build_public_evidence_view({})
        self.assertFalse(view["visible"])
        self.assertEqual(render_public_evidence_html(view), "")


if __name__ == "__main__":
    unittest.main()
