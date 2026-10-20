"""Read-only formal approval bridge regression tests. All data are synthetic."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sqlite3
import tempfile
import unittest

from evidence_display import build_public_evidence_view, fingerprint_approval_source
from formal_registry_adapter import (
    ReadOnlyFormalApprovalRegistry,
    REQUIRED_SCHEMA,
)
from test_evidence_gate import valid_case


def quote_for(source):
    keys = ("category", "item_name", "unit", "spec", "locality",
            "currency", "price_basis", "tax_included")
    return {**{key: source[key] for key in keys}, "amount": "NT$20,000"}


class ReadOnlyRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.db_path = Path(self.temp_dir.name) / "formal approvals #1.sqlite3"
        with sqlite3.connect(self.db_path) as db:
            db.executescript(REQUIRED_SCHEMA)
        self.source = valid_case()
        self.fingerprint = fingerprint_approval_source(self.source)
        self.registry = ReadOnlyFormalApprovalRegistry(self.db_path)

    def insert(self, *, fingerprint=None, evidence_id="approved:18", state="approved",
               reviewed_at="2026-10-20T00:00:00+00:00", revoked_at=None):
        with sqlite3.connect(self.db_path) as db:
            db.execute(
                "INSERT INTO judun_formal_evidence_approvals_v1 "
                "(fingerprint,evidence_id,approval_state,reviewed_at_utc,revoked_at_utc) "
                "VALUES (?,?,?,?,?)",
                (fingerprint if fingerprint is not None else self.fingerprint,
                 evidence_id, state, reviewed_at, revoked_at),
            )

    def test_trusted_record_can_allow_exact_price_difference(self):
        self.insert()
        result = build_public_evidence_view(
            self.source, quote_for(self.source),
            approved_record_lookup=self.registry)
        self.assertEqual(result["tier"], "COMPARABLE")
        self.assertEqual(result["difference_twd"], "2000")
        self.assertEqual(result["formal_evidence_id"], "approved:18")
        self.assertEqual(self.registry(self.fingerprint)["fingerprint"], self.fingerprint)

    def test_read_only_lookup_does_not_modify_existing_database(self):
        self.insert()
        before = sha256(self.db_path.read_bytes()).hexdigest()
        self.registry(self.fingerprint)
        after = sha256(self.db_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)

    def test_missing_registry_does_not_create_database(self):
        missing = Path(self.temp_dir.name) / "missing.sqlite3"
        self.assertIsNone(ReadOnlyFormalApprovalRegistry(missing)(self.fingerprint))
        self.assertFalse(missing.exists())

    def test_valid_database_but_no_approval_is_reference_only(self):
        view = build_public_evidence_view(self.source, quote_for(self.source),
                                          approved_record_lookup=self.registry)
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIsNone(view["difference_twd"])

    def test_pending_rejected_revoked_states_are_denied(self):
        for state in ("pending", "rejected", "revoked"):
            with self.subTest(state=state):
                with sqlite3.connect(self.db_path) as db:
                    db.execute("DELETE FROM judun_formal_evidence_approvals_v1")
                self.insert(state=state)
                self.assertIsNone(self.registry(self.fingerprint))

    def test_revoked_at_always_denies_even_if_state_says_approved(self):
        self.insert(revoked_at="2026-10-20T03:00:00+00:00")
        self.assertIsNone(self.registry(self.fingerprint))

    def test_reject_malformed_fingerprint_without_sql_injection(self):
        self.insert()
        for value in (None, "", "A" * 64, "a" * 63, "a" * 65,
                      "' OR 1=1 --", self.fingerprint + ";DROP TABLE x", 20):
            with self.subTest(value=value):
                self.assertIsNone(self.registry(value))
        self.assertIsNotNone(self.registry(self.fingerprint))

    def test_source_changed_after_approval_is_denied(self):
        self.insert()
        edited = {**self.source, "spec": "其他施工規格"}
        view = build_public_evidence_view(
            edited, quote_for(edited), approved_record_lookup=self.registry)
        self.assertEqual(view["tier"], "REFERENCE_ONLY")
        self.assertIsNone(view["difference_twd"])

    def test_unapproved_table_schema_is_not_used_implicitly(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("DROP TABLE judun_formal_evidence_approvals_v1")
            db.execute("CREATE TABLE public_evidence (fingerprint TEXT, state TEXT)")
            db.execute("INSERT INTO public_evidence VALUES (?, 'approved')",
                       (self.fingerprint,))
        self.assertIsNone(self.registry(self.fingerprint))

    def test_bad_evidence_ids_rejected(self):
        for ident in ("", " ", "<script>", "item\nnext", "x" * 129):
            with self.subTest(ident=ident):
                with sqlite3.connect(self.db_path) as db:
                    db.execute("DELETE FROM judun_formal_evidence_approvals_v1")
                self.insert(evidence_id=ident)
                self.assertIsNone(self.registry(self.fingerprint))

    def test_missing_timezone_or_invalid_review_date_denied(self):
        for reviewed in ("not-a-timestamp", "2026-10-20T00:00:00", ""):
            with self.subTest(reviewed=reviewed):
                with sqlite3.connect(self.db_path) as db:
                    db.execute("DELETE FROM judun_formal_evidence_approvals_v1")
                self.insert(reviewed_at=reviewed)
                self.assertIsNone(self.registry(self.fingerprint))

    def test_approval_id_reuse_in_legacy_table_denied(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("DROP TABLE judun_formal_evidence_approvals_v1")
            db.execute(
                "CREATE TABLE judun_formal_evidence_approvals_v1 "
                "(fingerprint TEXT UNIQUE, evidence_id TEXT, approval_state TEXT, "
                "reviewed_at_utc TEXT, revoked_at_utc TEXT)"
            )
            for sha in (self.fingerprint, "a" * 64):
                db.execute(
                    "INSERT INTO judun_formal_evidence_approvals_v1 VALUES (?,?,?,?,?)",
                    (sha, "shared-id", "approved", "2026-10-20T00:00:00+00:00", None)
                )
        self.assertIsNone(self.registry(self.fingerprint))

    def test_future_dated_approval_is_not_yet_eligible(self):
        self.insert(reviewed_at="2099-01-01T00:00:00+00:00")
        self.assertIsNone(self.registry(self.fingerprint))

    def test_no_automatic_schema_migration(self):
        with sqlite3.connect(self.db_path) as db:
            db.execute("DROP TABLE judun_formal_evidence_approvals_v1")
        self.assertIsNone(self.registry(self.fingerprint))
        with sqlite3.connect(self.db_path) as db:
            present = db.execute(
                "SELECT name FROM sqlite_master WHERE name='judun_formal_evidence_approvals_v1'"
            ).fetchone()
        self.assertIsNone(present)


if __name__ == "__main__":
    unittest.main()
