"""No production network, account credentials or real signing keys in tests."""
import base64
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
from unittest import TestCase, mock

import direct_deploy_publish as pub


class SignedChannelPublisherTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519",
                        "-out", str(cls.root / "private.pem")],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["openssl", "pkey", "-in", str(cls.root / "private.pem"),
                        "-pubout", "-out", str(cls.root / "public.pem")],
                       check=True, stdout=subprocess.DEVNULL)
        cls.pubkey = cls.root / "public.pem"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def sample(self, **change):
        cms = b"\x30\x03synthetic-cms-not-a-live-release"
        data = {
            "schema": "judun-autodeploy-v1",
            "release_id": "v1.2.127-p1-evidence-20261022",
            "base_artifact_id": "JUDUN-1.2.126-5D4BA415AA32",
            "target_artifact_id": "JUDUN-1.2.127-ABCDEF987654",
            "target_build_instance_id": "1.2.127-20261022-P1-ABCDEF987654",
            "expected_display_version": "v1.2.127",
            "payload_path": "releases/v1.2.127-p1.cms.b64",
            "payload_sha256": sha256(cms).hexdigest(),
            "noop": False,
        } | change
        manifest = (json.dumps(data, separators=(",", ":")) + "\n").encode()
        plain = self.root / "test_manifest.json"
        signed = self.root / "test_manifest.sig"
        plain.write_bytes(manifest)
        subprocess.run(["openssl", "pkeyutl", "-sign",
                        "-inkey", str(self.root / "private.pem"), "-rawin",
                        "-in", str(plain), "-out", str(signed)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return manifest, base64.b64encode(signed.read_bytes()), base64.b64encode(cms)

    def test_valid_independently_signed_release(self):
        manifest, sig, payload = self.sample()
        info = pub.parse_signed_manifest(manifest, sig, payload, self.pubkey)
        self.assertEqual(info["expected_display_version"], "v1.2.127")

    def test_tamper_and_key_mismatch_fail_closed(self):
        m, sig, payload = self.sample()
        for vals in ((m + b" ", sig, payload),
                     (m, sig[:-3], payload),
                     (m, sig, base64.b64encode(b"modified"))):
            with self.subTest(size=list(map(len, vals))):
                with self.assertRaises(ValueError):
                    pub.parse_signed_manifest(*vals, self.pubkey)

    def test_cannot_publish_same_or_older_version(self):
        for target in ("JUDUN-1.2.126-ABCDEF123456",
                       "JUDUN-1.2.125-ABCDEF123456"):
            m, sig, payload = self.sample(
                target_artifact_id=target, expected_display_version="v1.2.126")
            with self.assertRaises(ValueError):
                pub.parse_signed_manifest(m, sig, payload, self.pubkey)

    def test_duplicate_control_key_denied(self):
        m, sig, payload = self.sample()
        raw = m[:-2] + b',"noop":false}\n'
        with self.assertRaisesRegex(ValueError, "DIRECT_DEPLOY_DUPLICATE_CONTROL_FIELD"):
            pub.parse_signed_manifest(raw, sig, payload, self.pubkey)

    def test_live_requires_exact_base_and_81_managed_files(self):
        base = "JUDUN-1.2.126-5D4BA415AA32"
        digest = "a" * 64
        build = {"artifact_id": base}
        deep = {"artifact_id": base, "status": "ok", "deep_verified": True,
                "mismatch_count": 0, "files_verified": 81,
                "manifest_file_count": 81, "source_tree_sha256": digest}
        pub.check_live(build, deep, base, digest)
        for override in ({"mismatch_count": 1}, {"files_verified": 79},
                         {"source_tree_sha256": "b" * 64},
                         {"manifest_file_count": 80}):
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    pub.check_live(build, deep | override, base, digest)

    def test_atomic_publisher_writes_no_partial_ref_and_checks_source_key(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        pinned = self.pubkey.read_bytes()
        old = json.dumps({"target_artifact_id": info["base_artifact_id"]}).encode()
        calls = []
        def fake_http(method, endpoint, token, body=None, missing_ok=False):
            calls.append((method, endpoint, body))
            if endpoint.startswith("/git/ref/"):
                return {"object": {"sha": "a"*40}}
            if endpoint.startswith("/git/commits/"):
                return {"tree": {"sha": "b"*40}}
            if endpoint.startswith("/contents/channel/stable.json"):
                return {"content": base64.b64encode(old).decode()}
            if endpoint.startswith("/contents/keys/release_signing_public.pem"):
                return {"content": base64.b64encode(pinned).decode()}
            if endpoint.startswith("/contents/releases/"):
                return None
            if endpoint == "/git/blobs":
                return {"sha": "c"*40}
            if endpoint == "/git/trees":
                return {"sha": "d"*40}
            if endpoint == "/git/commits":
                return {"sha": "e"*40}
            if endpoint.startswith("/git/refs/") and method == "PATCH":
                return {"ref": "refs/heads/main"}
            raise AssertionError(endpoint)
        verify_called = []
        with mock.patch.object(pub, "github", side_effect=fake_http):
            result = pub.publish_atomic(m, sig, cms, info,
                                        self.pubkey, "test-only", lambda: verify_called.append(True))
        self.assertEqual(result, "e"*40)
        self.assertEqual(verify_called, [True])
        posts = [call for call in calls if call[0] == "POST" and call[1] == "/git/blobs"]
        self.assertEqual(len(posts), 3)
        self.assertEqual([x["path"] for x in next(body for meth, end, body in calls
                          if end == "/git/trees")["tree"]],
                         [info["payload_path"], "channel/stable.json.sig.b64",
                          "channel/stable.json"])
        self.assertEqual(calls[-1][0], "PATCH")
        self.assertEqual(calls[-1][2]["force"], False)

    def test_existing_payload_and_stale_channel_refused_before_git_writes(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        old = json.dumps({"target_artifact_id": "JUDUN-1.2.120-BADBADBADBAD"}).encode()
        def stale(method, endpoint, token, body=None, missing_ok=False):
            if endpoint.startswith("/git/ref/"):
                return {"object": {"sha": "a"*40}}
            if endpoint.startswith("/git/commits/"):
                return {"tree": {"sha": "b"*40}}
            if endpoint.startswith("/contents/channel/"):
                return {"content": base64.b64encode(old).decode()}
            if endpoint.startswith("/contents/keys/"):
                return {"content": base64.b64encode(self.pubkey.read_bytes()).decode()}
            raise AssertionError("unreachable")
        with mock.patch.object(pub, "github", side_effect=stale):
            with self.assertRaisesRegex(ValueError, "DIRECT_DEPLOY_CHANNEL_BASE_NOT_LIVE_BASE"):
                pub.publish_atomic(m, sig, cms, info, self.pubkey, "test-only", None)

    def test_post_publish_acceptance_requires_actual_target_and_deep_sha(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        target = info["target_artifact_id"]
        build = {"artifact_id": target, "build_instance_id": info["target_build_instance_id"],
                 "display_version": info["expected_display_version"]}
        deep = {"artifact_id": target, "build_instance_id": info["target_build_instance_id"],
                "status": "ok", "deep_verified": True, "mismatch_count": 0,
                "files_verified": 81, "manifest_file_count": 81}
        def live_good(path):
            return ({"/health/build": build, "/health/artifact?deep=true": deep,
                     "/health/ready": {"status": "ready"}})[path]
        with mock.patch.object(pub, "live_get", side_effect=live_good):
            result = pub.verify_target_live(info, attempts=1, interval=0)
        self.assertEqual(result["managed_files"], 81)
        self.assertEqual(result["version"], "v1.2.127")

        for drift in ({"mismatch_count": 1}, {"manifest_file_count": 82},
                      {"artifact_id": "JUDUN-1.2.126-5D4BA415AA32"}):
            def live_bad(path):
                if path == "/health/artifact?deep=true":
                    return deep | drift
                return live_good(path)
            with self.subTest(drift=drift):
                with mock.patch.object(pub, "live_get", side_effect=live_bad):
                    with self.assertRaisesRegex(
                            ValueError, "DIRECT_DEPLOY_PUBLISHED_BUT_VPS_DEPLOYMENT_NOT_VERIFIED"):
                        pub.verify_target_live(info, attempts=1, interval=0)

    def test_post_publish_old_live_version_cannot_claim_success(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        with mock.patch.object(pub, "live_get", return_value={
                "artifact_id": info["base_artifact_id"]}):
            with self.assertRaisesRegex(
                    ValueError, "DIRECT_DEPLOY_PUBLISHED_BUT_VPS_DEPLOYMENT_NOT_VERIFIED"):
                pub.verify_target_live(info, attempts=2, interval=0)
