"""Read-only acceptance for the ORIGINAL HTTPS v3 application/zip receiver route.

The historical Windows BUILD_PAYLOAD.ps1 creates a ZIP with RELEASE.json,
RUNTIME_RELEASE_LOCK.json, source files, and system_files/DEPLOY_MANIFEST.json.
This audits that contract and does NOT call the receiver or use any credentials.

It is intentionally distinct from production_delta_patch.py, which describes
a different GitHub CMS/Ed25519 pull-agent route. Never POST a CMS archive to
the HTTPS v3 receiver, or treat HTTP 200 health as deployment authorization.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from zipfile import ZipFile, BadZipFile

from production_delta_patch import computed_tree_sha

MANIFEST_PATH = "system_files/DEPLOY_MANIFEST.json"
REQUIRED = {MANIFEST_PATH, "RELEASE.json", "RUNTIME_RELEASE_LOCK.json"}
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_COUNT = 3000
MAX_JSON = 1024 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ARTIFACT = re.compile(r"^JUDUN-[A-Za-z0-9._-]{1,120}$")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(code: str):
    raise ValueError("HTTPS_V3_" + code)


def safe_path(path: object) -> str:
    if (not isinstance(path, str) or not path or "\0" in path or "\\" in path
            or path.startswith("/") or path.endswith("/")
            or PurePosixPath(path).as_posix() != path
            or any(x in ("", ".", "..") for x in path.split("/"))):
        fail("UNSAFE_OR_NONCANONICAL_ZIP_PATH")
    return path


def read_json(z: ZipFile, name: str) -> dict:
    if z.getinfo(name).file_size > MAX_JSON:
        fail("OVERSIZED_CONTROL_JSON")
    try:
        data = json.loads(z.read(name))
    except (UnicodeError, ValueError):
        fail("INVALID_CONTROL_JSON")
    if not isinstance(data, dict):
        fail("INVALID_CONTROL_SHAPE")
    return data


def file_fingerprint(z: ZipFile, path: str) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with z.open(path) as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            size += len(block)
            if size > MAX_UNCOMPRESSED:
                fail("FILE_TOO_LARGE")
            hasher.update(block)
    return size, hasher.hexdigest()


def validate_rows(rows: object) -> dict[str, dict]:
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_COUNT:
        fail("MALFORMED_MANIFEST_FILES")
    index = {}
    for row in rows:
        if not isinstance(row, dict):
            fail("MALFORMED_MANIFEST_FILES")
        name = safe_path(row.get("path"))
        if name in index or name == MANIFEST_PATH:
            fail("DUPLICATED_OR_SELF_REFERENTIAL_MANIFEST")
        if (not type(row.get("size")) is int or row["size"] < 0
                or not isinstance(row.get("sha256"), str)
                or not HEX64.fullmatch(row["sha256"])):
            fail("MALFORMED_MANIFEST_FILE_IDENTITY")
        index[name] = row
    return index


def inspect_bundle(path: Path, *, expected_base_artifact: str,
                   live_artifact: str, expected_target_artifact: str,
                   expected_version: str, live_formal_sha256: str,
                   live_mismatches: int = 0) -> dict:
    """No remote calls. Requires independent LIVE identity and evidence digest.

    This validates only the file package, NOT v3 token authentication, server
    backup, rollback, or payment/PDF end-to-end behavior.
    """
    if (not ARTIFACT.fullmatch(expected_base_artifact)
            or live_artifact != expected_base_artifact
            or not ARTIFACT.fullmatch(expected_target_artifact)
            or expected_target_artifact == live_artifact
            or not re.fullmatch(r"\d+\.\d+\.\d+", expected_version)
            or not HEX64.fullmatch(live_formal_sha256)
            or type(live_mismatches) is not int or live_mismatches != 0):
        fail("LIVE_BASE_OR_FORMAL_DIGEST_NOT_VERIFIED")
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARCHIVE:
        fail("MISSING_OR_OVERSIZED_LOCAL_PACKAGE")
    try:
        with ZipFile(path) as z:
            infos = z.infolist()
            if not 3 <= len(infos) <= MAX_COUNT:
                fail("UNSAFE_ENTRY_COUNT")
            names = []
            total = 0
            for info in infos:
                name = safe_path(info.filename)
                if info.is_dir() or stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    fail("UNSAFE_ZIP_ENTRY_TYPE")
                total += info.file_size
                if total > MAX_UNCOMPRESSED:
                    fail("UNCOMPRESSED_SIZE_BOUND_EXCEEDED")
                names.append(name)
            if len(set(names)) != len(names) or not REQUIRED.issubset(names):
                fail("MISSING_REQUIRED_OR_DUPLICATE_ENTRY")
            manifest = read_json(z, MANIFEST_PATH)
            release = read_json(z, "RELEASE.json")
            lock = read_json(z, "RUNTIME_RELEASE_LOCK.json")
            if manifest.get("schema") != "judun.deploy-manifest.v1":
                fail("UNRECOGNIZED_MANIFEST_SCHEMA")
            for field, wanted in (
                ("artifact_id", expected_target_artifact),
                ("version", expected_version),
            ):
                if manifest.get(field) != wanted or release.get(field) != wanted:
                    fail("PACKAGE_TARGET_IDENTITY_MISMATCH")
            for field in ("build_instance_id", "build_signature", "display_version"):
                value = manifest.get(field)
                if not isinstance(value, str) or not value or release.get(field) != value:
                    fail("RELEASE_MANIFEST_IDENTITY_MISMATCH")
            for field in ("artifact_id", "version", "build_signature", "build_instance_id"):
                if lock.get(field) != manifest.get(field):
                    fail("RUNTIME_LOCK_IDENTITY_MISMATCH")
            if (manifest.get("formal_evidence_sha256") != live_formal_sha256
                    or lock.get("formal_evidence_sha256") != live_formal_sha256):
                fail("FORMAL_DATA_FINGERPRINT_DRIFT")
            policy = manifest.get("deployment_policy")
            if not isinstance(policy, dict) or any(
                policy.get(flag) is not True for flag in (
                    "formal_seed_write_locked",
                    "persistent_formal_db_additive_only",
                    "post_deploy_deep_verification_required",
                )
            ) or policy.get("formal_backup_keep_versions") != 3:
                fail("BACKUP_OR_FORMAL_DATA_POLICY_MISMATCH")
            rows = validate_rows(manifest.get("files"))
            if set(rows) != set(names) - {MANIFEST_PATH}:
                fail("UNTRACKED_OR_MISSING_PACKAGE_MEMBER")
            if computed_tree_sha(list(rows.values())) != manifest.get("source_tree_sha256"):
                fail("AUTHORITATIVE_TREE_DIGEST_MISMATCH")
            for name, row in rows.items():
                actual_size, actual_hash = file_fingerprint(z, name)
                if actual_size != row["size"] or actual_hash != row["sha256"]:
                    fail("UNREVIEWED_PACKAGE_FILE_DRIFT")
            # Original RUNTIME_RELEASE_LOCK lists installed runtime files and
            # their source_path within the ZIP; verify both identities and the
            # separate runtime_tree_sha256 from the historic builder.
            runtime_rows = lock.get("files")
            if not isinstance(runtime_rows, list) or not runtime_rows:
                fail("MISSING_LOCKED_RUNTIME_FILES")
            runtime_identity = []
            seen_runtime = set()
            for entry in runtime_rows:
                if not isinstance(entry, dict):
                    fail("MALFORMED_RUNTIME_LOCK")
                installed_path = safe_path(entry.get("path"))
                source_path = safe_path(entry.get("source_path"))
                if installed_path in seen_runtime or source_path not in rows:
                    fail("RUNTIME_LOCK_SOURCE_MISMATCH")
                seen_runtime.add(installed_path)
                source = rows[source_path]
                if entry.get("size") != source["size"] or entry.get("sha256") != source["sha256"]:
                    fail("RUNTIME_LOCK_FILE_DRIFT")
                runtime_identity.append({
                    "path": installed_path, "size": source["size"],
                    "sha256": source["sha256"],
                })
            if computed_tree_sha(runtime_identity) != lock.get("runtime_tree_sha256"):
                fail("RUNTIME_TREE_DIGEST_MISMATCH")
            return {
                "status": "BUNDLE_VALIDATED_OFFLINE_ONLY",
                "package_artifact": manifest["artifact_id"],
                "expected_base_artifact": expected_base_artifact,
                "build_instance_id": manifest["build_instance_id"],
                "managed_package_files": len(rows),
                "locked_runtime_files": len(runtime_identity),
                "preserved_formal_sha256_verified": True,
                "receiver": "HTTPS_v3_application_zip",
                "receiver_authentication_verified": False,
                "actual_vps_deployment": False,
                "live_payment_or_pdf_e2e_verified": False,
            }
    except (BadZipFile, OSError, EOFError, RuntimeError):
        fail("UNREADABLE_OR_INVALID_ZIP")
