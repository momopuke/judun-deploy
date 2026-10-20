"""Candidate complete-quote renderer: never omit a customer's quoted line.

This is an internal SERVER-SIDE presentation contract, NOT wired into the
production FastAPI routes, PDF generator, payment or identity services. All
input quote rows and source rows MUST come from an already-authorized case.

One call renders at most 30 customer items; the caller must continue until
the response status is COMPLETE. This avoids silently truncating line items.
"""
from __future__ import annotations

from html import escape
from decimal import Decimal

from evidence_gate import parse_twd_amount
from paged_evidence_report import render_paged_public_price_sources

MAX_QUOTE_ITEMS = 5000
ITEMS_PER_PAGE = 30


def _label(value: object, fallback: str, limit: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        return escape(fallback)
    # If user-provided text exceeds the safe bound, display an explicit
    # review marker rather than quietly truncating a potentially important name.
    return escape(value.strip() if len(value) <= limit else fallback + "（內容過長，待人工確認）")


def render_authorized_quote_items(
    quote_rows: list,
    source_rows_by_item: list,
    *,
    offset: int = 0,
    approved_record_lookup=None,
) -> dict:
    """Render all original quote lines across pages; no speculative totals."""
    empty = {
        "status": "INVALID_INPUT", "html": "", "next_offset": None,
        "complete": False, "items_rendered": 0, "source_alerts": [],
    }
    if (not isinstance(quote_rows, list)
            or not isinstance(source_rows_by_item, list)
            or len(quote_rows) != len(source_rows_by_item)
            or len(quote_rows) > MAX_QUOTE_ITEMS
            or type(offset) is not int or offset < 0 or offset > len(quote_rows)):
        return empty

    finish = min(len(quote_rows), offset + ITEMS_PER_PAGE)
    source_alerts = []
    markup = [
        '<section class="judun-complete-quote-lines" aria-label="完整估價工項明細">',
        '<h2>完整估價工項明細</h2>',
    ]
    for i in range(offset, finish):
        row = quote_rows[i]
        sources = source_rows_by_item[i]
        # A malformed item is never skipped or presented as a valid quote.
        if not isinstance(row, dict):
            markup.append(
                '<article class="judun-quote-line judun-quote-line--review">'
                '<h3>第 ' + str(i + 1) + ' 項：待核對原始資料</h3>'
                '<p>本工項資料不完整，請核對原始報價，不能據此計算價差。</p>'
                '</article>'
            )
            source_alerts.append(i)
            continue

        name = _label(row.get("item_name"), "工項名稱未辨識")
        category = _label(row.get("category"), "類別待確認")
        unit = _label(row.get("unit"), "單位待確認", 48)
        amount = parse_twd_amount(row.get("amount"))
        price = ("NT$" + f"{amount:,.2f}".removesuffix(".00")
                 if amount is not None else "報價金額待人工確認")
        markup.append(
            '<article class="judun-quote-line">'
            '<h3>第 ' + str(i + 1) + ' 項：' + name + '</h3>'
            '<p>工項類別：' + category + '；單位：' + unit +
            '；報價：' + escape(price) + '</p>'
        )

        # Missing source list must not erase a customer's own quoted item.
        if not isinstance(sources, list):
            source_alerts.append(i)
            markup.append('<p>公開來源資料未就緒；本工項仍保留於完整版。</p></article>')
            continue
        if not sources:
            markup.append('<p>尚無可用公開來源；不自行推估價差。</p></article>')
            continue

        # Smaller report rows can inline all trusted citations; larger source
        # collections are explicitly flagged as partial and require follow-up.
        evidence = render_paged_public_price_sources(
            sources, row, pages_per_call=5,
            approved_record_lookup=approved_record_lookup,
        )
        if evidence["status"] not in ("COMPLETE",):
            source_alerts.append(i)
            markup.append(
                '<p>本工項公開來源仍待分頁核對，不能將此報告視為證據已完整呈現。</p>'
            )
        markup.extend(evidence.get("pages", []))
        markup.append('</article>')

    markup.append('</section>')
    next_offset = finish if finish < len(quote_rows) else None
    complete = next_offset is None and not source_alerts
    status = "COMPLETE" if complete else "MORE_ITEMS" if next_offset is not None else "SOURCE_REVIEW_REQUIRED"
    if next_offset is not None:
        markup.insert(2, '<p>本頁僅列出部分工項；下一頁必須繼續輸出，不能當作完整版結束。</p>')
    if source_alerts:
        markup.insert(2, '<p>部分工項需補充來源或人工核對；保留工項，不以參考價冒充已驗證價差。</p>')
    return {
        "status": status,
        "html": ''.join(markup),
        "next_offset": next_offset,
        "complete": complete,
        "items_rendered": finish - offset,
        "source_alerts": source_alerts,
    }
