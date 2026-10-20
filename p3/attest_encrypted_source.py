"""Non-secret v1.2.114 CMS source provenance gate: verify SHA and recipient.

No decryption, no private key, no output ciphertext/source, no network.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
ASSET = ROOT / "assets/v1.2.114-expansion-resilience-source-20261017.cms.b64"
RECORD = ROOT / "assets/v1.2.114-expansion-resilience-verification-20261017.json"
CERT = ROOT / "keys/payload_encrypt_cert.pem"
MAX_CMS = 32 * 1024 * 1024


def stop(code: str):
    raise ValueError("CMS_PROVENANCE_" + code)


def read_tlv(blob: bytes, offset: int, expected_tag: int) -> tuple[int, int]:
    if offset + 2 > len(blob) or blob[offset] != expected_tag:
        stop("UNEXPECTED_ASN1_TAG")
    length_octet = blob[offset + 1]
    cursor = offset + 2
    if length_octet & 0x80:
        octets = length_octet & 0x7f
        if not 1 <= octets <= 4 or cursor + octets > len(blob):
            stop("INVALID_ASN1_LENGTH")
        length = int.from_bytes(blob[cursor:cursor + octets], "big")
        cursor += octets
    else:
        length = length_octet
    if length < 0 or cursor + length > len(blob):
        stop("ASN1_OVERFLOW")
    return cursor, cursor + length


def recipient_serial(envelope: bytes) -> str:
    """Parse the original CMS IssuerAndSerial recipient, no X.509 private data."""
    start, end = read_tlv(envelope, 0, 0x30)
    pos, pos_end = read_tlv(envelope, start, 0x06)
    # PKCS#7 envelopedData OID 1.2.840.113549.1.7.3
    if envelope[pos:pos_end] != bytes.fromhex("2a864886f70d010703"):
        stop("NOT_ENVELOPED_DATA")
    ctxt, _ = read_tlv(envelope, pos_end, 0xa0)
    env, _ = read_tlv(envelope, ctxt, 0x30)
    _, p = read_tlv(envelope, env, 0x02)
    recipients, _ = read_tlv(envelope, p, 0x31)
    recipient, _ = read_tlv(envelope, recipients, 0x30)
    _, p = read_tlv(envelope, recipient, 0x02)
    rid, _ = read_tlv(envelope, p, 0x30)
    _, p = read_tlv(envelope, rid, 0x30)  # issuer
    serial, serial_end = read_tlv(envelope, p, 0x02)
    value = envelope[serial:serial_end].hex().upper().lstrip("0")
    if not value or len(value) > 80:
        stop("INVALID_RECIPIENT_SERIAL")
    return value


def certificate_serial(cert_path: Path) -> str:
    try:
        p = subprocess.run(
            ["openssl", "x509", "-in", str(cert_path), "-serial", "-noout"],
            capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        stop("OPENSSL_UNAVAILABLE")
    if p.returncode != 0:
        stop("INVALID_PUBLIC_CERT")
    value = p.stdout.decode("ascii", errors="ignore").strip()
    if not re.fullmatch(r"serial=[0-9A-Fa-f]{1,80}", value):
        stop("INVALID_CERT_SERIAL")
    return value.split("=", 1)[1].upper().lstrip("0")


def audit(asset: Path = ASSET, verification: Path = RECORD, cert: Path = CERT) -> dict:
    record = json.loads(verification.read_text("utf-8"))
    if (record.get("version") != "1.2.114"
            or record.get("artifact_id") != "JUDUN-1.2.114-AA38F0567A4D"):
        stop("UNEXPECTED_LIVE_BASELINE")
    if asset.stat().st_size > MAX_CMS * 2:
        stop("ENCODED_ASSET_TOO_LARGE")
    try:
        ciphertext = base64.b64decode(b"".join(asset.read_bytes().split()), validate=True)
    except (ValueError, binascii.Error):
        stop("INVALID_BASE64")
    if not ciphertext or len(ciphertext) > MAX_CMS:
        stop("INVALID_CMS_SIZE")
    digest = hashlib.sha256(ciphertext).hexdigest()
    if digest != record.get("encrypted_source_sha256"):
        stop("CMS_DIGEST_DRIFT")
    serial = recipient_serial(ciphertext)
    if serial != certificate_serial(cert):
        stop("CMS_RECIPIENT_CERT_DRIFT")
    return {
        "status": "CMS_SOURCE_PROVENANCE_PASS",
        "version": "1.2.114",
        "artifact_id": record["artifact_id"],
        "ciphertext_bytes": len(ciphertext),
        "sha256_matches_attestation": True,
        "recipient_matches_approved_public_certificate": True,
        "decrypted_source_recovered": False,
        "deployed": False,
    }


if __name__ == "__main__":
    try:
        print("P3_ENCRYPTED_SOURCE", json.dumps(audit(), sort_keys=True))
    except (ValueError, OSError, KeyError, json.JSONDecodeError):
        print("P3_ENCRYPTED_SOURCE_BLOCKED")
        raise SystemExit(2)
