"""Regression tests for relevance, provenance, comparability and safe outbound links."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_gate import evaluate, compare_with_target, parse_twd_amount, public_source_url, html_source_link, html_evidence_source_link

def valid_case():
    return {
        "url": "https://example.com.tw/renovation/quote-11",
        "title": "台北室內裝修油漆工程費用",
        "body": "台北室內裝修油漆工程，批土兩道、乳膠漆三道，公開報價 NT$18,000／坪。",
        "locality": "台北市",
        "currency": "TWD",
        "amount": "NT$18,000",
        "category": "油漆工程",
        "item_name": "牆面油漆",
        "unit": "坪",
        "spec": "批土兩道、乳膠漆三道",
        "price_phase": "公開報價",
        "evidence_type": "PRIMARY_CASE",
        "price_basis": "unit_price",
        "tax_included": True,
    }

class EvidenceGateTests(unittest.TestCase):
    def test_structured_case_not_comparable_until_pair_match(self):
        a = evaluate(valid_case())
        self.assertEqual(a.status, "READY_FOR_MATCHING")
        self.assertFalse(a.usable_for_exact_price_comparison)
        self.assertFalse(a.transaction_confirmed)

    def test_strict_matching_pair_is_structurally_comparable(self):
        s=valid_case()
        target={k:s[k] for k in ("category", "item_name", "unit", "spec", "locality", "currency", "price_basis", "tax_included")}
        target["amount"]="NT$20,000"
        r=compare_with_target(s,target)
        self.assertEqual(r.status,"COMPARABLE")
        self.assertTrue(r.usable_for_exact_price_comparison)
        self.assertFalse(r.transaction_confirmed)

    def test_different_specs_not_marked_comparable(self):
        s=valid_case()
        target={k:s[k] for k in ("category", "item_name", "unit", "spec", "locality", "currency", "price_basis", "tax_included")}
        target["amount"]="20000"
        for k,v in (("spec","乳膠漆一道"),("unit","式"),("locality","高雄市"),("item_name","牆面泥作"),("category","防水工程")):
            with self.subTest(key=k):
                self.assertEqual(compare_with_target(s,{**target,k:v}).status,"REFERENCE_ONLY")

    def test_missing_customer_price_not_comparable(self):
        s=valid_case()
        target={k:s[k] for k in ("category", "item_name", "unit", "spec", "locality", "currency", "price_basis", "tax_included")}
        self.assertEqual(compare_with_target(s,target).status,"HOLD")

    def test_unrelated_pharmaceutical_price_is_rejected(self):
        r = dict(valid_case(), title="醫療器材與藥品採購價格表", body="醫藥器材費用", category="", item_name="")
        self.assertEqual(evaluate(r).status, "REJECT")

    def test_unrelated_finance_price_rejected(self):
        r = dict(valid_case(), title="虛擬貨幣投資報酬率", body="", category="", item_name="")
        self.assertEqual(evaluate(r).status, "REJECT")

    def test_model_supplied_category_cannot_make_unrelated_page_relevant(self):
        candidate = dict(valid_case(), title="學校招生簡章與報名費",
                         body="本年度招生及報名公告，繳費請見表單",
                         category="油漆工程", item_name="牆面油漆")
        result = evaluate(candidate)
        self.assertEqual(result.status, "REJECT")
        self.assertEqual(result.reasons, ("SOURCE_TEXT_NOT_RENOVATION",))
        self.assertFalse(result.as_dict()["eligible_for_formal_qa"])

    def test_source_page_without_relevant_content_rejected_even_with_matching_specs(self):
        candidate = dict(valid_case(), title="2026 手機促銷單價",
                         body="優惠活動與價格列表",
                         category="室內裝修", item_name="牆面油漆")
        self.assertEqual(evaluate(candidate).status, "REJECT")

    def test_redirect_to_blocked_domain_rejected(self):
        x = dict(valid_case(), redirected=True,
                 resolved_url="https://www.twfuns.com/landing/123")
        self.assertEqual(evaluate(x).status, "REJECT")
        self.assertIn("REDIRECT_TO_BLOCKED_OR_NONPUBLIC_URL", evaluate(x).reasons)

    def test_redirect_to_internal_or_loopback_url_rejected(self):
        for target in ("http://127.0.0.1:8000/admin",
                       "http://192.168.0.1/private",
                       "javascript:alert(1)"):
            with self.subTest(target=target):
                x = dict(valid_case(), redirected=True, resolved_url=target)
                self.assertEqual(evaluate(x).status, "REJECT")

    def test_redirect_without_final_url_held(self):
        self.assertEqual(evaluate(dict(valid_case(), redirected=True)).status, "HOLD")

    def test_cross_domain_redirect_requires_chain_review(self):
        x = dict(valid_case(), redirected=True,
                 resolved_url="https://public-renovation.example.org/taiwan/prices")
        self.assertEqual(evaluate(x).status, "HOLD")
        y = dict(x, redirect_chain_verified=True,
                 redirect_chain_urls=[x["url"], x["resolved_url"]])
        self.assertEqual(evaluate(y).status, "READY_FOR_MATCHING")
        self.assertFalse(evaluate(y).eligible_for_formal_import)

    def test_direct_source_resolved_equals_original_requires_no_redirect_chain(self):
        original=valid_case()
        self.assertEqual(evaluate(dict(original,
            redirected=False, resolved_url=original["url"])).status, "READY_FOR_MATCHING")

    def test_changed_final_url_even_if_redirect_flag_absent_requires_chain(self):
        original=valid_case()
        x=dict(original, redirected=False, resolved_url="https://other.example.org/price")
        self.assertEqual(evaluate(x).status,"HOLD")

    def test_redirect_intermediate_hop_to_private_ip_is_rejected(self):
        origin=valid_case()
        final="https://example.com.tw/renovation/final"
        x=dict(origin, redirected=True, resolved_url=final,
               redirect_chain_verified=True,
               redirect_chain_urls=[origin["url"], "http://127.0.0.1:8000/admin", final])
        self.assertEqual(evaluate(x).status, "REJECT")

    def test_redirect_claimed_verified_without_chain_is_held(self):
        x=dict(valid_case(), redirected=True,
               resolved_url="https://example.com.tw/renovation/moved",
               redirect_chain_verified=True)
        self.assertEqual(evaluate(x).status, "HOLD")

    def test_redirect_chain_endpoint_mismatch_held(self):
        original=valid_case()
        x=dict(original, redirected=True,
               resolved_url="https://example.com.tw/renovation/moved",
               redirect_chain_verified=True,
               redirect_chain_urls=["https://other.example.org/start",
                                    "https://example.com.tw/renovation/moved"])
        self.assertEqual(evaluate(x).status, "HOLD")

    def test_redirect_chain_unreasonably_long_held(self):
        original=valid_case()
        final="https://example.com.tw/renovation/complete"
        chain=[original["url"]]+["https://example.com.tw/hop"+str(i) for i in range(12)]+[final]
        x=dict(original, redirected=True, resolved_url=final,
               redirect_chain_verified=True, redirect_chain_urls=chain)
        self.assertEqual(evaluate(x).status, "HOLD")

    def test_same_domain_redirect_can_remain_eligible_for_qa(self):
        x = dict(valid_case(), redirected=True,
                 resolved_url="https://example.com.tw/renovation/new-url")
        self.assertEqual(evaluate(x).status, "HOLD")
        y = dict(x, redirect_chain_verified=True,
                 redirect_chain_urls=[x["url"], x["resolved_url"]])
        self.assertEqual(evaluate(y).status, "READY_FOR_MATCHING")

    def test_mixed_medical_and_renovation_requires_review(self):
        r = dict(valid_case(), title="裝修工程與醫療器材共同採購")
        self.assertEqual(evaluate(r).status, "HOLD")

    def test_pure_ad_without_price_is_held(self):
        r = dict(valid_case(), title="油漆工程請私訊報價", amount=None)
        self.assertEqual(evaluate(r).status, "HOLD")

    def test_rejected_domain_has_no_reentry(self):
        r = dict(valid_case(), url="https://www.twfuns.com/post/123")
        self.assertEqual(evaluate(r).status, "REJECT")
        self.assertFalse(public_source_url("https://cdn.twfuns.net/aa"))

    def test_similar_but_distinct_hostname_not_overblocked(self):
        self.assertTrue(public_source_url("https://nottwfuns.example.org/quote"))

    def test_nonpublic_localhost_and_private_network_rejected(self):
        for url in ("http://localhost:8000/", "http://127.0.0.1/abc",
                    "http://192.168.1.1/item", "http://10.0.0.1/item",
                    "http://user:pass@example.com/a", "javascript:alert(1)", "/admin/data"):
            with self.subTest(url=url):
                self.assertFalse(public_source_url(url))

    def test_oversized_price_string_fails_before_matching(self):
        self.assertIsNone(parse_twd_amount("1" * 100000))
        x = dict(valid_case(), amount="1" * 100000)
        decision = evaluate(x)
        self.assertEqual(decision.status, "HOLD")
        self.assertIn("NO_VALID_EXPLICIT_PRICE", decision.reasons)

    def test_empty_and_malformed_url_rejected(self):
        for url in ("", None, "#evidence", "http://", "https://localhost", "ftp://example.org/quote"):
            with self.subTest(url=url):
                self.assertFalse(public_source_url(url))

    def test_foreign_currency_is_not_twd_price(self):
        self.assertEqual(evaluate(dict(valid_case(), currency="USD")).status, "HOLD")

    def test_parser_amount_without_price_in_source_is_held(self):
        source=dict(valid_case(), body="室內裝修工項說明、品牌與施工步驟。")
        decision=evaluate(source)
        self.assertEqual(decision.status, "HOLD")
        self.assertIn("PRICE_NOT_IN_CAPTURED_PUBLIC_SOURCE", decision.reasons)
        self.assertFalse(decision.eligible_for_formal_import)
        self.assertFalse(decision.usable_for_exact_price_comparison)

    def test_source_year_or_floor_area_not_counted_as_twd_price(self):
        for sample in ("室內裝修：2026 年，施工 18,000 坪。",
                       "室內裝修：2026 年度技術規範與產品型號 18000。",
                       "台北室內裝修：戶號 18000，工程內容詳情請見說明。"):
            with self.subTest(sample=sample):
                self.assertEqual(evaluate(dict(valid_case(),body=sample)).status, "HOLD")

    def test_source_amount_and_parser_amount_mismatch_is_held(self):
        src=dict(valid_case(),body="室內裝修油漆報價 NT$8,000 元／坪。",
                 amount="NT$18,000")
        verdict=evaluate(src)
        self.assertEqual(verdict.status,"HOLD")
        self.assertIn("PRICE_NOT_IN_CAPTURED_PUBLIC_SOURCE",verdict.reasons)

    def test_explicit_source_prices_with_wan_or_per_ping_accepted(self):
        cases=[
            ("室內裝修防水工程，報價1.5萬元。","15000"),
            ("室內裝修油漆工程，每坪 1500。","1500"),
            ("室內裝修油漆工程，單價：1,500 元。","1500"),
            ("室內裝修油漆工程，TWD 1,500。","1500"),
        ]
        for excerpt,amount in cases:
            with self.subTest(excerpt=excerpt):
                case=dict(valid_case(),body=excerpt,amount=amount)
                self.assertEqual(evaluate(case).status,"READY_FOR_MATCHING")

    def test_quoted_price_ranges_are_reference_only_not_exact(self):
        cases=[
            ("裝修油漆工程，單價：1,500～1,800 元／坪。","1500"),
            ("裝修油漆工程，單價：1,500～1,800 元／坪。","1800"),
            ("裝修油漆工程，價格 1,500-1,800 元。","1500"),
            ("裝修油漆工程，NT$1,500 起。","1500"),
            ("裝修油漆工程，報價約 1500 元。","1500"),
            ("裝修油漆工程，大約 NT$1,500。","1500"),
            ("裝修油漆工程，最低 NT$1,500。","1500"),
        ]
        for excerpt,amount in cases:
            with self.subTest(excerpt=excerpt,amount=amount):
                d=evaluate(dict(valid_case(),body=excerpt,amount=amount))
                self.assertEqual(d.status,"REFERENCE_ONLY",d)
                self.assertFalse(d.usable_for_exact_price_comparison)

    def test_year_after_price_label_is_not_a_quoted_price(self):
        case=dict(valid_case(), body="台北室內裝修，價格 2026 年度行情說明。", amount="2026")
        self.assertEqual(evaluate(case).status,"HOLD")

    def test_conflicting_exact_and_approximate_mentions_remain_reference(self):
        examples = (
            ("台北裝修油漆單價 NT$18,000／坪；另註明約 NT$18,000。", "台北裝修"),
            ("台北裝修油漆單價約 NT$18,000；明細另列 NT$18,000／坪。", "台北裝修"),
            ("台北裝修油漆單價起價 NT$18,000；報價 NT$18,000。", "台北裝修"),
        )
        for body, title in examples:
            with self.subTest(body=body):
                case = dict(valid_case(), title=title, body=body)
                decision = evaluate(case)
                self.assertEqual(decision.status, "REFERENCE_ONLY")
                self.assertIn("SOURCE_PRICE_RANGE_OR_ESTIMATE_NOT_EXACT", decision.reasons)

    def test_approximate_source_without_classification_is_not_publishable(self):
        case = dict(valid_case(), body="台北裝修油漆單價約 NT$18,000／坪")
        self.assertEqual(evaluate({**case, "evidence_type": ""}).status, "HOLD")
        self.assertEqual(evaluate({**case, "price_phase": ""}).status, "HOLD")

    def test_exact_explicit_quote_still_comparable_candidate(self):
        for excerpt,amount in [
            ("台北裝修油漆工程，單價：1,500 元／坪。","1500"),
            ("台北裝修油漆工程，NT$18,000／坪。","18000"),
            ("台北裝修工程，費用 1.5 萬元。","15000"),
        ]:
            with self.subTest(excerpt=excerpt):
                d=evaluate(dict(valid_case(),body=excerpt,amount=amount))
                self.assertEqual(d.status,"READY_FOR_MATCHING",d)

    def test_price_cannot_be_guessed_from_other_text(self):
        self.assertEqual(evaluate(dict(valid_case(), amount=None)).status, "HOLD")

    def test_missing_locality_requires_review(self):
        self.assertEqual(evaluate(dict(valid_case(), locality="")).status, "HOLD")

    def test_missing_phase_requires_review(self):
        self.assertEqual(evaluate(dict(valid_case(), price_phase="")).status, "HOLD")

    def test_undefined_evidence_class_is_not_admitted(self):
        self.assertEqual(evaluate(dict(valid_case(), evidence_type="UNKNOWN")).status, "HOLD")

    def test_missing_spec_reduced_to_reference(self):
        r = evaluate(dict(valid_case(), spec=""))
        self.assertEqual(r.status, "REFERENCE_ONLY")
        self.assertFalse(r.eligible_for_formal_import)
        self.assertTrue(r.as_dict()["eligible_for_formal_qa"])
        self.assertFalse(r.usable_for_exact_price_comparison)

    def test_benchmark_types_cannot_be_cases(self):
        for classification in ("PLATFORM_QUOTE_STATS", "ESTIMATOR_BENCHMARK",
                               "OFFICIAL_BENCHMARK", "EDITORIAL_REFERENCE"):
            with self.subTest(classification=classification):
                v = evaluate(dict(valid_case(), evidence_type=classification))
                self.assertEqual(v.status, "REFERENCE_ONLY")
                self.assertFalse(v.transaction_confirmed)

    def test_invalid_units_not_comparable(self):
        self.assertEqual(evaluate(dict(valid_case(), unit="公斤")).status, "REFERENCE_ONLY")

    def test_quoted_price_numbers_and_wan(self):
        self.assertEqual(parse_twd_amount("1.5萬"), 15000)
        self.assertEqual(parse_twd_amount("NT$18,000"), 18000)
        self.assertIsNone(parse_twd_amount("價格面議"))
        self.assertIsNone(parse_twd_amount("0"))
        self.assertIsNone(parse_twd_amount("-4"))

    def test_url_html_safe_new_tab(self):
        link=html_source_link("https://example.com.tw/?a=1&b=2", "公開<價格>")
        self.assertIn('target="_blank" rel="noopener noreferrer"', link)
        self.assertIn("&amp;b=2", link)
        self.assertIn("公開&lt;價格&gt;", link)
        with self.assertRaises(ValueError):
            html_source_link("javascript:alert(1)")


    def test_same_text_but_different_unit_or_total_basis_rejected(self):
        source = valid_case()
        target = {k:source[k] for k in ("category", "item_name", "unit", "spec", "locality",
                                      "currency", "price_basis", "tax_included")}
        target["amount"] = "20000"
        for source_basis, dest_basis in (("unit_price", "total_price"),
                                         ("total_price", "unit_price"),
                                         (None, "unit_price"), ("unit_price", None),
                                         ("other", "other")):
            with self.subTest(source_basis=source_basis, dest_basis=dest_basis):
                result = compare_with_target({**source, "price_basis":source_basis},
                                             {**target, "price_basis":dest_basis})
                self.assertEqual(result.status,"REFERENCE_ONLY")
                self.assertFalse(result.usable_for_exact_price_comparison)
                self.assertFalse(result.eligible_for_formal_import)

    def test_total_amount_requires_identical_quantity(self):
        source = {**valid_case(), "price_basis":"total_price", "quantity":25,
                  "body":"台北室內裝修油漆工程，整項總價 NT$18,000 元。"}
        target = {k:source[k] for k in ("category", "item_name", "unit", "spec", "locality",
                                      "currency", "price_basis", "tax_included")}
        target["amount"] = "20000"
        for q in (None, 20, "NaN", 0, -1):
            with self.subTest(q=q):
                r = compare_with_target(source, {**target, "quantity":q})
                self.assertEqual(r.status,"REFERENCE_ONLY")
        self.assertEqual(compare_with_target(source,{**target, "quantity":"25.00"}).status,
                         "COMPARABLE")

    def test_total_price_falsely_labeled_unit_price_is_not_comparable(self):
        source = {**valid_case(),
                  "body": "台北裝修油漆工程，整項總價 NT$18,000 元。",
                  "price_basis": "unit_price"}
        target = {key: source[key] for key in
                  ("category", "item_name", "unit", "spec", "locality",
                   "currency", "price_basis", "tax_included")}
        target["amount"] = "NT$20,000"
        decision = compare_with_target(source, target)
        self.assertEqual(decision.status, "REFERENCE_ONLY")
        self.assertIn("SOURCE_PRICE_UNIT_BASIS_NOT_PROVEN", decision.reasons)

    def test_unit_price_without_price_linked_unit_is_reference_only(self):
        source = {**valid_case(),
                  "body": "台北裝修油漆工程，價格 NT$18,000 元；施工面積 20 坪。"}
        target = {key: source[key] for key in
                  ("category", "item_name", "unit", "spec", "locality",
                   "currency", "price_basis", "tax_included")}
        target["amount"] = "NT$20,000"
        self.assertEqual(compare_with_target(source, target).status, "REFERENCE_ONLY")

    def test_explicit_same_occurrence_per_unit_price_is_comparable(self):
        source = {**valid_case(),
                  "body": "台北裝修油漆工程，每坪報價 NT$18,000。"}
        target = {key: source[key] for key in
                  ("category", "item_name", "unit", "spec", "locality",
                   "currency", "price_basis", "tax_included")}
        target["amount"] = "NT$20,000"
        self.assertEqual(compare_with_target(source, target).status, "COMPARABLE")

    def test_tax_inclusion_must_match_explicitly(self):
        source=valid_case()
        target={k:source[k] for k in ("category","item_name","unit","spec","locality",
                                      "currency","price_basis","tax_included")}
        target["amount"]="20000"
        for tax in (None, False, "true", 1):
            with self.subTest(tax=tax):
                self.assertEqual(compare_with_target(source,{**target,"tax_included":tax}).status,
                                 "REFERENCE_ONLY")

    def test_no_gate_decision_approves_formal_import_before_existing_qa(self):
        for record in (valid_case(), dict(valid_case(),spec=""),
                       dict(valid_case(),currency="USD"),
                       dict(valid_case(),title="完全無關",body="",category="",item_name="")):
            self.assertFalse(evaluate(record).eligible_for_formal_import)

    def test_numeric_loopback_aliases_cannot_be_used_as_sources(self):
        for address in ("http://127.1/private", "http://0177.0.0.1/private",
                        "http://0x7f.0x0.0.1/private",
                        "http://127-0-0-1.sslip.io/private",
                        "http://127.0.0.1.nip.io/private",
                        "http://backend.local/secret",
                        "http://registry.internal/secret",
                        "https://example.com:99999/path"):
            with self.subTest(address=address):
                self.assertFalse(public_source_url(address))
        # Do not block globally routable encoded service URLs by default.
        self.assertTrue(public_source_url("https://142-93-91-214.sslip.io/"))

    def test_audited_citation_uses_verified_landing_url(self):
        entry=valid_case()
        final="https://renovation.example.org/verified/quote"
        src=dict(entry, redirected=True, resolved_url=final,
                 redirect_chain_verified=True,
                 redirect_chain_urls=[entry["url"],final])
        actual=html_evidence_source_link(src)
        self.assertIn(final,actual)
        self.assertNotIn(entry["url"],actual)
        self.assertIn('target="_blank"',actual)
        with self.assertRaises(ValueError):
            html_evidence_source_link(dict(entry, redirected=True,
                      resolved_url="https://twfuns.com/excluded"))
        with self.assertRaises(ValueError):
            html_evidence_source_link(dict(entry, redirected=True,
                      resolved_url=final)) # missing verified chain

    def test_audited_citation_preserves_direct_source(self):
        entry=valid_case()
        self.assertIn(entry["url"],html_evidence_source_link(entry))

    def test_invalid_record_rejected(self):
        self.assertEqual(evaluate(None).status, "REJECT")

if __name__ == "__main__":
    unittest.main()
