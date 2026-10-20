"""Candidate complete-quote renderer: never omit a customer's quoted line.

This is an internal SERVER-SIDE presentation contract, NOT wired into the
production FastAPI routes, PDF generator, payment or identity services. All
input quote rows and source rows MUST come from an already-authorized case.

One call renders at most 30 customer items; the caller must continue until
the response status is COMPLETE. This avoids silently truncating line items.
"""
from __future__ import annotations

from html import escape
import hashlib
import json

from evidence_gate import parse_twd_amount
from evidence_display import fingerprint_approval_source
from paged_evidence_report import render_paged_public_price_sources

MAX_QUOTE_ITEMS = 5000
ITEMS_PER_PAGE = 30
MAX_ASSOCIATED_SOURCE_ROWS = 20000


def _label(value: object, fallback: str, limit: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        return escape(fallback)
    # If user-provided text exceeds the safe bound, display an explicit
    # review marker rather than quietly truncating a potentially important name.
    return escape(value.strip() if len(value) <= limit else fallback + "（內容過長，待人工確認）")


_QUOTE_FIELDS = ("category", "item_name", "unit", "amount", "quantity",
                 "spec", "currency", "price_basis", "tax_included", "locality")


def quote_snapshot_digest(quote_rows: list) -> str:
    """Bind continuation to an immutable ordered collection of customer lines."""
    if not isinstance(quote_rows, list) or len(quote_rows) > MAX_QUOTE_ITEMS:
        raise ValueError("invalid quote snapshot")
    digest = hashlib.sha256(b"judun.quote-items.v1")
    for quote in quote_rows:
        if isinstance(quote, dict):
            fields = {name: quote.get(name) for name in _QUOTE_FIELDS}
            try:
                raw = json.dumps(fields, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False).encode("utf-8")
            except (TypeError, ValueError):
                raw = b"INVALID_QUOTE_FIELDS"
        else:
            raw = b"INVALID_QUOTE_ROW"
        digest.update(len(raw).to_bytes(8, "big") + raw)
    return digest.hexdigest()


def source_association_digest(rows: list, expected_items: int) -> tuple[str, bool]:
    """Return (digest, safe_for_pairing) for indexed per-item source batches.

    An oversized or misaligned collection disables matching but must never
    delete the customer's original quoted lines. Hashes bind the entire ordered
    item -> source mapping when sources can be safely inspected.
    """
    digest = hashlib.sha256(b"judun.quote-source-map.v1")
    digest.update(str(expected_items).encode("ascii") + b"|")
    if not isinstance(rows, list) or len(rows) != expected_items:
        digest.update(b"UNALIGNED")
        digest.update(str(len(rows) if isinstance(rows, list) else -1).encode("ascii"))
        return digest.hexdigest(), False
    total = sum(len(part) for part in rows if isinstance(part, list))
    if total > MAX_ASSOCIATED_SOURCE_ROWS:
        digest.update(b"OVERSIZED")
        digest.update(str(total).encode("ascii"))
        return digest.hexdigest(), False
    for part in rows:
        if not isinstance(part, list):
            digest.update(b"INVALID_PART")
            continue
        digest.update(len(part).to_bytes(8, "big"))
        for item in part:
            if isinstance(item, dict):
                try:
                    marker = fingerprint_approval_source(item)
                except (TypeError, ValueError):
                    marker = "INVALID_EVIDENCE"
            else:
                marker = "INVALID_ROW"
            digest.update(marker.encode("ascii") + b";")
    return digest.hexdigest(), True


def render_authorized_quote_items(
    quote_rows: list,
    source_rows_by_item: list,
    *,
    offset: int = 0,
    approved_record_lookup=None,
    expected_quote_digest: str | None = None,
    expected_source_digest: str | None = None,
    prior_source_alerts: list[int] | None = None,
) -> dict:
    """Render all original quote lines across pages; no speculative totals."""
    empty = {
        "status": "INVALID_INPUT", "html": "", "next_offset": None,
        "complete": False, "items_rendered": 0, "source_alerts": [],
        "page_source_alerts": [], "quote_digest": None,
        "source_digest": None,
    }
    if (not isinstance(quote_rows, list)
            or not isinstance(source_rows_by_item, list)
            or len(quote_rows) > MAX_QUOTE_ITEMS
            or type(offset) is not int or offset < 0 or offset > len(quote_rows)):
        return empty

    digest = quote_snapshot_digest(quote_rows)
    source_digest, sources_safe = source_association_digest(
        source_rows_by_item, len(quote_rows))
    if ((offset > 0 and expected_quote_digest != digest)
            or (expected_quote_digest is not None and expected_quote_digest != digest)):
        return {**empty, "status": "QUOTE_SNAPSHOT_CHANGED",
                "quote_digest": digest}
    # A later page must receive all earlier review flags. Without a verified
    # cumulative state it may only be described as an incomplete continuation.
    if offset > 0 and (not isinstance(prior_source_alerts, list)
                       or any(type(i) is not int or i < 0 or i >= offset
                              for i in prior_source_alerts)
                       or len(prior_source_alerts) != len(set(prior_source_alerts))):
        return {**empty, "status": "CONTINUATION_STATE_REQUIRED",
                "quote_digest": digest}
    if offset == 0 and prior_source_alerts not in (None, []):
        return {**empty, "status": "INVALID_CONTINUATION_STATE",
                "quote_digest": digest}

    if ((offset > 0 and expected_source_digest != source_digest)
            or (expected_source_digest is not None
                and expected_source_digest != source_digest)):
        return {**empty, "status": "SOURCE_SNAPSHOT_CHANGED",
                "quote_digest": digest, "source_digest": source_digest}

    finish = min(len(quote_rows), offset + ITEMS_PER_PAGE)
    # Never associate sources with the wrong customer quote: if arrays are
    # misaligned, preserve every quote line but suppress ALL source matching.
    aligned = sources_safe
    page_alerts = []
    markup = [
        '<section class="judun-complete-quote-lines" aria-label="完整估價工項明細">',
        '<h2>完整估價工項明細</h2>',
    ]
    for i in range(offset, finish):
        row = quote_rows[i]
        sources = source_rows_by_item[i] if aligned else None
        # A malformed item is never skipped or presented as a valid quote.
        if not isinstance(row, dict):
            markup.append(
                '<article class="judun-quote-line judun-quote-line--review">'
                '<h3>第 ' + str(i + 1) + ' 項：待核對原始資料</h3>'
                '<p>本工項資料不完整，請核對原始報價，不能據此計算價差。</p>'
                '</article>'
            )
            page_alerts.append(i)
            continue

        name = _label(row.get("item_name"), "工項名稱未辨識")
        category = _label(row.get("category"), "類別待確認")
        unit = _label(row.get("unit"), "單位待確認", 48)
        amount = parse_twd_amount(row.get("amount"))
        currency = str(row.get("currency") or "").upper()
        twd = currency in ("TWD", "NTD", "NT$", "新臺幣", "新台幣")
        # Keeping a malformed quote line is not the same as verifying it.
        # Explicitly carry a review flag even when there are zero sources.
        critical = ("category", "item_name", "unit", "spec", "locality")
        fields_complete = all(
            isinstance(row.get(key), str) and bool(row[key].strip())
            and len(row[key]) <= 160 for key in critical
        )
        if (not fields_complete or amount is None or not twd
                or row.get("price_basis") not in ("unit_price", "total_price")
                or type(row.get("tax_included")) is not bool):
            if i not in page_alerts:
                page_alerts.append(i)
        if amount is not None and twd:
            price = "NT$" + format(amount, ",f").rstrip("0").rstrip(".") if amount.as_tuple().exponent < 0 else "NT$" + format(amount, ",f")
        else:
            raw = row.get("amount")
            # Preserve an original short amount for manual review, but NEVER
            # relabel a foreign/unknown currency as NT dollars.
            if isinstance(raw, str) and 0 < len(raw.strip()) <= 80:
                price = "原始金額：" + raw.strip() + "（幣別或金額待核對）"
            else:
                price = "報價金額待人工確認"
        markup.append(
            '<article class="judun-quote-line">'
            '<h3>第 ' + str(i + 1) + ' 項：' + name + '</h3>'
            '<p>工項類別：' + category + '；單位：' + unit +
            '；報價：' + escape(price) + '</p>'
        )

        # Missing source list must not erase a customer's own quoted item.
        if not isinstance(sources, list):
            page_alerts.append(i)
            markup.append('<p>公開來源資料未就緒；本工項仍保留於完整版。</p></article>')
            continue
        if not sources:
            markup.append('<p>尚無可用公開來源；不自行推估價差。</p></article>')
            continue

        # Drain the bounded source pagination inside this report item. A
        # 1,100-source case must not stop after its first 1,000 source rows.
        # The same source fingerprint is required for every continuation.
        evidence_offset = 0
        evidence_digest = None
        result_status = "MORE"
        evidence_pages = []
        while result_status == "MORE":
            evidence = render_paged_public_price_sources(
                sources, row, offset=evidence_offset, pages_per_call=5,
                approved_record_lookup=approved_record_lookup,
                expected_snapshot_digest=evidence_digest,
            )
            result_status = evidence["status"]
            evidence_pages.extend(evidence.get("pages", []))
            evidence_digest = evidence.get("snapshot_digest")
            next_offset = evidence.get("next_offset")
            if result_status == "MORE":
                if (type(next_offset) is not int
                        or next_offset <= evidence_offset
                        or next_offset > len(sources)):
                    result_status = "SOURCE_PAGE_STALLED"
                    break
                evidence_offset = next_offset
        if result_status != "COMPLETE":
            if i not in page_alerts:
                page_alerts.append(i)
            markup.append(
                '<p>本工項公開來源仍待分頁核對，不能將此報告視為證據已完整呈現。</p>'
            )
        markup.extend(evidence_pages)
        markup.append('</article>')

    markup.append('</section>')
    next_offset = finish if finish < len(quote_rows) else None
    source_alerts = list(prior_source_alerts or []) + page_alerts
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
        "page_source_alerts": page_alerts,
        "quote_digest": digest,
        "source_digest": source_digest,
    }


