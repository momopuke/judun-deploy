"""Synthetic CMS attestation tests, never production source or keys."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from attest_encrypted_source import audit, recipient_serial
from test_offline_source_recovery import make_suite


class CmsSourceProvenanceTests(unittest.TestCase):
    def test_matching_recipient_and_ciphertext_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            enc, meta, hist, source = make_suite(root)
            result = audit(enc, meta, root / "cert.pem")
            self.assertTrue(result["sha256_matches_attestation"])
            self.assertTrue(result["recipient_matches_approved_public_certificate"])
            self.assertFalse(result["decrypted_source_recovered"])

    def test_ciphertext_drift_rejected_before_decryption(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            enc, meta, hist, source = make_suite(root)
            enc.write_bytes(enc.read_bytes() + b"\nAA==")
            with self.assertRaisesRegex(ValueError, "CMS_DIGEST_DRIFT|INVALID_BASE64"):
                audit(enc, meta, root / "cert.pem")

    def test_wrong_public_certificate_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            enc, meta, hist, source = make_suite(root)
            wrong = root / "wrong.pem"
            wrong.write_text("not a valid cert")
            with self.assertRaisesRegex(ValueError, "INVALID_PUBLIC_CERT"):
                audit(enc, meta, wrong)


if __name__ == "__main__":
    unittest.main()
