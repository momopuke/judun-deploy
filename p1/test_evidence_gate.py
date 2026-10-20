"""Regression tests for relevance, provenance, comparability and safe outbound links."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evidence_gate import evaluate, compare_with_target, parse_twd_amount, public_source_url, html_source_link

def valid_case():
    return {
        "url": "https://example.com.tw/renovation/quote-11",
        "title": "台北室內裝修油漆工程費用",
        "body": "公開工項與報價，提供房屋裝修規格。",
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

    def test_empty_and_malformed_url_rejected(self):
        for url in ("", None, "#evidence", "http://", "https://localhost", "ftp://example.org/quote"):
            with self.subTest(url=url):
                self.assertFalse(public_source_url(url))

    def test_foreign_currency_is_not_twd_price(self):
        self.assertEqual(evaluate(dict(valid_case(), currency="USD")).status, "HOLD")

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
        source = {**valid_case(), "price_basis":"total_price", "quantity":25}
        target = {k:source[k] for k in ("category", "item_name", "unit", "spec", "locality",
                                      "currency", "price_basis", "tax_included")}
        target["amount"] = "20000"
        for q in (None, 20, "NaN", 0, -1):
            with self.subTest(q=q):
                r = compare_with_target(source, {**target, "quantity":q})
                self.assertEqual(r.status,"REFERENCE_ONLY")
        self.assertEqual(compare_with_target(source,{**target, "quantity":"25.00"}).status,
                         "COMPARABLE")

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

    def test_invalid_record_rejected(self):
        self.assertEqual(evaluate(None).status, "REJECT")

if __name__ == "__main__":
    unittest.main()