def render_complete_authorized_quote_report(
    quote_rows: list,
    source_rows_by_item: list,
    *,
    approved_record_lookup=None,
) -> dict:
    """Build a complete server-side report from every original quote row.

    The adapter owns all continuations, so it cannot accidentally label the
    last page COMPLETE while a previous page required source review. The caller
    must render the returned HTML in its existing authorized report template.
    No DB write, PDF conversion, payment request, or publication occurs here.
    """
    invalid = {
        "status": "INVALID_INPUT", "html": "", "complete": False,
        "quote_items": 0, "pages": 0, "source_alerts": [],
    }
    if (not isinstance(quote_rows, list)
            or not isinstance(source_rows_by_item, list)
            or len(quote_rows) > MAX_QUOTE_ITEMS):
        return invalid
    all_pages = []
    cumulative_alerts = []
    digest = None
    sources_digest = None
    offset = 0
    while True:
        page = render_authorized_quote_items(
            quote_rows,
            source_rows_by_item,
            offset=offset,
            approved_record_lookup=approved_record_lookup,
            expected_quote_digest=digest,
            expected_source_digest=sources_digest,
            prior_source_alerts=cumulative_alerts,
        )
        if page["status"] not in ("COMPLETE", "MORE_ITEMS", "SOURCE_REVIEW_REQUIRED"):
            return {**invalid, "status": page["status"]}
        all_pages.append(page["html"])
        cumulative_alerts = page["source_alerts"]
        digest = page["quote_digest"]
        sources_digest = page["source_digest"]
        if page["next_offset"] is None:
            complete = page["complete"]
            return {
                "status": "COMPLETE" if complete else "SOURCE_REVIEW_REQUIRED",
                "html": "".join(all_pages),
                "complete": complete,
                "quote_items": len(quote_rows),
                "pages": len(all_pages),
                "source_alerts": cumulative_alerts,
            }
        offset = page["next_offset"]
