"""Offline scope audit for decrypted JUDUN source tarballs.

Never treat an incremental CMS delivery as an authoritative copy of live app.py.
This module does not decrypt, transmit, execute scripts, or touch production.
"""
from __future__ import annotations

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile

MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_COUNT = 3000
MAX_EXTRACTED_TOTAL = 256 * 1024 * 1024
MAX_SCRIPT_BYTES = 256 * 1024
VERSION = re.compile(r"^1\.2\.\d{2,3}$")
APP_LOCATIONS = frozenset(("app.py", "runtime/app.py", "system_files/app.py"))
PATCH_PREFIXES = ("apply_", "restore_")


def fail(code: str) -> None:
    raise ValueError("SOURCE_SCOPE_" + code)


def path_ok(name: str) -> bool:
    return (bool(name) and name == PurePosixPath(name).as_posix()
            and not name.startswith("/")
            and "\\" not in name and "\0" not in name
            and not any(c in ("", ".", "..") for c in name.split("/"))
            and all(ord(c) >= 32 for c in name))


def patch_identity(source: bytes) -> dict:
    if len(source) > MAX_SCRIPT_BYTES:
        fail("PATCH_SCRIPT_TOO_LARGE")
    try:
        code = ast.parse(source.decode("utf-8"))
    except (UnicodeError, SyntaxError):
        fail("INVALID_PATCH_PROGRAM")
    assignments = {}
    for statement in code.body:
        if (isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
                and statement.targets[0].id in {"BASE", "VERSION", "SIGNATURE"}):
            field = statement.targets[0].id
            if field in assignments:
                fail("DUPLICATE_PATCH_METADATA")
            if not isinstance(statement.value, ast.Constant) or not isinstance(statement.value.value, str):
                fail("INVALID_PATCH_METADATA")
            assignments[field] = statement.value.value
    return assignments


def inspect_source_archive(archive: Path, *,
                           expected_version: str | None = None,
                           required_patch: str | None = None) -> dict:
    archive = Path(archive)
    if (not archive.is_file() or archive.is_symlink()
            or archive.stat().st_size > MAX_ARCHIVE_BYTES):
        fail("MISSING_OR_TOO_LARGE")
    try:
        with tarfile.open(archive, "r:*") as t:
            members = t.getmembers()
            if not 1 <= len(members) <= MAX_MEMBER_COUNT:
                fail("INVALID_MEMBER_COUNT")
            seen = set()
            total = 0
            for m in members:
                if not path_ok(m.name) or m.name in seen:
                    fail("UNSAFE_OR_DUPLICATE_MEMBER")
                if not (m.isfile() or m.isdir()):
                    fail("LINK_OR_SPECIAL_MEMBER")
                seen.add(m.name)
                if m.isfile():
                    total += m.size
                    if total > MAX_EXTRACTED_TOTAL:
                        fail("EXPANDED_SIZE_LIMIT")
            present_app = sorted(APP_LOCATIONS.intersection(seen))
            if len(present_app) > 1:
                fail("AMBIGUOUS_MAIN_APP")
            candidates = sorted(n for n in seen if n.endswith(".py") and
                                PurePosixPath(n).name.startswith(PATCH_PREFIXES))
            if required_patch and required_patch not in candidates:
                fail("REQUIRED_PATCH_NOT_IN_ARCHIVE")
            detected = []
            for name in candidates:
                entry = t.getmember(name)
                if entry.size > MAX_SCRIPT_BYTES:
                    continue
                source = t.extractfile(entry)
                if source is None:
                    fail("UNREADABLE_PATCH")
                identities = patch_identity(source.read(MAX_SCRIPT_BYTES + 1))
                if "VERSION" in identities:
                    detected.append((name, identities))
            versions = {v["VERSION"] for _, v in detected}
            if len(versions) > 1:
                fail("CONFLICTING_PATCH_VERSION")
            declared = next(iter(versions)) if versions else None
            if expected_version is not None:
                if not VERSION.fullmatch(expected_version):
                    fail("INVALID_REQUESTED_VERSION")
                if declared is not None and declared != expected_version:
                    fail("PATCH_VERSION_MISMATCH")
                if required_patch and declared is None:
                    fail("PATCH_VERSION_MISSING")
            bases = sorted({v["BASE"] for _, v in detected if "BASE" in v})
            if len(bases) > 1:
                fail("CONFLICTING_BASE_ARTIFACT")
            return {
                "status": "SCOPE_CLASSIFIED_OFFLINE",
                "scope": "APP_PRESENT_UNVERIFIED" if present_app else "DELTA_ONLY_NO_APP_PY",
                "total_archive_files": sum(m.isfile() for m in members),
                "app_member_present": bool(present_app),
                "declared_version": declared,
                "declared_base_artifact": bases[0] if bases else None,
                "original_runtime_source_verified": False,
                "live_deployed": False,
            }
    except (tarfile.TarError, OSError, EOFError):
        fail("UNREADABLE_ARCHIVE")


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify offline JUDUN CMS plaintext without executing code")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--expected-version")
    parser.add_argument("--required-patch")
    args = parser.parse_args()
    try:
        result = inspect_source_archive(
            args.archive, expected_version=args.expected_version,
            required_patch=args.required_patch,
        )
    except ValueError as e:
        # Error codes only; no source content, file paths or secrets.
        print("P3_SOURCE_SCOPE_BLOCKED", str(e).split(" ", 1)[0][:90])
        return 2
    print("P3_SOURCE_SCOPE", json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
