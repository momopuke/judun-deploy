"""JUDUN release-archive retention planning, read-only and fail-closed.

Policy: preserve the active release and exactly one verified previous rollback
release; only *older release archives* can be considered for cleanup. This
tool NEVER deletes. Formal QA databases, snapshots, and customer evidence
backups are not interchangeable with application release archives and must
not be affected by this policy.

Inputs come from a trusted inventory of the existing VPS rollback directory.
No assumed VPS paths, destructive globbing, network calls or follow-symlinks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

ARTIFACT = re.compile(r"JUDUN-\d+\.\d+\.\d+-[A-Za-z0-9][A-Za-z0-9_-]{1,80}")
SHA256 = re.compile(r"[0-9a-f]{64}")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}")


def verify_release_files(root: Path, inventory: dict) -> dict:
    """Recompute actual archive bytes without following links or touching DBs.

    Never trusts metadata fields saying 'verified'. Only root-level, known
    release archive basenames are opened. An operator must supply the actual
    existing rollback archive directory, not a guessed filesystem path.
    """
    if root.is_symlink() or not root.is_dir():
        raise ValueError("RETENTION_BACKUP_ROOT_NOT_VERIFIED")
    if (not isinstance(inventory, dict)
            or inventory.get("schema") != "judun.release-backup-inventory.v1"
            or not isinstance(inventory.get("entries"), list)):
        raise ValueError("RETENTION_INVENTORY_SCHEMA_INVALID")
    if len(inventory["entries"]) > 10000:
        raise ValueError("RETENTION_INVENTORY_TOO_LARGE")
    copied = []
    for entry in inventory["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("RETENTION_ENTRY_INVALID")
        if entry.get("kind") != "release_rollback_archive":
            # Keep unknown/other backup kinds out of this workflow entirely.
            copied.append(dict(entry))
            continue
        name = entry.get("name")
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if (not isinstance(name, str) or not SAFE_NAME.fullmatch(name)
                or name.startswith(".") or ".." in name
                or not isinstance(digest, str) or not SHA256.fullmatch(digest)
                or type(size) is not int or size < 1):
            raise ValueError("RETENTION_RELEASE_ARCHIVE_METADATA_INVALID")
        target = root / name
        # O_NOFOLLOW and fstat prevent following an attacker-controlled
        # symlink or mistaking a directory/device/pipe for an archive.
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if hasattr(os, "O_NONBLOCK"):
            flags |= os.O_NONBLOCK
        try:
            fd = os.open(target, flags)
        except OSError as error:
            raise ValueError("RETENTION_RELEASE_ARCHIVE_UNREADABLE") from error
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_size != size:
                raise ValueError("RETENTION_RELEASE_ARCHIVE_NOT_REGULAR_OR_SIZE_DRIFT")
            hasher = hashlib.sha256()
            with os.fdopen(fd, "rb", closefd=False) as fh:
                while chunk := fh.read(1024 * 1024):
                    hasher.update(chunk)
            after = os.fstat(fd)
            if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
                    or hasher.hexdigest() != digest):
                raise ValueError("RETENTION_RELEASE_ARCHIVE_DIGEST_OR_METADATA_DRIFT")
        finally:
            os.close(fd)
        verified = dict(entry)
        verified["regular_file_verified"] = True
        verified["digest_verified"] = True
        copied.append(verified)
    return {**inventory, "entries": copied}


def plan(inventory: object, *, current_artifact: str, previous_artifact: str) -> dict:
    """Validate release backup metadata before proposing any old-archive cleanup.

    One previous rollback is mandatory. A current-release archive is optional,
    because the current release may only exist in its installed directory.
    """
    if (not isinstance(current_artifact, str) or not ARTIFACT.fullmatch(current_artifact)
            or not isinstance(previous_artifact, str)
            or not ARTIFACT.fullmatch(previous_artifact)
            or current_artifact == previous_artifact):
        raise ValueError("RETENTION_RELEASE_IDENTITIES_UNTRUSTED")
    # An arbitrary archive with a matching digest is not proof it is the
    # previous release. The rollback identity must be an older release;
    # same-version/different-build promotions require separate trusted
    # release-lineage attestation and are not eligible for automatic review.
    current_parts = tuple(map(int, current_artifact.split("-")[1].split(".")))
    previous_parts = tuple(map(int, previous_artifact.split("-")[1].split(".")))
    if previous_parts >= current_parts:
        raise ValueError("RETENTION_PREVIOUS_RELEASE_NOT_OLDER")
    if (not isinstance(inventory, dict)
            or inventory.get("schema") != "judun.release-backup-inventory.v1"
            or not isinstance(inventory.get("entries"), list)):
        raise ValueError("RETENTION_INVENTORY_SCHEMA_INVALID")
    entries = inventory["entries"]
    if len(entries) > 10000:
        raise ValueError("RETENTION_INVENTORY_TOO_LARGE")
    seen_artifacts = set()
    seen_names = set()
    keep, older = [], []
    unrelated = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("RETENTION_ENTRY_INVALID")
        # Source inventories may include formal-data or other backup entries.
        # We never even consider their deletion.
        if entry.get("kind") != "release_rollback_archive":
            unrelated += 1
            continue
        artifact = entry.get("artifact_id")
        name = entry.get("name")
        digest = entry.get("sha256")
        size = entry.get("size_bytes")
        if (not isinstance(artifact, str) or not ARTIFACT.fullmatch(artifact)
                or not isinstance(name, str) or not SAFE_NAME.fullmatch(name)
                or name.startswith(".") or ".." in name
                or not isinstance(digest, str) or not SHA256.fullmatch(digest)
                or type(size) is not int or size < 1
                or entry.get("regular_file_verified") is not True
                or entry.get("digest_verified") is not True
                or artifact in seen_artifacts or name in seen_names):
            raise ValueError("RETENTION_RELEASE_ARCHIVE_NOT_INDEPENDENTLY_VERIFIED")
        seen_artifacts.add(artifact)
        seen_names.add(name)
        summary = {"artifact_id": artifact, "archive_name": name}
        if artifact in (current_artifact, previous_artifact):
            keep.append(summary)
        else:
            older.append(summary)
    if previous_artifact not in seen_artifacts:
        raise ValueError("RETENTION_VERIFIED_PREVIOUS_ROLLBACK_REQUIRED")
    return {
        "schema": "judun.p3.release-retention-plan.v1",
        "decision": "REVIEW_ONLY_NOT_EXECUTED",
        "current_artifact": current_artifact,
        "previous_artifact": previous_artifact,
        "retain_release_archives": sorted(keep, key=lambda e: e["artifact_id"]),
        "older_release_archives_for_manual_review": sorted(older, key=lambda e: e["artifact_id"]),
        "unrelated_or_formal_data_entries_untouched": unrelated,
        "releases_auto_deleted": 0,
        "formal_backup_policy_changed": False,
        "delete_command_generated": False,
        "vps_modified": False,
        "next_step": "VERIFY_EXACT_ARCHIVE_ROOT_AND_RESTORE_TEST_BEFORE_ANY_CLEANUP",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--current-artifact", required=True)
    parser.add_argument("--previous-artifact", required=True)
    args = parser.parse_args()
    try:
        if args.inventory.is_symlink() or not args.inventory.is_file():
            raise ValueError("RETENTION_INVENTORY_NOT_REGULAR_FILE")
        if args.inventory.stat().st_size > 1_000_000:
            raise ValueError("RETENTION_INVENTORY_TOO_LARGE")
        inventory = json.loads(args.inventory.read_text("utf-8"))
        inventory = verify_release_files(args.backup_root, inventory)
        result = plan(inventory, current_artifact=args.current_artifact,
                      previous_artifact=args.previous_artifact)
        print("P3_RELEASE_RETENTION_PLAN", json.dumps(result, sort_keys=True))
        return 0
    except (OSError, UnicodeError, ValueError, TypeError):
        # No arbitrary errors, paths, customer data, backup contents or tokens.
        print("P3_RELEASE_RETENTION_BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
