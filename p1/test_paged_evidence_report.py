"""Synthetic pagination contract tests: 200-row pages, continuation, no loss."""
from __future__ import annotations

import unittest

from paged_evidence_report import (
    MAX_ITEMS_IN_COLLECTION,
    render_paged_public_price_sources,
    public_source_snapshot_digest,
)
from test_evidence_gate import valid_case


def customer():
    source = valid_case()
    names = ("category", "item_name", "unit", "spec", "locality",
             "currency", "price_basis", "tax_included")
    return {**{name: source[name] for name in names}, "amount": "NT$20,000"}


def distinct(count):
    return [
        {**valid_case(), "url": "https://example.com.tw/renovation/source-" + str(i)}
        for i in range(count)
    ]


class PagedReportTests(unittest.TestCase):
    def test_201_sources_complete_across_two_pages_without_dropping_last(self):
        sources = distinct(201)
        one = render_paged_public_price_sources(
            sources, customer(), pages_per_call=1)
        self.assertEqual(one["status"], "MORE")
        self.assertEqual(one["processed"], 200)
        self.assertEqual(one["next_offset"], 200)
        self.assertEqual(one["reference_only"], 200)
        self.assertEqual(one["displayed"], 200)
        two = render_paged_public_price_sources(
            sources, customer(), offset=one["next_offset"], pages_per_call=1,
            expected_snapshot_digest=one["snapshot_digest"])
        self.assertEqual(two["status"], "COMPLETE")
        self.assertTrue(two["complete"])
        self.assertEqual(two["processed"], 1)
        self.assertIn("source-200", two["pages"][0])
        self.assertEqual(one["displayed"] + two["displayed"], 201)

    def test_many_rows_do_not_disappear_in_full_report(self):
        sources = distinct(415)
        result = render_paged_public_price_sources(
            sources, customer(), pages_per_call=3)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(len(result["pages"]), 3)
        self.assertEqual(result["reference_only"], 415)
        self.assertEqual(result["displayed"], 415)
        self.assertEqual(result["next_offset"], None)
        self.assertIn("source-414", "".join(result["pages"]))

    def test_cross_page_duplicates_are_not_counted_twice(self):
        base = distinct(200)
        more = [dict(base[0]), *distinct(2)]
        result = render_paged_public_price_sources(
            base + more, customer(), pages_per_call=2)
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["duplicates_skipped"], 3)
        self.assertEqual(result["reference_only"], 200)
        # All of the later rows are duplicate snapshots and not new cases.
        self.assertEqual(result["displayed"], 200)

    def test_duplicate_across_separate_continuations_is_removed(self):
        first = distinct(200)
        last = [dict(first[0]), {**valid_case(), "url": "https://example.com.tw/new"}]
        result = render_paged_public_price_sources(
            first + last, customer(), offset=200, pages_per_call=1,
            expected_snapshot_digest=public_source_snapshot_digest(first + last))
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["duplicates_skipped"], 1)
        self.assertEqual(result["reference_only"], 1)
        self.assertEqual(result["displayed"], 1)

    def test_mutated_source_snapshot_refuses_cross_page_continuation(self):
        source_rows = distinct(201)
        first = render_paged_public_price_sources(
            source_rows, customer(), pages_per_call=1)
        edited = list(source_rows)
        edited[0] = {**source_rows[0], "amount": "NT$20,000"}
        result = render_paged_public_price_sources(
            edited, customer(), offset=first["next_offset"],
            pages_per_call=1, expected_snapshot_digest=first["snapshot_digest"])
        self.assertEqual(result["status"], "SOURCE_SNAPSHOT_CHANGED")
        self.assertFalse(result["complete"])
        self.assertEqual(result["pages"], [])

    def test_mutation_during_paginated_render_returns_no_partial_html(self):
        from unittest.mock import patch
        import paged_evidence_report as page
        sources = distinct(201)
        original = page.render_report_public_price_sources
        triggered = []

        def modify_after_render(chunk, *args, **kwargs):
            result = original(chunk, *args, **kwargs)
            if not triggered:
                triggered.append(True)
                sources[0]["amount"] = "NT$19,000"
            return result

        with patch.object(page, "render_report_public_price_sources",
                          side_effect=modify_after_render):
            result = page.render_paged_public_price_sources(
                sources, customer(), pages_per_call=2)
        self.assertEqual(result["status"], "SOURCE_SNAPSHOT_CHANGED")
        self.assertEqual(result["pages"], [])
        self.assertEqual(result["displayed"], 0)
        self.assertFalse(result["complete"])

    def test_continuation_without_initial_snapshot_digest_is_denied(self):
        result = render_paged_public_price_sources(
            distinct(201), customer(), offset=200, pages_per_call=1)
        self.assertEqual(result["status"], "SOURCE_SNAPSHOT_CHANGED")
        self.assertEqual(result["pages"], [])

    def test_multiple_valid_cases_share_url_but_keep_different_prices(self):
        source = valid_case()
        other = {**source, "body": "台北裝修油漆報價 NT$16,000／坪",
                 "amount": "NT$16,000"}
        result = render_paged_public_price_sources(
            [source, other], customer(), pages_per_call=1)
        self.assertEqual(result["displayed"], 2)
        self.assertEqual(result["duplicates_skipped"], 0)

    def test_oversized_collections_and_invalid_offsets_are_explicit_failure(self):
        sources = distinct(2)
        for kwargs in ({"offset": -1}, {"offset": 3},
                       {"offset": True}, {"pages_per_call": 0},
                       {"pages_per_call": 6}, {"pages_per_call": True}):
            with self.subTest(kwargs=kwargs):
                result = render_paged_public_price_sources(sources, customer(), **kwargs)
                self.assertEqual(result["status"], "INVALID_INPUT")
                self.assertFalse(result["complete"])
                self.assertEqual(result["pages"], [])
        too_many = [valid_case()] * (MAX_ITEMS_IN_COLLECTION + 1)
        result = render_paged_public_price_sources(too_many, customer())
        self.assertEqual(result["status"], "INVALID_INPUT")
        self.assertFalse(result["complete"])

    def test_empty_snapshot_is_completely_handled(self):
        result = render_paged_public_price_sources([], customer())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["pages"], [])

    def test_unrelated_sources_are_filtered_not_silently_marked_comparable(self):
        bad = dict(valid_case(), category="水電工程")
        result = render_paged_public_price_sources([bad, valid_case()], customer())
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(result["reference_only"], 1)
        self.assertEqual(result["comparable"], 0)
        self.assertEqual(result["excluded"], 1)

if __name__ == "__main__":
    unittest.main()
