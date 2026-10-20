"""Read-only acceptance for the ORIGINAL HTTPS v3 application/zip receiver route.

The historical Windows BUILD_PAYLOAD.ps1 creates a ZIP with RELEASE.json,
RUNTIME_RELEASE_LOCK.json, source files, and system_files/DEPLOY_MANIFEST.json.
This audits that contract and does NOT call the receiver or use any credentials.

It is intentionally distinct from production_delta_patch.py, which describes
a different GitHub CMS/Ed25519 pull-agent route. Never POST a CMS archive to
the HTTPS v3 receiver, or treat HTTP 200 health as deployment authorization.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from io import BytesIO
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
MAX_EMBEDDED_BUNDLE = 100 * 1024 * 1024
MAX_EMBEDDED_SCRIPT = 180 * 1024 * 1024
REQUIRED_EMBEDDED_FILES = frozenset((
    "data_expansion_web.py", "deployment_integrity.py", "evidence_store.py",
    "run_data_expansion.sh", "public_quote_evidence.json",
    "data_expansion_controller/controller.py",
    "data_expansion_controller/source_registry.json",
    "data_expansion_controller/discovery_queries.json",
    "data_expansion_controller/README.md",
))
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



def audit_embedded_runtime(z: ZipFile, lock: dict, runtime_identity: list) -> dict:
    """Match R3.3 BUILD_PAYLOAD.ps1's embedded ZIP and manifest evidence."""
    script_path = "system_files/deploy_paid_test.sh"
    try:
        entry = z.getinfo(script_path)
    except KeyError:
        fail("MISSING_EMBEDDED_DEPLOY_SCRIPT")
    if entry.file_size > MAX_EMBEDDED_SCRIPT:
        fail("EMBEDDED_SCRIPT_TOO_LARGE")
    script = z.read(script_path)
    if (b"__JUDUN_RUNTIME_ZIP_B64__" in script or
            b"R3.3 embedded data-expansion runtime" not in script):
        fail("MISSING_RUNTIME_EMBED_MARKER")
    start_tags = (b"<<'JUDUN_RUNTIME_B64'\n", b"<<'JUDUN_RUNTIME_B64'\r\n")
    starts = [(script.find(token), len(token)) for token in start_tags]
    starts = [(pos, width) for pos, width in starts if pos >= 0]
    if len(starts) != 1:
        fail("MISSING_OR_AMBIGUOUS_RUNTIME_BASE64")
    start_pos, start_width = starts[0]
    start = start_pos + start_width
    # The LF is present in both LF and CRLF; strip the optional CR below.
    end_token = b"\nJUDUN_RUNTIME_B64"
    end = script.find(end_token, start)
    if (end < 0 or script.find(end_token, end + len(end_token)) >= 0
            or any(script.find(token, start) >= 0 for token in start_tags)):
        fail("AMBIGUOUS_RUNTIME_BASE64")
    encoded = script[start:end].replace(b"\r", b"").replace(b"\n", b"")
    if len(encoded) > (MAX_EMBEDDED_BUNDLE * 4 // 3 + 8):
        fail("EMBEDDED_BUNDLE_TOO_LARGE")
    try:
        blob = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        fail("INVALID_RUNTIME_BASE64")
    if len(blob) > MAX_EMBEDDED_BUNDLE:
        fail("EMBEDDED_BUNDLE_TOO_LARGE")
    if (type(lock.get("runtime_bundle_bytes")) is not int
            or len(blob) != lock["runtime_bundle_bytes"]
            or digest(blob) != lock.get("runtime_bundle_sha256")):
        fail("EMBEDDED_RUNTIME_LOCK_DIGEST_MISMATCH")
    try:
        with ZipFile(BytesIO(blob)) as inner:
            metadata = inner.infolist()
            if len(metadata) > MAX_COUNT or sum(e.file_size for e in metadata) > MAX_UNCOMPRESSED:
                fail("EMBEDDED_ZIP_RESOURCE_LIMIT")
            names = [safe_path(info.filename) for info in metadata]
            if any(e.is_dir() or stat.S_IFMT(e.external_attr >> 16) == stat.S_IFLNK for e in metadata):
                fail("UNSAFE_EMBEDDED_ENTRY")
            if (len(names) != len(set(names))
                    or not REQUIRED_EMBEDDED_FILES.issubset(names)
                    or "DEPLOY_MANIFEST.json" not in names):
                fail("INCOMPLETE_EMBEDDED_RUNTIME")
            manifest = read_json(inner, "DEPLOY_MANIFEST.json")
            for field in ("artifact_id", "version", "build_signature", "build_instance_id"):
                if manifest.get(field) != lock.get(field):
                    fail("EMBEDDED_RUNTIME_IDENTITY_MISMATCH")
            if manifest.get("source_tree_sha256") != lock.get("runtime_tree_sha256"):
                fail("EMBEDDED_TREE_LOCK_MISMATCH")
            inner_rows = validate_rows(manifest.get("files"))
            if (len(inner_rows) != len(runtime_identity)
                    or computed_tree_sha(list(inner_rows.values())) != lock["runtime_tree_sha256"]):
                fail("EMBEDDED_FILE_TABLE_MISMATCH")
            for entry in runtime_identity:
                target = inner_rows.get(entry["path"])
                if target is None or target["size"] != entry["size"] or target["sha256"] != entry["sha256"]:
                    fail("EMBEDDED_LOCK_FILE_IDENTITY_MISMATCH")
                if entry["path"] in names:
                    n, checksum = file_fingerprint(inner, entry["path"])
                    if n != entry["size"] or checksum != entry["sha256"]:
                        fail("EMBEDDED_FILE_BYTES_MISMATCH")
            return {"embedded_runtime_files": len(inner_rows),
                    "embedded_runtime_sha256_verified": True}
    except (BadZipFile, OSError, EOFError, RuntimeError):
        fail("UNREADABLE_EMBEDDED_ZIP")


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
            embedded = audit_embedded_runtime(z, lock, runtime_identity)
            return {
                "status": "BUNDLE_VALIDATED_OFFLINE_ONLY",
                "package_artifact": manifest["artifact_id"],
                "expected_base_artifact": expected_base_artifact,
                "build_instance_id": manifest["build_instance_id"],
                "managed_package_files": len(rows),
                "locked_runtime_files": len(runtime_identity),
                **embedded,
                "preserved_formal_sha256_verified": True,
                "receiver": "HTTPS_v3_application_zip",
                "receiver_authentication_verified": False,
                "actual_vps_deployment": False,
                "live_payment_or_pdf_e2e_verified": False,
            }
    except (BadZipFile, OSError, EOFError, RuntimeError):
        fail("UNREADABLE_OR_INVALID_ZIP")
