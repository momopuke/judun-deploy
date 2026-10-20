"""Conservative PUBLIC report presentation for vetted renovation price evidence.

INTEGRATION CANDIDATE ONLY. The live report is not modified by this file.
Production MUST resolve formal_qa_approved/formal_evidence_id from its trusted
server-side accepted evidence registry; never from a browser request.

The strict pairing gate alone never confers formal evidence acceptance and
neither this module nor its rendered HTML triggers data import, payment or
publication. Source contents and URLs remain untrusted.
"""
from __future__ import annotations

from decimal import Decimal
from html import escape
import hashlib
import json

from evidence_gate import (
    evaluate,
    compare_with_target,
    html_evidence_source_link,
    parse_twd_amount,
)

def _hidden(reason: str) -> dict:
    return {
        "visible": False,
        "tier": "EXCLUDED",
        "label": "不顯示",
        "explanation": reason,
        "source_url": None,
        "reference_amount_twd": None,
        "customer_amount_twd": None,
        "difference_twd": None,
        "difference_percent": None,
        "difference_basis": None,
        "transaction_confirmed": False,
        "formal_evidence_id": None,
    }


def _money(value: Decimal) -> str:
    # Render exact decimal without floating point or implicit rounding.
    return format(value, "f")


# Hash all captured fields used by relevance, routing, pair-match and price display.
# The formal registry must store this snapshot digest AT the time of QA approval.
_APPROVED_SOURCE_KEYS = (
    "url", "resolved_url", "redirected", "redirect_chain_urls",
    "redirect_chain_verified", "title", "body", "locality", "region",
    "currency", "amount", "category", "item_name", "unit", "spec",
    "price_phase", "evidence_type", "price_basis", "tax_included", "quantity",
)


