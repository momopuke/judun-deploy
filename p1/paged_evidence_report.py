"""Bounded multi-page rendering of public renovation-price evidence.

Integration candidate only, never deployed. Production must authorize the
user, report and item ownership before calling. The incoming source_rows are
an ordered, stable snapshot from the trusted server, not an HTTP-provided list.

This does not merge unlike work items, mutate formal evidence or create price
approval. A caller must keep the SAME immutable snapshot across paginated calls.
"""
from __future__ import annotations

import hashlib
import json

from evidence_display import fingerprint_approval_source, _APPROVED_SOURCE_KEYS
from report_evidence_section import (
    MAX_SOURCE_ROWS,
    render_report_public_price_sources,
)

MAX_PAGES_PER_CALL = 5
MAX_ITEMS_IN_COLLECTION = 10000


def source_row_snapshot_marker(source: object) -> str:
    """Fingerprint every bounded source row, including malformed candidates.

    The formal QA fingerprint is used when available; a malformed-but-JSON
    row is NOT approved evidence, but its bytes still bind pagination. Never
    collapse distinct malformed rows into the same static marker.
    """
    if isinstance(source, dict):
        try:
            return "QA:" + fingerprint_approval_source(source)
        except (TypeError, ValueError):
            pass
        # Bound malformed fallback to fields the evidence gate and renderer
        # actually consume. Do not serialize arbitrary crawler metadata,
        # unexpected large attachments or unrelated PII as part of a digest.
        source = {key: source.get(key) for key in _APPROVED_SOURCE_KEYS}
        for value in source.values():
            if isinstance(value, str) and len(value) > 65536:
                raise ValueError("oversized public source field")
            if isinstance(value, list) and len(value) > 12:
                raise ValueError("oversized public source list")
    elif not (source is None or type(source) in (str, int, float, bool, list)):
        raise ValueError("unsupported public source row")
    try:
        raw = json.dumps(
            source, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("unverifiable public source snapshot") from exc
    if len(raw) > 65536:
        raise ValueError("unverifiable oversized public source snapshot")
    return "UNVERIFIED:" + hashlib.sha256(raw).hexdigest()


def public_source_snapshot_digest(source_rows: list) -> str:
    """Checksum the *entire ordered* candidate list, including invalid rows."""
    if not isinstance(source_rows, list) or len(source_rows) > MAX_ITEMS_IN_COLLECTION:
        raise ValueError("invalid source snapshot")
    h = hashlib.sha256()
    h.update(b"judun.full-public-sources.v2\\n")
    for source in source_rows:
        marker = source_row_snapshot_marker(source)
        h.update(marker.encode("ascii") + b"\\n")
    return h.hexdigest()


def render_paged_public_price_sources(
    source_rows: list,
    customer_quote: dict,
    *,
    offset: int = 0,
    pages_per_call: int = 3,
    approved_record_lookup=None,
    expected_snapshot_digest: str | None = None,
) -> dict:
    """Render up to pages_per_call x 200 sources, exposing a continuation offset.

    Complete means EVERY row in the supplied snapshot was inspected, not that
    every source is relevant or comparable. Never infer completeness if MORE.
    """
    invalid = {
        "status": "INVALID_INPUT", "pages": [], "next_offset": None,
        "processed": 0, "comparable": 0, "reference_only": 0,
        "excluded": 0, "duplicates_skipped": 0, "displayed": 0,
        "complete": False, "snapshot_digest": None,
    }
    if (not isinstance(source_rows, list)
            or not isinstance(customer_quote, dict)
            or len(source_rows) > MAX_ITEMS_IN_COLLECTION
            or type(offset) is not int or offset < 0 or offset > len(source_rows)
            or type(pages_per_call) is not int
            or not 1 <= pages_per_call <= MAX_PAGES_PER_CALL):
        return invalid

    try:
        digest = public_source_snapshot_digest(source_rows)
    except ValueError:
        return {**invalid, "status": "SOURCE_SNAPSHOT_UNVERIFIABLE"}
    if offset != 0 and (not isinstance(expected_snapshot_digest, str)
                        or expected_snapshot_digest != digest):
        return {
            **invalid, "status": "SOURCE_SNAPSHOT_CHANGED",
            "snapshot_digest": digest,
        }
    if expected_snapshot_digest is not None and expected_snapshot_digest != digest:
        return {
            **invalid, "status": "SOURCE_SNAPSHOT_CHANGED",
            "snapshot_digest": digest,
        }

    # Repeat past fingerprint inspection without rendering, so a continued
    # request cannot emit a formerly displayed identical record a second time.
    # This is bounded to MAX_ITEMS_IN_COLLECTION and deterministic over a frozen
    # source snapshot. Callers MUST NOT reorder rows between requests.
    seen = set()
    for source in source_rows[:offset]:
        if isinstance(source, dict):
            try:
                seen.add(fingerprint_approval_source(source))
            except (TypeError, ValueError):
                continue

    next_end = min(len(source_rows), offset + pages_per_call * MAX_SOURCE_ROWS)
    pages = []
    totals = {
        "comparable": 0, "reference_only": 0, "excluded": 0,
        "duplicates_skipped": 0, "displayed": 0,
    }
    for start in range(offset, next_end, MAX_SOURCE_ROWS):
        end = min(next_end, start + MAX_SOURCE_ROWS)
        unique_chunk = []
        for source in source_rows[start:end]:
            if isinstance(source, dict):
                try:
                    sha = fingerprint_approval_source(source)
                except (TypeError, ValueError):
                    sha = None
                if sha is not None:
                    if sha in seen:
                        totals["duplicates_skipped"] += 1
                        continue
                    seen.add(sha)
            unique_chunk.append(source)
        result = render_report_public_price_sources(
            unique_chunk,
            customer_quote,
            approved_record_lookup=approved_record_lookup,
            view_mode="full",
        )
        if result["status"] != "OK":
            return {
                **invalid, "status": "PAGE_FAILED",
                "next_offset": start,
                "processed": start - offset,
            }
        pages.append(result["html"])
        for name in ("comparable", "reference_only", "excluded", "displayed"):
            totals[name] += result[name]

    # Each independent paginated call must be internally consistent even
    # when a background expansion writer mutates a shared list midway. Never
    # return partial HTML compiled from two source versions.
    try:
        unchanged = public_source_snapshot_digest(source_rows) == digest
    except ValueError:
        unchanged = False
    if not unchanged:
        return {
            **invalid, "status": "SOURCE_SNAPSHOT_CHANGED",
            "snapshot_digest": None,
        }

    complete = next_end == len(source_rows)
    return {
        "status": "COMPLETE" if complete else "MORE",
        "pages": pages,
        "next_offset": None if complete else next_end,
        "processed": next_end - offset,
        **totals,
        "complete": complete,
        "snapshot_digest": digest,
    }
