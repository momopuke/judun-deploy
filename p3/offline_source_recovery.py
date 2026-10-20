"""Offline v1.2.114 encrypted-source verification and optional PRIVATE app.py staging.

No network, no VPS calls, no GitHub writes, no deployment.  Uses the original
historical recipient private key only inside a 0700 temporary directory.
A ciphertext SHA match plus decryption is NOT proof of current live source:
the recovered app identity must be compared independently to live release.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tarfile
import tempfile
from zipfile import ZipFile, is_zipfile

MAX_CIPHERTEXT = 32 * 1024 * 1024
MAX_PLAINTEXT = 128 * 1024 * 1024
MAX_APP = 16 * 1024 * 1024
MAX_FILES = 3000
HIST_KEY = "judun81/_SYSTEM/payload_decrypt_private.pem"
HIST_CERT = "judun81/_SYSTEM/payload_encrypt_cert.pem"
DEFAULT_ARCHIVE_APP_PATHS = ("runtime/app.py", "system_files/app.py", "app.py")


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def deny(reason: str):
    raise ValueError("JUDUN_RECOVERY_" + reason)


def assert_safe_member(name: str):
    if (not name or "\0" in name or "\\" in name or name.startswith("/")
            or ".." in PurePosixPath(name).parts
            or PurePosixPath(name).as_posix() != name):
        deny("UNSAFE_ARCHIVE_MEMBER")


def get_ciphertext(encoded: Path, attestation: dict) -> bytes:
    if encoded.stat().st_size > MAX_CIPHERTEXT * 2:
        deny("ENCRYPTED_ASSET_TOO_LARGE")
    text = encoded.read_bytes()
    try:
        data = base64.b64decode(b"".join(text.split()), validate=True)
    except (ValueError, binascii.Error):
        deny("INVALID_CMS_BASE64")
    if len(data) > MAX_CIPHERTEXT or not data:
        deny("INVALID_CIPHERTEXT_SIZE")
    if sha(data) != attestation.get("encrypted_source_sha256"):
        deny("CIPHERTEXT_SHA256_MISMATCH")
    return data


def invoke_openssl(args: list[str]) -> bytes:
    try:
        process = subprocess.run(
            ["openssl", *args], capture_output=True, timeout=40, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        deny("OPENSSL_UNAVAILABLE")
    if process.returncode != 0:
        # Never echo openssl stderr: it can contain paths or secret diagnostics.
        deny("OPENSSL_VERIFICATION_OR_DECRYPTION_FAILED")
    return process.stdout


def inspect_plaintext(plain: Path, version: str) -> tuple[bytes, dict]:
    """Extract only a single checked app.py into memory; never unpack everything."""
    size = plain.stat().st_size
    if size <= 0 or size > MAX_PLAINTEXT:
        deny("DECRYPTED_SOURCE_SIZE_INVALID")
    choices: dict[str, bytes] = {}
    if tarfile.is_tarfile(plain):
        with tarfile.open(plain, "r:*") as tf:
            members = tf.getmembers()
            if len(members) > MAX_FILES or sum(m.size for m in members) > MAX_PLAINTEXT:
                deny("DECRYPTED_ARCHIVE_RESOURCE_LIMIT")
            for m in members:
                assert_safe_member(m.name)
                if not (m.isfile() or m.isdir()):
                    deny("DECRYPTED_ARCHIVE_SPECIAL_MEMBER")
                if m.isfile() and m.name in DEFAULT_ARCHIVE_APP_PATHS:
                    if m.size > MAX_APP:
                        deny("OVERSIZED_SOURCE_APP")
                    stream = tf.extractfile(m)
                    if stream is None:
                        deny("UNREADABLE_SOURCE_APP")
                    choices[m.name] = stream.read(MAX_APP + 1)
    elif is_zipfile(plain):
        with ZipFile(plain) as z:
            members = z.infolist()
            if len(members) > MAX_FILES or sum(m.file_size for m in members) > MAX_PLAINTEXT:
                deny("DECRYPTED_ARCHIVE_RESOURCE_LIMIT")
            for m in members:
                assert_safe_member(m.filename.rstrip("/"))
                if stat.S_IFMT(m.external_attr >> 16) == stat.S_IFLNK:
                    deny("DECRYPTED_ARCHIVE_SPECIAL_MEMBER")
                if m.filename in DEFAULT_ARCHIVE_APP_PATHS:
                    if m.file_size > MAX_APP:
                        deny("OVERSIZED_SOURCE_APP")
                    choices[m.filename] = z.read(m.filename)
    else:
        raw = plain.read_bytes()
        if len(raw) <= MAX_APP:
            choices["app.py"] = raw
    if len(choices) != 1:
        deny("EXPECTED_ONE_AUTHENTIC_APP")
    app_name, app = next(iter(choices.items()))
    if (len(app) > MAX_APP or
            re.search(rb'(?m)^APP_VERSION\s*=\s*["\x27]' + version.encode() + rb'["\x27]\s*$', app) is None):
        deny("APP_RELEASE_VERSION_MISMATCH")
    try:
        compile(app.decode("utf-8"), "<recovered-JUDUN-app>", "exec")
    except (UnicodeError, SyntaxError, ValueError):
        deny("INVALID_APP_PYTHON")
    return app, {
        "found_member": app_name,
        "app_sha256": sha(app),
        "app_bytes": len(app),
        "version": version,
        "attested_ciphertext_only": True,
        "recovered_app_matches_live_authoritative_sha": "NOT_VERIFIED",
    }



def verify_live_app_tree(app: bytes, manifest: dict, live_source_tree_sha256: str) -> bool:
    """Require a full trusted manifest matching independently published tree."""
    from production_delta_patch import computed_tree_sha
    if (manifest.get("schema") != "judun.deploy-manifest.v1"
            or manifest.get("artifact_id") != "JUDUN-1.2.114-AA38F0567A4D"
            or manifest.get("version") != "1.2.114"):
        deny("INDEPENDENT_MANIFEST_IDENTITY_MISMATCH")
    records = manifest.get("files")
    if not isinstance(records, list) or len(records) < 79:
        deny("INCOMPLETE_INDEPENDENT_MANIFEST")
    paths = [x.get("path") for x in records if isinstance(x, dict)]
    if len(paths) != len(records) or len(paths) != len(set(paths)):
        deny("INVALID_INDEPENDENT_MANIFEST_FILES")
    if (not isinstance(live_source_tree_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", live_source_tree_sha256)
            or computed_tree_sha(records) != live_source_tree_sha256
            or manifest.get("source_tree_sha256") != live_source_tree_sha256):
        deny("INDEPENDENT_SOURCE_TREE_DRIFT")
    matches = [x for x in records if x.get("path") in
               ("app.py", "system_files/app.py", "runtime/app.py")]
    if len(matches) != 1:
        deny("INDEPENDENT_APP_ENTRY_NOT_UNIQUE")
    row = matches[0]
    if row.get("size") != len(app) or row.get("sha256") != sha(app):
        deny("APP_DOES_NOT_MATCH_LIVE_TREE")
    return True


def recover(encoded: Path, verification: Path, historical_zip: Path,
            *, out_private: Path | None = None,
            trusted_manifest: Path | None = None,
            public_tree_sha256: str | None = None) -> dict:
    record = json.loads(verification.read_text("utf-8"))
    if record.get("version") != "1.2.114" or record.get("artifact_id") != "JUDUN-1.2.114-AA38F0567A4D":
        deny("UNEXPECTED_SOURCE_ATTESTATION")
    blob = get_ciphertext(encoded, record)
    with tempfile.TemporaryDirectory(prefix="judun-offline-source-") as d:
        base = Path(d)
        base.chmod(0o700)
        key, cert, cipher, plain = (base / n for n in
                                    ("recipient.pem", "cert.pem", "cipher.cms", "decrypted"))
        with ZipFile(historical_zip) as z:
            k = z.read(HIST_KEY)
            c = z.read(HIST_CERT)
        key.write_bytes(k)
        key.chmod(0o600)
        cert.write_bytes(c)
        cipher.write_bytes(blob)
        priv_pub = invoke_openssl(["pkey", "-in", str(key), "-pubout", "-outform", "DER"])
        cert_pem = invoke_openssl(["x509", "-in", str(cert), "-pubkey", "-noout"])
        cert_pub_file = base / "public.pem"
        cert_pub_file.write_bytes(cert_pem)
        cert_pub = invoke_openssl(["pkey", "-pubin", "-in", str(cert_pub_file),
                                   "-pubout", "-outform", "DER"])
        if priv_pub != cert_pub:
            deny("ENCRYPTION_CERT_PRIVATE_KEY_MISMATCH")
        invoke_openssl(["cms", "-decrypt", "-inform", "DER", "-in", str(cipher),
                        "-recip", str(cert), "-inkey", str(key), "-out", str(plain)])
        app, report = inspect_plaintext(plain, record["version"])
        if (trusted_manifest is None) != (public_tree_sha256 is None):
            deny("MANIFEST_AND_TREE_REQUIRED_TOGETHER")
        if trusted_manifest is not None:
            manifest = json.loads(trusted_manifest.read_text("utf-8"))
            verify_live_app_tree(app, manifest, public_tree_sha256)
            report["recovered_app_matches_live_authoritative_sha"] = "VERIFIED_VIA_INDEPENDENT_LIVE_TREE"
        report["ciphertext_sha256_verified"] = True
        report["history_key_certificate_match"] = True
        report["vps_modified"] = False
        report["deployed"] = False
        if out_private is not None:
            if out_private.is_symlink() or out_private.exists():
                deny("REFUSE_OVERWRITE_PRIVATE_STAGING")
            path = out_private.resolve()
            repo_root = Path(__file__).resolve().parent.parent
            if path.is_relative_to(repo_root) or ".git" in out_private.parts:
                deny("REFUSE_GIT_WORKTREE_OUTPUT")
            # The caller must choose a pre-existing private directory,
            # outside any shared/Git-backed workspace.
            parent = path.parent
            if not parent.is_dir() or (parent.stat().st_mode & 0o077):
                deny("PRIVATE_STAGING_DIR_PERMISSIONS")
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(app)
                stream.flush()
                os.fsync(stream.fileno())
            report["staged_to_private_destination"] = True
        else:
            report["staged_to_private_destination"] = False
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore encrypted JUDUN source offline (NEVER deploy).")
    parser.add_argument("--encrypted", type=Path, required=True)
    parser.add_argument("--verification", type=Path, required=True)
    parser.add_argument("--historical-zip", type=Path, required=True)
    parser.add_argument("--out-private", type=Path)
    parser.add_argument("--trusted-manifest", type=Path)
    parser.add_argument("--public-tree-sha256")
    args = parser.parse_args()
    try:
        report = recover(args.encrypted, args.verification, args.historical_zip,
                         out_private=args.out_private)
        print("JUDUN_SOURCE_RECOVERY", json.dumps(report, sort_keys=True))
        return 0
    except (ValueError, OSError, KeyError, tarfile.TarError, RuntimeError):
        print("JUDUN_SOURCE_RECOVERY_BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
