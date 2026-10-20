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

from evidence_gate import (
    evaluate,
    compare_with_target,
    html_evidence_source_link,
    parse_twd_amount,
)

_COMPARABLE_FIELDS = ("category", "item_name", "unit", "spec", "locality",
                      "currency", "price_basis", "tax_included")


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


def build_public_evidence_view(
    source: dict,
    customer_quote: dict | None = None,
    *,
    formal_qa_approved: bool = False,
    formal_evidence_id: str | None = None,
) -> dict:
    """Return safe display data; comparisons require BOTH strict match and formal QA.

    The formal approval flag and evidence ID must be supplied by the trusted
    server after looking up this very source in its approved evidence registry.
    They are NOT evidence of approval by themselves.
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
    # Do not accidentally print the parser-selected range endpoint as a price.
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

    # A structurally matched page is not automatically accepted formal data.
    # An approval ID must also identify a nonempty approved source record.
    approved = (formal_qa_approved is True
                and isinstance(formal_evidence_id, str)
                and 0 < len(formal_evidence_id.strip()) <= 128)
    if not approved:
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
        "formal_evidence_id": formal_evidence_id.strip(),
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
        ('<p>公開來源價格：NT
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
 + escape(f"{amount:,.2f}".removesuffix(".00")) + '</p>'
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
