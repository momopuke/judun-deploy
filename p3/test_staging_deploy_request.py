"""Verify the signed GitHub staging request through the actual staging installer."""

import base64
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

import staging_deploy_request as channel
import staging_release as stage


def sha(data):
    return hashlib.sha256(data).hexdigest()


class StagingRequestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.keys = Path(directory.name)
        cls.keygen("genpkey", "-algorithm", "Ed25519", "-out", "signing.pem")
        cls.keygen("pkey", "-in", "signing.pem", "-pubout", "-out", "release_signing_public.pem")
        cls.keygen("req", "-x509", "-newkey", "rsa:2048", "-noenc", "-days", "1",
                   "-subj", "/CN=Judun staging test", "-out", "recipient.pem",
                   "-keyout", "recipient-key.pem")

    @classmethod
    def keygen(cls, *args):
        subprocess.run(["openssl", *args], cwd=cls.keys, capture_output=True, check=True)

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.work = Path(directory.name)
        self.root, self.state = self.work / "stage", self.work / "requests"
        signing_key = self.keys / "release_signing_public.pem"
        pin = patch.object(channel, "KEY_SHA256", sha(signing_key.read_bytes()))
        pin.start()
        self.addCleanup(pin.stop)
        self.previous, baseline = self.package(189)
        stage.prepare(self.root, baseline, self.previous)
        stage.initialize(self.root, self.previous.name)
        self.target, self.candidate = self.package(190)
        self.commit = "1" * 40
        self.prefix = f"{self.commit}/staging/candidate"
        self.files = {
            channel.REQUEST: json.dumps({"candidate_commit": self.commit}).encode(),
        }
        self.downloads = []
        self.restarts = []

    def package(self, patch_number):
        content = f"# staging fixture {patch_number}\n".encode()
        digest = sha(content)
        tree = sha(f"app.py\t{digest}\t{len(content)}\n".encode())
        target = stage.Release(f"1.2.{patch_number}", f"FIXTURE-{patch_number}",
                               f"BUILD-{patch_number}", tree, 1)
        manifest = asdict(target)
        manifest.update(schema="judun.deploy-manifest.v1",
                        files=[{"path": "app.py", "size": len(content), "sha256": digest}])
        package = self.work / f"{patch_number}.zip"
        with ZipFile(package, "w") as archive:
            archive.writestr("payload/" + stage.MANIFEST, json.dumps(manifest))
            archive.writestr("payload/app.py", content)
        return target, package

    def approve(self, baseline=None):
        envelope = self.work / "candidate.cms"
        channel.openssl("cms", "-encrypt", "-binary", "-aes256", "-outform", "DER",
                        "-in", str(self.candidate), "-out", str(envelope),
                        str(self.keys / "recipient.pem"))
        manifest = self.work / "candidate.json"
        signature = self.work / "candidate.sig"
        manifest.write_text(json.dumps({
            "schema": channel.SCHEMA,
            "base_snapshot": baseline or self.previous.name,
            "target": asdict(self.target),
            "cms_sha256": sha(envelope.read_bytes()),
            "zip_sha256": sha(self.candidate.read_bytes()),
        }))
        channel.openssl("pkeyutl", "-sign", "-inkey", str(self.keys / "signing.pem"),
                        "-rawin", "-in", str(manifest), "-out", str(signature))
        self.files.update({
            self.prefix + ".json": manifest.read_bytes(),
            self.prefix + ".json.sig.b64": base64.b64encode(signature.read_bytes()),
            self.prefix + ".cms": envelope.read_bytes(),
        })

    def fetch(self, path, limit, destination=None):
        self.downloads.append(path)
        data = self.files[path]
        self.assertLessEqual(len(data), limit)
        if destination is not None:
            destination.write_bytes(data)
        return data

    def install(self, health=None):
        return channel.install_request(
            self.root, self.state, self.keys, self.fetch,
            lambda: self.restarts.append(stage.selection(self.root).name),
            health or (lambda release: None),
        )

    def test_signed_candidate_installs_and_repeat_is_read_only(self):
        self.approve()
        self.assertEqual(self.install()["status"], "installed")
        self.assertEqual(stage.verify_snapshot(stage.selection(self.root)), self.target)
        self.assertEqual(self.install()["status"], "already_active")
        self.assertEqual(self.restarts, [self.target.name])
        self.assertEqual(self.downloads.count(self.prefix + ".cms"), 1)

    def test_no_request_leaves_the_running_snapshot_in_place(self):
        self.files[channel.REQUEST] = b'{"candidate_commit":null}'
        self.assertEqual(self.install(), {"status": "no_request"})
        self.assertEqual(self.downloads, [channel.REQUEST])
        self.assertFalse(self.restarts)

    def test_superseded_request_cannot_switch_the_snapshot(self):
        self.approve()
        original_fetch = self.fetch

        def replace_request(path, limit, destination=None):
            response = original_fetch(path, limit, destination)
            if path.endswith(".cms"):
                self.files[channel.REQUEST] = json.dumps({"candidate_commit": "2" * 40}).encode()
            return response

        self.fetch = replace_request
        self.assertEqual(self.install()["status"], "superseded")
        self.assertEqual(stage.verify_snapshot(stage.selection(self.root)), self.previous)
        self.assertFalse(self.restarts)

    def test_tampered_manifest_is_rejected_before_payload_download(self):
        self.approve()
        self.files[self.prefix + ".json"] += b" "
        with self.assertRaisesRegex(ValueError, "signature"):
            self.install()
        self.assertNotIn(self.prefix + ".cms", self.downloads)
        self.assertFalse(self.restarts)

    def test_signed_request_for_another_baseline_does_not_switch(self):
        self.approve(baseline="OTHER-" + "2" * 64)
        with self.assertRaisesRegex(ValueError, "stale staging baseline"):
            self.install()
        self.assertNotIn(self.prefix + ".cms", self.downloads)
        self.assertFalse(self.restarts)

    def test_modified_encrypted_package_is_rejected(self):
        self.approve()
        self.files[self.prefix + ".cms"] += b"!"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.install()
        self.assertEqual(stage.verify_snapshot(stage.selection(self.root)), self.previous)
        self.assertFalse(self.restarts)

    def test_failed_start_restores_previous_and_repeat_does_not_interrupt_it(self):
        self.approve()

        def health(release):
            if release == self.target:
                raise RuntimeError("fixture startup failed")

        with self.assertRaisesRegex(RuntimeError, "fixture startup failed"):
            self.install(health)
        self.assertEqual(stage.verify_snapshot(stage.selection(self.root)), self.previous)
        with self.assertRaisesRegex(ValueError, "already attempted"):
            self.install(health)
        self.assertEqual(self.restarts, [self.target.name, self.previous.name])


if __name__ == "__main__":
    unittest.main()
