"""Read-only candidate bridge to a server-owned formal evidence approval registry.

No schema migrations, inserts, updates, deletes, network calls, or live
application changes are performed here. This proposed table is NOT asserted to
exist in current Judun production. A genuine QA-approved source snapshot must
have been recorded by the actual formal ingestion pipeline before use.

Never accept database_path, registry instance, or its returned approval dict
from public HTTP parameters, reports, uploads, or browser JS.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
import re
import sqlite3

# Fixed and versioned contract to prevent accidentally treating the older
# public_evidence.db as a formal approval registry.
APPROVAL_TABLE = "judun_formal_evidence_approvals_v1"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_EVIDENCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")

# This string is only a *reviewed schema proposal*. No installation happens.
REQUIRED_SCHEMA = """
CREATE TABLE judun_formal_evidence_approvals_v1 (
    fingerprint TEXT NOT NULL UNIQUE,
    evidence_id TEXT NOT NULL UNIQUE,
    approval_state TEXT NOT NULL CHECK(approval_state IN ('approved','pending','rejected','revoked')),
    reviewed_at_utc TEXT NOT NULL,
    revoked_at_utc TEXT
);
"""


class ReadOnlyFormalApprovalRegistry:
    """Fail-closed lookup used only by the trusted report server.

    The database path MUST originate from server-side trusted configuration.
    The connector is deliberately incompatible with unknown legacy schemas;
    absence of the versioned table results in no approval.
    """

    def __init__(self, database_path: str | Path):
        self._path = Path(database_path).expanduser().absolute()

    def __call__(self, source_fingerprint: str) -> dict | None:
        return self.lookup_exact_snapshot(source_fingerprint)

    def lookup_exact_snapshot(self, source_fingerprint: str) -> dict | None:
        if not isinstance(source_fingerprint, str) or _DIGEST.fullmatch(source_fingerprint) is None:
            return None
        if not self._path.is_file():
            return None
        try:
            # URI mode=ro enforces read-only even when the service normally has
            # filesystem write permission. SQLite will not create a missing DB.
            with closing(sqlite3.connect(self._path.as_uri() + "?mode=ro", uri=True, timeout=1.0)) as db:
                db.execute("PRAGMA query_only = ON")
                rows = db.execute(
                    "SELECT evidence_id, fingerprint, approval_state, "
                    "reviewed_at_utc, revoked_at_utc "
                    "FROM " + APPROVAL_TABLE + " WHERE fingerprint = ? LIMIT 2",
                    (source_fingerprint,),
                ).fetchall()
                if len(rows) != 1:
                    return None
                # An approval ID must represent exactly one reviewed snapshot.
                # Reject a legacy or malformed table reusing the same ID.
                owner_rows = db.execute(
                    "SELECT fingerprint FROM " + APPROVAL_TABLE +
                    " WHERE evidence_id = ? LIMIT 2",
                    (rows[0][0],),
                ).fetchall()
                if len(owner_rows) != 1 or owner_rows[0][0] != source_fingerprint:
                    return None
        except (sqlite3.Error, OSError, ValueError):
            return None
        if len(rows) != 1:
            return None
        evidence_id, fingerprint, state, reviewed_at, revoked_at = rows[0]
        if (fingerprint != source_fingerprint or state != "approved"
                or revoked_at is not None
                or not isinstance(evidence_id, str)
                or _EVIDENCE_ID.fullmatch(evidence_id) is None
                or not isinstance(reviewed_at, str)):
            return None
        try:
            when = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if when.tzinfo is None or when.utcoffset() is None:
                return None
            # A future-dated approval cannot yet be relied on. Allow only
            # a small clock-skew tolerance for independently managed servers.
            if when.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
                return None
        except ValueError:
            return None
        return {
            "state": "approved",
            "fingerprint": source_fingerprint,
            "evidence_id": evidence_id,
        }
