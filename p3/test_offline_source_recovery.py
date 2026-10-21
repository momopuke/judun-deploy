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
from offline_source_recovery import recover, sha, inspect_plaintext, verify_live_app_tree, HIST_CERT, HIST_KEY
from production_delta_patch import computed_tree_sha

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
            with self.assertRaisesRegex(ValueError, "PRIVATE_STAGING_REQUIRES_VERIFIED_LIVE_SOURCE"):
                recover(enc, meta, hist, out_private=dest)
            rows = [{"path": "runtime/app.py", "size": len(source), "sha256": sha(source)}]
            for i in range(80):
                data = ("fixture-file-" + str(i)).encode("ascii")
                rows.append({"path": "runtime/ref%03d" % i, "size": len(data), "sha256": sha(data)})
            tree = computed_tree_sha(rows)
            trusted = root / "trusted-manifest.json"
            trusted.write_text(json.dumps({
                "schema": "judun.deploy-manifest.v1",
                "version": "1.2.114", "artifact_id": BUILD,
                "files": rows, "source_tree_sha256": tree,
            }))
            staged = recover(enc, meta, hist, out_private=dest,
                             trusted_manifest=trusted, public_tree_sha256=tree)
            self.assertTrue(staged["staged_to_private_destination"])
            self.assertEqual(dest.read_bytes(), source)
            self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "REFUSE_OVERWRITE_PRIVATE_STAGING"):
                recover(enc, meta, hist, out_private=dest,
                        trusted_manifest=trusted, public_tree_sha256=tree)

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

    def test_rejects_duplicate_tar_or_zip_member_before_choosing_app(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original = b'APP_VERSION = "1.2.114"\n'
            for kind in ("tar", "zip"):
                with self.subTest(kind=kind):
                    archive = root / ("dup.tar.gz" if kind == "tar" else "dup.zip")
                    if kind == "tar":
                        with tarfile.open(archive, "w:gz") as tar:
                            for content in (original, b'APP_VERSION = "1.2.114"\n# different\n'):
                                item = tarfile.TarInfo("runtime/app.py")
                                item.size = len(content)
                                tar.addfile(item, BytesIO(content))
                    else:
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            with ZipFile(archive, "w") as z:
                                z.writestr("runtime/app.py", original)
                                z.writestr("runtime/app.py", original + b"# different\n")
                    with self.assertRaisesRegex(ValueError, "DUPLICATE_ARCHIVE_MEMBER"):
                        inspect_plaintext(archive, "1.2.114")

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


    def test_actual_synthetic_cms_recovery_requires_independent_tree(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            encrypted, verify_file, archive, app = make_suite(root)
            rows = [{"path": "runtime/app.py", "size": len(app), "sha256": sha(app)}]
            for index in range(80):
                data = ("filler" + str(index)).encode()
                rows.append({"path": "runtime/ref%03d" % index,
                             "size": len(data), "sha256": sha(data)})
            tree = computed_tree_sha(rows)
            live_manifest = root / "live-manifest.json"
            live_manifest.write_text(json.dumps({
                "schema": "judun.deploy-manifest.v1",
                "version": "1.2.114", "artifact_id": BUILD,
                "source_tree_sha256": tree, "files": rows,
            }))
            result = recover(encrypted, verify_file, archive,
                             trusted_manifest=live_manifest, public_tree_sha256=tree)
            self.assertEqual(
                result["recovered_app_matches_live_authoritative_sha"],
                "VERIFIED_VIA_INDEPENDENT_LIVE_TREE",
            )
            with self.assertRaisesRegex(ValueError, "INDEPENDENT_SOURCE_TREE_DRIFT"):
                recover(encrypted, verify_file, archive,
                        trusted_manifest=live_manifest, public_tree_sha256="f" * 64)
            with self.assertRaisesRegex(ValueError, "MANIFEST_AND_TREE_REQUIRED_TOGETHER"):
                recover(encrypted, verify_file, archive, trusted_manifest=live_manifest)

    def test_full_app_must_match_independent_live_release_tree(self):
        app = b'APP_VERSION = "1.2.114"\n'
        records = [{"path": "system_files/app.py", "size": len(app), "sha256": sha(app)}]
        for index in range(80):
            data = ("synthetic_" + str(index)).encode()
            records.append({"path": "system_files/sim_%02d" % index,
                            "size": len(data), "sha256": sha(data)})
        tree = computed_tree_sha(records)
        manifest = {
            "schema": "judun.deploy-manifest.v1",
            "version": "1.2.114",
            "artifact_id": BUILD,
            "files": records,
            "source_tree_sha256": tree,
        }
        self.assertTrue(verify_live_app_tree(app, manifest, tree))
        with self.assertRaisesRegex(ValueError, "APP_DOES_NOT_MATCH_LIVE_TREE"):
            verify_live_app_tree(app + b"changed", manifest, tree)
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_SOURCE_TREE_DRIFT"):
            verify_live_app_tree(app, manifest, "f" * 64)
        incomplete = dict(manifest, files=records[:1])
        with self.assertRaisesRegex(ValueError, "INCOMPLETE_INDEPENDENT_MANIFEST"):
            verify_live_app_tree(app, incomplete, tree)
        mismatched = dict(manifest, artifact_id="JUDUN-1.2.113-OLDER")
        with self.assertRaisesRegex(ValueError, "INDEPENDENT_MANIFEST_IDENTITY_MISMATCH"):
            verify_live_app_tree(app, mismatched, tree)


if __name__ == "__main__":
    unittest.main()
