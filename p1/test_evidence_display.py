"""Tests of safe report evidence tiers and trusted approved-source binding."""
import unittest

from evidence_display import (
    build_public_evidence_view,
    fingerprint_approval_source,
    render_public_evidence_html,
)
from test_evidence_gate import valid_case


def customer_quote(source=None):
    source = source or valid_case()
    keys = ("category", "item_name", "unit", "spec", "locality",
            "currency", "price_basis", "tax_included")
    return {**{k: source[k] for k in keys}, "amount": "NT$20,000"}


def approved_lookup(source):
    """Simulates a SERVER-SIDE approved evidence record, not a browser input."""
    approved_digest = fingerprint_approval_source(source)
    return lambda requested_digest: {
        "state": "approved",
        "fingerprint": approved_digest,
        "evidence_id": "evidence-18",
    } if requested_digest == approved_digest else None


class EvidencePresentationTests(unittest.TestCase):
    def test_unrelated_candidate_is_not_publicly_displayed(self):
        source = dict(valid_case(), title="醫療器材採購", body="診所醫療器材價格")
        view = build_public_evidence_view(
            source, customer_quote(), approved_record_lookup=approved_lookup(source))
        self.assertEqual(view["tier"], "EXCLUDED")
        self.assertIsNone(view["source_url"])
        self.assertIsNone(view["difference_twd"])
        self.assertEqual(render_public_evidence_html(view), "")

    def test_parser_fabricated_price_not_in_source_is_suppressed(self):
        source = dict(valid_case(), body="室內裝修工程施工說明；無公開價格。")
        self.assertFalse(build_public_evidence_view(source, customer_quote())["visible"])

    def test_public_source_without_customer_quote_is_reference_only(self):
        view = build_public_evidence_view(valid_case())
        self.assertTrue(view["visible"])
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertEqual(view["reference_amount_twd"], "18000")
        self.assertIsNone(view["difference_percent"])
        html = render_public_evidence_html(view)
        self.assertIn("NT$18,000", html)
        self.assertNotIn("約略估價", html)
        self.assertIn('target="_blank"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn("https://example.com.tw/renovation/quote-11", html)

    def test_matching_fields_alone_cannot_create_price_gap(self):
        view = build_public_evidence_view(valid_case(), customer_quote())
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIn("正式覆核", view["label"])
        self.assertIsNone(view["difference_twd"])

    def test_reject_all_untrusted_approval_results(self):
        source = valid_case()
        correct = fingerprint_approval_source(source)
        bad_results = [
            None, True, "approved", {},
            {"state": "approved", "fingerprint": correct},
            {"state": "pending", "fingerprint": correct, "evidence_id": "evidence-18"},
            {"state": "approved", "fingerprint": "0" * 64, "evidence_id": "evidence-18"},
            {"state": "approved", "fingerprint": correct, "evidence_id": " "},
            {"state": "approved", "fingerprint": correct, "evidence_id": "X" * 129},
        ]
        for result in bad_results:
            with self.subTest(result=result):
                view = build_public_evidence_view(
                    source, customer_quote(), approved_record_lookup=lambda _: result)
                self.assertEqual(view["tier"], "REFERENCE_ONLY")
                self.assertIsNone(view["difference_twd"])

    def test_registry_failure_fails_closed(self):
        def broken_lookup(_):
            raise RuntimeError("database unavailable")
        view = build_public_evidence_view(
            valid_case(), customer_quote(), approved_record_lookup=broken_lookup)
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIsNone(view["difference_twd"])

    def test_formally_approved_exact_pair_has_transparent_difference(self):
        source = valid_case()
        view = build_public_evidence_view(
            source, customer_quote(source), approved_record_lookup=approved_lookup(source))
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

    def test_negative_gap_is_labelled_lower_without_confusing_minus_currency(self):
        source = valid_case()
        quote = {**customer_quote(source), "amount": "NT$16,000"}
        view = build_public_evidence_view(
            source, quote, approved_record_lookup=approved_lookup(source))
        self.assertEqual(view["difference_twd"], "-2000")
        self.assertEqual(view["difference_percent"], "-11.1")
        html = render_public_evidence_html(view)
        self.assertIn("低於公開來源價格 NT$2,000", html)
        self.assertIn("11.1%", html)
        self.assertNotIn("NT$-2000", html)

    def test_equal_price_has_explicit_equal_label(self):
        source = valid_case()
        quote = {**customer_quote(source), "amount": "NT$18,000"}
        view = build_public_evidence_view(
            source, quote, approved_record_lookup=approved_lookup(source))
        self.assertEqual(view["difference_twd"], "0")
        html = render_public_evidence_html(view)
        self.assertIn("與公開來源價格相同", html)

    def test_renderer_rejects_tampered_difference_claim(self):
        source = valid_case()
        view = build_public_evidence_view(
            source, customer_quote(source),
            approved_record_lookup=approved_lookup(source))
        for modification in ({"difference_twd": "99000"},
                             {"difference_percent": "991.2"},
                             {"difference_twd": "NaN"},
                             {"difference_percent": "Infinity"}):
            with self.subTest(modification=modification):
                self.assertEqual(
                    render_public_evidence_html({**view, **modification}), "")

    def test_modified_source_cannot_reuse_approval(self):
        original = valid_case()
        approved = approved_lookup(original)
        tampered = {**original, "price_phase": "公開成交價格"}
        # Relevant and structurally matching, but NOT the same reviewed snapshot.
        view = build_public_evidence_view(
            tampered, customer_quote(tampered), approved_record_lookup=approved)
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIsNone(view["difference_twd"])

    def test_no_gap_when_spec_tax_basis_or_unit_mismatch(self):
        source = valid_case()
        for change in ({"spec": "其他工法"}, {"tax_included": False},
                       {"price_basis": "total_price"}, {"unit": "式"}):
            with self.subTest(change=change):
                quote = {**customer_quote(), **change}
                view = build_public_evidence_view(
                    source, quote, approved_record_lookup=approved_lookup(source))
                self.assertNotEqual(view["tier"], "COMPARABLE")
                self.assertIsNone(view["difference_twd"])

    def test_estimate_or_range_never_generates_exact_difference(self):
        source = dict(valid_case(), body="室內裝修油漆工程估價約 NT$18,000／坪")
        view = build_public_evidence_view(
            source, customer_quote(source), approved_record_lookup=approved_lookup(source))
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIsNone(view["difference_percent"])
        self.assertIsNone(view["reference_amount_twd"])
        html = render_public_evidence_html(view)
        self.assertNotIn("NT$18,000", html)
        self.assertIn("區間", html)
        self.assertIn('target="_blank"', html)

    def test_benchmark_reference_only_even_with_formal_approval(self):
        source = dict(valid_case(), evidence_type="ESTIMATOR_BENCHMARK")
        view = build_public_evidence_view(
            source, customer_quote(source), approved_record_lookup=approved_lookup(source))
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
        view = build_public_evidence_view(
            source, customer_quote(), approved_record_lookup=approved_lookup(source))
        self.assertFalse(view["visible"])
        self.assertEqual(render_public_evidence_html(view), "")

    def test_valid_redirect_links_to_final_public_source(self):
        source = dict(valid_case(), redirected=True,
                      resolved_url="https://public.example.org/quote/final",
                      redirect_chain_urls=[
                          valid_case()["url"],
                          "https://public.example.org/quote/final",
                      ], redirect_chain_verified=True)
        view = build_public_evidence_view(source, customer_quote(source))
        self.assertTrue(view["visible"])
        self.assertIn('href="https://public.example.org/quote/final"',
                      render_public_evidence_html(view))

    def test_empty_input_fails_closed(self):
        view = build_public_evidence_view({})
        self.assertFalse(view["visible"])
        self.assertEqual(render_public_evidence_html(view), "")

    def test_fingerprint_is_stable_and_sensitive_to_critical_fields(self):
        original = valid_case()
        fp = fingerprint_approval_source(original)
        self.assertEqual(fp, fingerprint_approval_source(dict(original)))
        self.assertEqual(len(fp), 64)
        for change in ({"amount": "NT$19,000"}, {"url": "https://other.example.org"},
                       {"body": "室內裝修油漆工程報價 NT$18,000"},
                       {"tax_included": False}, {"quantity": 50}):
            with self.subTest(change=change):
                self.assertNotEqual(fp, fingerprint_approval_source({**original, **change}))

    def test_overlarge_captured_page_fails_closed_before_rendering(self):
        for changes in (
            {"body": "裝修工程報價 NT$18,000／坪" + "X" * 62000},
            {"title": "台北室內裝修" + "A" * 1000},
            {"redirect_chain_urls": ["https://example.com.tw/a"] * 11},
        ):
            with self.subTest(changes=list(changes)):
                source = {**valid_case(), **changes}
                with self.assertRaises(ValueError):
                    fingerprint_approval_source(source)

    def test_extreme_decimal_ratio_never_crashes_or_reports_false_gap(self):
        source = dict(valid_case(),
                      amount="NT$0.000000000000000000000001",
                      body=("台北室內裝修油漆工程，批土兩道、乳膠漆三道，"
                            "公開報價 NT$0.000000000000000000000001／坪（含稅）。"))
        quote = {**customer_quote(source), "amount": "NT$10000000000"}
        result = build_public_evidence_view(
            source, quote, approved_record_lookup=approved_lookup(source))
        self.assertEqual(result["tier"], "REFERENCE_ONLY")
        self.assertIsNone(result["difference_percent"])
        self.assertIsNone(result["reference_amount_twd"])
        self.assertNotIn("NT$0.00", render_public_evidence_html(result))

    def test_decimal_prices_render_without_silent_cent_rounding(self):
        source = dict(valid_case(),
                      amount="NT$18,000.125",
                      body=("台北室內裝修油漆工程，批土兩道、乳膠漆三道，"
                            "公開報價 NT$18,000.125／坪（含稅）。"))
        quote = {**customer_quote(source), "amount": "NT$20,000.375"}
        result = build_public_evidence_view(
            source, quote, approved_record_lookup=approved_lookup(source))
        self.assertEqual(result["tier"], "COMPARABLE")
        html = render_public_evidence_html(result)
        self.assertIn("NT$18,000.125", html)
        self.assertIn("NT$20,000.375", html)
        self.assertIn("NT$2,000.25", html)

    def test_non_serializable_snapshot_has_no_approval(self):
        source = dict(valid_case(), quantity=object())
        view = build_public_evidence_view(
            source, customer_quote(source), approved_record_lookup=approved_lookup(valid_case()))
        self.assertNotEqual(view["tier"], "COMPARABLE")


if __name__ == "__main__":
    unittest.main()
