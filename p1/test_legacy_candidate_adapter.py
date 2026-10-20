"""Pinned-schema sample tests against archived v1.2.82 page_candidate structure."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from legacy_candidate_adapter import adapt_price_record, audit_legacy_candidate


def old_candidate():
    return {
        "candidate_id": "JDCAND-ABC123", "state": "candidate",
        "candidate_origin": "fresh", "source_id": "source-2",
        "source_status": "active", "domain": "example.com.tw",
        "url": "https://example.com.tw/quote?utm=123",
        "canonical_url": "https://example.com.tw/quote",
        "title": "台中油漆工程公開報價", "region": "台中市",
        "area": "25坪", "price_stage": None, "evidence_type": "PRIMARY_CASE",
        "validation": {"pass": True, "policy_version": "archive-v1282"},
        "raw_price_texts": ["室內裝修牆面油漆價格，每坪 NT$1,500"],
        "draft_records": [{
            "draft_record_id":"JDCAND-ABC123-P01",
            "raw_price_text":"室內裝修牆面油漆價格，每坪 NT$1,500",
            "amount_twd": 1500,
            "amount_low_twd": None,
            "amount_high_twd": None,
            "unit": "坪",
            "payment_verified": False,
            "approved_comparable": False,
        }],
        "flags": {"payment_verified": False, "approved_comparable": False,
                  "unknown_fields_not_inferred": True}
    }


class ArchivedCandidateAdapterTests(unittest.TestCase):
    def test_old_record_never_claims_exact_spec_or_auto_import(self):
        entry=old_candidate()
        mapped=adapt_price_record(entry,entry["draft_records"][0])
        self.assertEqual(mapped["url"],entry["canonical_url"])
        self.assertEqual(mapped["amount"],"1500")
        self.assertEqual(mapped["currency"],"TWD")
        self.assertEqual(mapped["spec"],"")
        self.assertEqual(mapped["price_phase"],"公開報價")
        audit=audit_legacy_candidate(entry)
        self.assertFalse(audit["safe_to_auto_import"])
        self.assertEqual(audit["records"][0]["status"],"REFERENCE_ONLY")
        self.assertFalse(audit["records"][0]["usable_for_exact_price_comparison"])
        self.assertFalse(audit["records"][0]["transaction_confirmed"])

    def test_missing_page_context_blocks_source(self):
        entry=old_candidate()
        entry["title"]="最新手機價格列表"
        entry["draft_records"][0]["raw_price_text"]="蘋果手機優惠每台 1500 元"
        self.assertEqual(audit_legacy_candidate(entry)["records"][0]["status"],"REJECT")

    def test_domain_blocked_independent_of_old_pass(self):
        entry=old_candidate()
        entry["canonical_url"]="https://www.twfuns.com/offer/21"
        self.assertEqual(audit_legacy_candidate(entry)["records"][0]["status"],"REJECT")

    def test_prior_page_qa_failure_must_hold(self):
        entry=old_candidate()
        entry["validation"]["pass"]=False
        d=audit_legacy_candidate(entry)["records"][0]
        self.assertEqual(d["status"],"HOLD")
        self.assertEqual(d["reasons"],["LEGACY_PAGE_QA_NOT_PASSED"])

    def test_foreign_currency_marker_fails_twd(self):
        entry=old_candidate()
        entry["draft_records"][0]["raw_price_text"]="裝修油漆 USD 1500 報價"
        result=audit_legacy_candidate(entry)["records"][0]
        self.assertEqual(result["status"],"HOLD")

    def test_price_range_must_not_be_exact(self):
        entry=old_candidate()
        entry["draft_records"][0].update({"amount_twd":None,"amount_low_twd":1500,
                                          "amount_high_twd":4000})
        data=adapt_price_record(entry,entry["draft_records"][0])
        self.assertEqual(data["amount"],"")
        self.assertEqual(audit_legacy_candidate(entry)["records"][0]["status"],"HOLD")

    def test_legacy_unverified_fields_stay_unverified_even_if_extra_values(self):
        entry=old_candidate()
        entry["draft_records"][0].update({"verified_item_name":"油漆工程",
                                          "verified_specification":"兩道底漆、三道面漆"})
        audit=audit_legacy_candidate(entry)
        self.assertEqual(audit["records"][0]["status"],"READY_FOR_MATCHING")
        self.assertFalse(audit["records"][0]["usable_for_exact_price_comparison"])
        self.assertFalse(audit["safe_to_auto_import"])

    def test_legacy_adapter_carries_blocked_final_url_to_gate(self):
        entry=old_candidate()
        entry["redirected"]=True
        entry["final_url"]="https://twfuns.com/hidden"
        self.assertEqual(audit_legacy_candidate(entry)["records"][0]["status"],"REJECT")

    def test_legacy_adapter_holds_unverified_external_redirect(self):
        entry=old_candidate()
        entry["redirected"]=True
        entry["final_url"]="https://other-public.example.org/renovation/price"
        self.assertEqual(audit_legacy_candidate(entry)["records"][0]["status"],"HOLD")
        entry["redirect_chain_verified"]=True
        self.assertEqual(audit_legacy_candidate(entry)["records"][0]["status"],"REFERENCE_ONLY")

    def test_legacy_adapter_requires_known_redirect_target(self):
        entry=old_candidate()
        entry["redirected"]=True
        self.assertEqual(audit_legacy_candidate(entry)["records"][0]["status"],"HOLD")

    def test_no_parsed_records_never_auto_imports(self):
        entry=old_candidate()
        entry["draft_records"]=[]
        audit=audit_legacy_candidate(entry)
        self.assertEqual(audit["records"],[])
        self.assertFalse(audit["safe_to_auto_import"])

    def test_no_region_does_not_infer_from_title(self):
        entry=old_candidate()
        entry["region"]=None
        audit=audit_legacy_candidate(entry)
        self.assertEqual(audit["records"][0]["status"],"HOLD")
        self.assertIn("TAIWAN_LOCALITY_UNVERIFIED",audit["records"][0]["reasons"])

if __name__=="__main__":
    unittest.main()
