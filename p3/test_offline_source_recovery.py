"""All tests are synthetic; no production keys, endpoints, or source are used."""
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from offline_source_recovery import recover, sha, inspect_plaintext, HIST_CERT, HIST_KEY

BUILD = "JUDUN-1.2.114-AA38F0567A4D"


def openssl(*args):
    subprocess.run(["openssl", *args], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True, timeout=25)


def make_suite(root: Path):
    cert = root / "cert.pem"
    private = root / "private.pem"
    plain = root / "fixture.tar.gz"
    ciphertext = root / "fixture.cms"
    ciphertext_b64 = root / "asset.cms.b64"
    metadata = root / "asset-meta.json"
    historic = root / "historic.zip"
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-subj", "/CN=JUDUN-LOCAL-TEST-ONLY",
            "-days", "1", "-keyout", str(private), "-out", str(cert))
    source = b'APP_VERSION = "1.2.114"\nRELEASE_REVISION = "1.2.114"\n'
    with tarfile.open(plain, "w:gz") as tar:
        info = tarfile.TarInfo(name="runtime/app.py")
        info.size = len(source)
        tar.addfile(info, BytesIO(source))
    openssl("cms", "-encrypt", "-binary", "-aes256", "-in", str(plain),
            "-out", str(ciphertext), "-outform", "DER", str(cert))
    blob = ciphertext.read_bytes()
    ciphertext_b64.write_bytes(base64.b64encode(blob))
    metadata.write_text(json.dumps({
        "version": "1.2.114", "artifact_id": BUILD,
        "encrypted_source_sha256": sha(blob),
    }))
    with ZipFile(historic, "w") as z:
        z.writestr(HIST_KEY, private.read_bytes())
        z.writestr(HIST_CERT, cert.read_bytes())
    return ciphertext_b64, metadata, historic, source


class OfflineSourceRestoreTests(unittest.TestCase):
    def test_synthetic_aes_cms_decrypt_and_private_stage_only(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            enc, meta, hist, source = make_suite(root)
            result = recover(enc, meta, hist)
            self.assertTrue(result["ciphertext_sha256_verified"])
            self.assertTrue(result["history_key_certificate_match"])
            self.assertEqual(result["app_sha256"], sha(source))
            self.assertFalse(result["staged_to_private_destination"])
            self.assertEqual(result["recovered_app_matches_live_authoritative_sha"], "NOT_VERIFIED")
            restricted = root / "private-stage"
            restricted.mkdir(mode=0o700)
            dest = restricted / "app.py"
            staged = recover(enc, meta, hist, out_private=dest)
            self.assertTrue(staged["staged_to_private_destination"])
            self.assertEqual(dest.read_bytes(), source)
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "REFUSE_OVERWRITE_PRIVATE_STAGING"):
                recover(enc, meta, hist, out_private=dest)

    def test_block_ciphertext_tampering_and_invalid_release_identity(self):
        with tempfile.TemporaryDirectory() as td:
            enc, meta, hist, _ = make_suite(Path(td))
            enc.write_bytes(enc.read_bytes() + b"A")
            with self.assertRaisesRegex(ValueError, "CIPHERTEXT_SHA256_MISMATCH|INVALID_CMS_BASE64"):
                recover(enc, meta, hist)
            enc, meta, hist, _ = make_suite(Path(td))
            record = json.loads(meta.read_text())
            record["artifact_id"] = "JUDUN-1.2.113-STALE"
            meta.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "UNEXPECTED_SOURCE_ATTESTATION"):
                recover(enc, meta, hist)

    def test_reject_unsafe_archived_member_and_wrong_python_version(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bad = root / "bad.tar.gz"
            with tarfile.open(bad, "w:gz") as tar:
                info = tarfile.TarInfo(name="../danger")
                raw = b"unsafe"
                info.size = len(raw)
                tar.addfile(info, BytesIO(raw))
            with self.assertRaisesRegex(ValueError, "UNSAFE_ARCHIVE_MEMBER"):
                inspect_plaintext(bad, "1.2.114")
            bad.write_text('APP_VERSION = "1.2.113"\n')
            with self.assertRaisesRegex(ValueError, "APP_RELEASE_VERSION_MISMATCH"):
                inspect_plaintext(bad, "1.2.114")


if __name__ == "__main__":
    unittest.main()