def fingerprint_approval_source(source: dict) -> str:
    """Canonical digest for a formally reviewed PUBLIC SOURCE snapshot.

    No trust is created by this digest: only the server-side approved registry
    can grant status. Compare the complete critical snapshot, not just a URL or
    user-supplied price, to prevent stale approvals being reused after changes.
    """
    if not isinstance(source, dict):
        raise ValueError("source must be a mapping")
    snapshot = {key: source.get(key) for key in _APPROVED_SOURCE_KEYS}
    try:
        raw = json.dumps(snapshot, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("source contains unsupported review fields") from exc
    return hashlib.sha256(raw).hexdigest()


def _find_approved_id(source: dict, approved_record_lookup) -> str | None:
    """Fail closed unless a trusted backend registry confirms the same snapshot.

    approved_record_lookup must be a *server-defined* callable accepting a
    snapshot SHA-256 and returning {state, fingerprint, evidence_id}. NEVER
    accept this callable, its output, or approval flags from a browser request.
    """
    if not callable(approved_record_lookup):
        return None
    try:
        digest = fingerprint_approval_source(source)
        record = approved_record_lookup(digest)
    except Exception:  # A registry failure must never grant price comparison.
        return None
    if not isinstance(record, dict):
        return None
    record_id = record.get("evidence_id")
    if (record.get("state") != "approved"
            or record.get("fingerprint") != digest
            or not isinstance(record_id, str)
            or not 0 < len(record_id.strip()) <= 128):
        return None
    return record_id.strip()


def build_public_evidence_view(
    source: dict,
    customer_quote: dict | None = None,
    *,
    approved_record_lookup=None,
) -> dict:
    """Return safe display data; comparisons require BOTH strict match and formal QA.

    A verified price gap requires the trusted server's registry to return an
    approved record bound to the EXACT snapshot fingerprint. Booleans and
    evidence IDs from forms/query parameters are NOT proof of approval.
    """
    gate = evaluate(source)
    if gate.status in ("REJECT", "HOLD"):
        return _hidden("來源不相關或證據不足，不列入公開報告或價差計算")

    # Re-evaluate the whole redirect chain before publishing its landing URL.
    # Any unexpected source URL failure fails closed.
    try:
        html_evidence_source_link(source)
    except (TypeError, ValueError):
        return _hidden("公開來源連結未通過檢查")
    url = source.get("resolved_url") or source.get("url")
    source_amount = parse_twd_amount(source.get("amount"))
    if source_amount is None:
        return _hidden("來源價格尚未驗證")

    view = {
        "visible": True,
        "tier": "REFERENCE_ONLY",
        "label": "公開行情參考",
        "explanation": "公開來源提供價格線索，但不可直接當作同規格報價或成交價。",
        "source_url": url,
        "reference_amount_twd": _money(source_amount),
        "customer_amount_twd": None,
        "difference_twd": None,
        "difference_percent": None,
        "difference_basis": None,
        "transaction_confirmed": False,
        "formal_evidence_id": None,
    }

    # An estimate, interval or "starting from" number is not an exact point.
    # Do not print the parser-selected range endpoint as a precise price.
    if "SOURCE_PRICE_RANGE_OR_ESTIMATE_NOT_EXACT" in gate.reasons:
        view["label"] = "公開估價範圍參考"
        view["explanation"] = "來源使用區間、起價或約略估價；不把其中一個數字當成精確單價，也不計算價差。"
        view["reference_amount_twd"] = None

    pair = compare_with_target(source, customer_quote) if isinstance(customer_quote, dict) else None
    if pair is None or pair.status != "COMPARABLE":
        if gate.status == "READY_FOR_MATCHING":
            view["label"] = "待確認可比條件"
            view["explanation"] = "尚未證實與屋主工項的規格、計價基準、含稅及數量條件一致；不得顯示精確價差。"
        return view

    # Comparing matching fields never confers formal QA approval.
    approved_id = _find_approved_id(source, approved_record_lookup)
    if approved_id is None:
        view["label"] = "規格相符，待正式覆核"
        view["explanation"] = "比對欄位吻合，但此來源尚未取得正式證據 QA 核准，不提供精確價差。"
        return view

    customer_amount = parse_twd_amount(customer_quote.get("amount"))
    if customer_amount is None:
        return view
    delta = customer_amount - source_amount
    percent = (delta / source_amount * Decimal("100")).quantize(Decimal("0.1"))
    view.update({
        "tier": "COMPARABLE",
        "label": "同規格公開報價比較",
        "explanation": "同工項、規格、地區、單位、計價基準及稅況相符，且來源通過正式 QA；公開價不等於實際成交價，差異不等於超收。",
        "customer_amount_twd": _money(customer_amount),
        "difference_twd": _money(delta),
        "difference_percent": _money(percent),
        "difference_basis": "客戶報價減公開來源價格；百分比以公開來源價格為分母",
        "formal_evidence_id": approved_id,
    })
    return view


def render_public_evidence_html(view: dict, title: str = "公開報價依據") -> str:
    """Render one escaped report evidence block with direct new-tab citation.

    No href is generated for rejected/held evidence. Callers should omit those
    blocks entirely from customer reports. Do not insert any raw source HTML.
    """
    if not isinstance(view, dict) or view.get("visible") is not True:
        return ""
    if view.get("tier") not in ("COMPARABLE", "REFERENCE_ONLY"):
        return ""
    url = view.get("source_url")
    if not isinstance(url, str):
        return ""
    # Re-validate link before rendering. The integration must still use the
    # network collector's independently checked DNS/redirect safety policy.
    from evidence_gate import html_source_link
    try:
        link = html_source_link(url)
    except ValueError:
        return ""
    heading = escape(str(title), quote=True)
    label = escape(str(view.get("label") or ""), quote=True)
    explanation = escape(str(view.get("explanation") or ""), quote=True)
    amount = parse_twd_amount(view.get("reference_amount_twd"))
    if amount is None and view.get("tier") == "COMPARABLE":
        return ""
    html = (
        '<article class="judun-public-evidence" data-evidence-tier="' +
        escape(view["tier"], quote=True) + '">'
        '<h3>' + heading + '</h3>'
        '<p><strong>' + label + '</strong></p>'
        + ('<p>公開來源價格：NT$' + escape(f"{amount:,.2f}".removesuffix(".00")) + '</p>'
           if amount is not None else '')
        + '<p>' + explanation + '</p>'
    )
    if view["tier"] == "COMPARABLE":
        customer = parse_twd_amount(view.get("customer_amount_twd"))
        diff = view.get("difference_twd")
        percent = view.get("difference_percent")
        if customer is None or not isinstance(diff, str) or not isinstance(percent, str):
            return ""
        html += (
            '<p>屋主報價：NT$' + escape(f"{customer:,.2f}".removesuffix(".00")) +
            '；與公開來源差額：NT$' + escape(diff) +
            '（' + escape(percent) + '%，以公開來源價格為基準）</p>'
        )
    return html + '<p>' + link + '</p></article>'
