"""Compatibility adapter for archived JUDUN v1.2.82 page_candidate schema.

Reference only: model fields were verified against v1.2.82 October 4 package,
NOT against current v1.2.114 source. The adapter is never a live importer.

No candidate is granted completed-payment status or formal-price approval.
"""
from __future__ import annotations
import re
from decimal import Decimal
from evidence_gate import evaluate, GateDecision, parse_twd_amount

_EXPLICIT_PRICE_PHASE = (
    ("結算", "公開結算"),
    ("成交", "公開成交敘述（尚未驗證付款）"),
    ("報價", "公開報價"),
    ("估價", "公開估價"),
    ("單價", "公開單價"),
    ("行情", "公開行情"),
)
_FOREIGN = re.compile(r"\b(?:USD|HKD|JPY|RMB|CNY|EUR)\b|美金|美元|日圓|人民幣|港幣", re.I)


def phase_from_evidence(candidate: dict, raw_price_text: str) -> str:
    """Only use first-party captured source text as phase evidence."""
    declared = candidate.get("price_stage")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    text = str(candidate.get("title") or "") + " " + raw_price_text
    for signal, phase in _EXPLICIT_PRICE_PHASE:
        if signal in text:
            return phase
    return ""


def adapt_price_record(candidate: dict, draft: dict) -> dict:
    """Map one v1.2.82 draft record into conservative gate fields.

    Legacy parser's item label derived from raw_price_text is not a reviewed
    precise construction specification. Do not fabricate spec or unit.
    """
    if not isinstance(candidate, dict) or not isinstance(draft, dict):
        raise TypeError("candidate and draft must be mappings")
    raw = str(draft.get("raw_price_text") or "")
    explicit_foreign_currency = bool(_FOREIGN.search(raw))
    amount = draft.get("amount_twd")
    if amount is not None and not isinstance(amount, bool):
        try:
            n = Decimal(str(amount))
            amount_str = str(n) if n > 0 else ""
        except (ValueError, ArithmeticError):
            amount_str = ""
    else:
        amount_str = ""
    # The old parser did not distinguish a quoted range from a precise price.
    if draft.get("amount_low_twd") is not None or draft.get("amount_high_twd") is not None:
        amount_str = ""
    result = {
        "url": candidate.get("canonical_url") or candidate.get("url") or "",
        # Optional new collector fields; archived v1.2.82 did not record these.
        "redirected": candidate.get("redirected") is True,
        "resolved_url": candidate.get("resolved_url") or candidate.get("final_url") or "",
        "redirect_chain_verified": candidate.get("redirect_chain_verified") is True,
        "title": candidate.get("title") or "",
        "body": raw,
        "category": candidate.get("category") or "",
        "item_name": draft.get("verified_item_name") or "",
        "spec": draft.get("verified_specification") or "",
        "unit": draft.get("unit") or "",
        "locality": candidate.get("region") or "",
        "currency": "" if explicit_foreign_currency else ("TWD" if amount_str and raw else ""),
        "amount": amount_str,
        "price_phase": phase_from_evidence(candidate, raw),
        "evidence_type": candidate.get("evidence_type") or "",
    }
    return result


def audit_legacy_candidate(candidate: dict) -> dict:
    """Per-price-source QA decisions, without modifying original candidate.

    DO NOT use this wrapper alone as an auto-import permission gate.
    """
    if not isinstance(candidate, dict):
        raise TypeError("candidate must be mapping")
    validation = candidate.get("validation") or {}
    # Prior rule passed is necessary but not a substitute for this separate QA.
    older_qa_pass = isinstance(validation, dict) and validation.get("pass") is True
    records = candidate.get("draft_records") or []
    if not isinstance(records, list):
        records = []
    decisions = []
    for item in records:
        if not isinstance(item, dict):
            continue
        translated = adapt_price_record(candidate, item)
        verdict = evaluate(translated)
        if not older_qa_pass and verdict.status not in ("REJECT",):
            verdict = GateDecision("HOLD", ("LEGACY_PAGE_QA_NOT_PASSED",), False, False)
        decisions.append({
            "record_key": str(item.get("draft_record_id") or "")[:100],
            "status": verdict.status,
            "reasons": list(verdict.reasons),
            "eligible_for_formal_import": verdict.eligible_for_formal_import,
            "usable_for_exact_price_comparison": verdict.usable_for_exact_price_comparison,
            "transaction_confirmed": False,
        })
    return {
        "candidate_id": str(candidate.get("candidate_id") or "")[:90],
        "source_url": str(candidate.get("canonical_url") or candidate.get("url") or "")[:2048],
        "legacy_validation_passed": older_qa_pass,
        "records": decisions,
        "safe_to_auto_import": False,
        "requires_existing_qa_and_current_schema_check": True,
    }
