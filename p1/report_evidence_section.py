"""Server-side render adapter: vetted public evidence to one report section.

Candidate only. This module is NOT wired to the current public website,
payment endpoints, actual customer report routes, PDF renderer or formal DB.
CALLER MUST authorize the requesting user and case/report ownership first.
Any approved_record_lookup MUST be server-side only (never browser input).
Without that trusted callback, references can be shown but NOT price gaps.

Safe characteristics: no DB writes, no network, bounded source count, exact
source dedupe, escaped HTML and no forced changes to approved CSS/branding.
"""
from __future__ import annotations

import unicodedata

from evidence_display import (
    build_public_evidence_view,
    fingerprint_approval_source,
    render_public_evidence_html,
)

MAX_SOURCE_ROWS = 200
MAX_VISIBLE_ITEMS = 20

def _same_item(a: object, b: object) -> bool:
    """Compare scope labels without inventing synonyms or guessing similarity."""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    left = "".join(unicodedata.normalize("NFKC", a).split()).casefold()
    right = "".join(unicodedata.normalize("NFKC", b).split()).casefold()
    return bool(left and right and left == right)



def render_report_public_price_sources(source_rows: list, customer_quote: dict,
                                       *, approved_record_lookup=None,
                                       view_mode: str = "compact") -> dict:
    """Build strictly server-generated public price citations for ONE quote item.

    This routine may only be called inside an already-authorized report route.
    Authorization and report ownership are deliberately NOT inferred from a
    customer_quote, item list, frontend flag, or report ID.
    """
    empty = {
        "html": "", "comparable": 0, "reference_only": 0,
        "excluded": 0, "displayed": 0, "truncated": False,
        "excluded_breakdown": {}, "status": "INVALID_INPUT",
    }
    if (not isinstance(source_rows, list) or not isinstance(customer_quote, dict)
            or len(source_rows) > MAX_SOURCE_ROWS or view_mode not in ("compact", "full")
            or not isinstance(customer_quote.get("category"), str)
            or not isinstance(customer_quote.get("item_name"), str)
            or not customer_quote["category"].strip()
            or not customer_quote["item_name"].strip()):
        return empty

    candidate_views = []
    seen = set()
    excluded = 0
    reason_counts = {}
    def count_excluded(code: str):
        nonlocal excluded
        excluded += 1
        reason_counts[code] = reason_counts.get(code, 0) + 1

    for source in source_rows:
        if not isinstance(source, dict):
            count_excluded("INVALID_ROW")
            continue
        # This section describes ONE client work item; a different work item
        # on an otherwise legitimate renovation page is NOT relevant here.
        # Disclose unrelated records neither as references nor as price gaps.
        if not _same_item(source.get("category"), customer_quote.get("category")):
            count_excluded("CATEGORY_MISMATCH")
            continue
        if not _same_item(source.get("item_name"), customer_quote.get("item_name")):
            count_excluded("ITEM_MISMATCH")
            continue
        try:
            fingerprint = fingerprint_approval_source(source)
        except (ValueError, TypeError):
            count_excluded("UNREADABLE_EVIDENCE")
            continue
        if fingerprint in seen:
            # Exact duplicate, NOT multiple case prices on the same URL.
            continue
        seen.add(fingerprint)
        view = build_public_evidence_view(
            source, customer_quote, approved_record_lookup=approved_record_lookup
        )
        if not view["visible"]:
            count_excluded("SOURCE_REJECTED_OR_UNVERIFIED")
            continue
        candidate_views.append((view, str(source.get("item_name") or "公開報價依據")))

    # Valid, QA-approved same-scope sources first; preserve stable input order
    # within the same tier. The source amount never determines priority.
    candidate_views.sort(key=lambda item: item[0]["tier"] != "COMPARABLE")
    comparable_count = sum(view["tier"] == "COMPARABLE" for view, _ in candidate_views)
    reference_count = len(candidate_views) - comparable_count
    limit = MAX_VISIBLE_ITEMS if view_mode == "compact" else MAX_SOURCE_ROWS

    # Keep all comparable sources before reference-only. A compact page does
    # not let unrelated benchmarks push verified sources outside the cap.
    rendered = []
    for view, title in candidate_views[:limit]:
        html = render_public_evidence_html(view, title=title)
        if html:
            rendered.append((view["tier"], html))

    displayed = len(rendered)
    truncated = len(candidate_views) > displayed
    summary = (
        '<section class="judun-public-price-sources" aria-label="公開來源與價差依據">'
        '<h2>公開來源與價差依據</h2>'
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
    # Keep actionable comparable evidence readable. Move long reference lists
    # into a native accessible disclosure. Each report item has no duplicate
    # element IDs, even when many items are mounted on one page.
    summary += ''.join(html for tier, html in rendered if tier == "COMPARABLE")
    references = [html for tier, html in rendered if tier == "REFERENCE_ONLY"]
    if references:
        summary += (
            '<details class="judun-related-price-sources"' +
            (' open' if view_mode == 'full' else '') + '>'
            '<summary>展開相關公開參考來源（' + str(len(references)) + ' 筆）</summary>'
            + ''.join(references) + '</details>'
        )
    summary += '</section>'
    return {
        "html": summary,
        "comparable": comparable_count,
        "reference_only": reference_count,
        "excluded": excluded,
        "excluded_breakdown": dict(sorted(reason_counts.items())),
        "displayed": displayed,
        "truncated": truncated,
        "status": "OK",
    }
