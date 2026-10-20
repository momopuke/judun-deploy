"""Server-side render adapter: vetted public evidence to one report section.

Candidate only. This module is NOT wired to the current public website,
payment endpoints, actual customer report routes, PDF renderer or formal DB.
CALLER MUST already authorize the requesting user and case/report ownership,
and must supply a server-side approved_record_lookup (never browser input).

Safe characteristics: no DB writes, no network, bounded source count, exact
source dedupe, escaped HTML and no forced changes to approved CSS/branding.
"""
from __future__ import annotations

from html import escape

from evidence_display import (
    build_public_evidence_view,
    fingerprint_approval_source,
    render_public_evidence_html,
)

MAX_SOURCE_ROWS = 200
MAX_VISIBLE_ITEMS = 20


def render_report_public_price_sources(source_rows: list, customer_quote: dict,
                                       *, approved_record_lookup=None) -> dict:
    """Build strictly server-generated public price citations for ONE quote item.

    This routine may only be called inside an already-authorized report route.
    Authorization and report ownership are deliberately NOT inferred from a
    customer_quote, item list, frontend flag, or report ID.
    """
    empty = {
        "html": "", "comparable": 0, "reference_only": 0,
        "excluded": 0, "displayed": 0, "truncated": False,
        "status": "INVALID_INPUT",
    }
    if (not isinstance(source_rows, list) or not isinstance(customer_quote, dict)
            or len(source_rows) > MAX_SOURCE_ROWS):
        return empty

    candidate_views = []
    seen = set()
    excluded = 0
    for source in source_rows:
        if not isinstance(source, dict):
            excluded += 1
            continue
        try:
            fingerprint = fingerprint_approval_source(source)
        except (ValueError, TypeError):
            excluded += 1
            continue
        if fingerprint in seen:
            # Exact duplicate, NOT multiple case prices on the same URL.
            continue
        seen.add(fingerprint)
        view = build_public_evidence_view(
            source, customer_quote, approved_record_lookup=approved_record_lookup
        )
        if not view["visible"]:
            excluded += 1
            continue
        candidate_views.append((view, str(source.get("item_name") or "公開報價依據")))

    # Valid and QA-approved same-scope price first, context-only after.
    candidate_views.sort(key=lambda item: item[0]["tier"] != "COMPARABLE")
    html_items = []
    comparable_count = 0
    reference_count = 0
    for view, title in candidate_views:
        if view["tier"] == "COMPARABLE":
            comparable_count += 1
        else:
            reference_count += 1
        if len(html_items) < MAX_VISIBLE_ITEMS:
            html = render_public_evidence_html(view, title=title)
            if html:
                html_items.append(html)

    displayed = len(html_items)
    truncated = len(candidate_views) > displayed
    summary = (
        '<section class="judun-public-price-sources" '
        'aria-labelledby="judun-public-price-sources-heading">'
        '<h2 id="judun-public-price-sources-heading">公開來源與價差依據</h2>'
        '<p>可比公開報價：' + str(comparable_count) +
        ' 筆；僅供參考：' + str(reference_count) + ' 筆。</p>'
    )
    if comparable_count == 0:
        summary += (
            '<p>目前沒有通過同規格比對與正式 QA 的價格來源；'
            '不得將參考行情解讀為已確認價差或實際成交價。</p>'
        )
    if truncated:
        summary += (
            '<p>本區僅顯示前 ' + str(displayed) +
            ' 筆來源，其餘來源尚未在此展開；請勿把此清單當成完整來源總數。</p>'
        )
    # No raw source HTML or clickable third-party script can reach the output.
    summary += ''.join(html_items) + '</section>'
    return {
        "html": summary,
        "comparable": comparable_count,
        "reference_only": reference_count,
        "excluded": excluded,
        "displayed": displayed,
        "truncated": truncated,
        "status": "OK",
    }
