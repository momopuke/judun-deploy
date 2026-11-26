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

    def test_stage_mismatch_reports_only_release_identity(self):
        target = {"target_artifact_id": "new", "target_build_instance_id": "build",
                  "expected_display_version": "v1.2.193"}
        build = {"status": "ok", "manifest_status": "ok", "artifact_id": "new",
                 "build_instance_id": "build", "display_version": "v1.2.193",
                 "version": "1.2.192", "source_tree_sha256": "a" * 64,
                 "payment_mode": "test_unlock", "unrelated": "private data"}
        for version, tree, expected_version, expected_tree in (
            ("1.2.192", "a" * 64, "1.2.192", "a" * 64),
            ("private data", {"raw": "private data"}, "unknown", "unknown"),
        ):
            with self.subTest(version=version), self.assertRaises(ValueError) as caught:
                pub.check_target_build({**build, "version": version, "source_tree_sha256": tree},
                                       target, "b" * 64, "test_unlock")
            self.assertEqual(str(caught.exception),
                             "DIRECT_DEPLOY_LIVE_TARGET_BUILD_MISMATCH fields=version,source_tree_sha256 "
                             f"observed_version={expected_version} observed_tree={expected_tree}")

    def sample(self, **change):
        cms = b"\x30\x03synthetic-cms-not-a-live-release"
        data = {
            "schema": "judun-autodeploy-v1",
            "release_id": "v1.2.127-p1-evidence-20261022",
            "base_artifact_id": "JUDUN-1.2.126-5D4BA415AA32",
            "target_artifact_id": "JUDUN-1.2.127-ABCDEF987654",
            "target_build_instance_id": "1.2.127-20261022-P1-ABCDEF987654",
            "expected_display_version": "v1.2.127",
            "expected_managed_file_count": 81,
            "expected_source_tree_sha256": "a" * 64,
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

    def test_staging_auth_cannot_access_admin_or_payment_routes(self):
        for path in (
            "/", "/admin", "/admin/email-test",
            "/ecpay/callback", "/payment/confirm",
            "/health/artifact?deep=false",
            "/health/artifact?deep=true&anything=1",
            "/health/build?session=x",
            "//external.invalid/health/build",
        ):
            with self.subTest(path=path), self.assertRaisesRegex(
                ValueError, "DIRECT_DEPLOY_(STAGING_AUTH_HEALTH_PATH_ONLY|SITE_OR_PATH_INVALID)"
            ):
                pub.site_get(pub.STAGING, path, token="synthetic-local-only")
        with self.assertRaisesRegex(ValueError, "STAGING_AUTH_ORIGIN_MISMATCH"):
            pub.site_get(pub.LIVE, "/health/build", token="synthetic-local-only")

    def test_staging_auth_rejects_control_characters_and_empty_tokens(self):
        for token in ("", "space not allowed", "line\nfeed", "return\rfeed",
                      "tab\tchar", "x" * 4097, 47, None):
            if token is None:
                continue  # None is public/no-token mode; normal existing live path.
            with self.subTest(token_type=type(token).__name__), self.assertRaisesRegex(
                ValueError, "STAGING_AUTH_TOKEN_MALFORMED"
            ):
                pub.site_get(pub.STAGING, "/health/build", token=token)

    def test_only_attested_staging_gets_sites_auth_header(self):
        class FakeResponse:
            status = 200
            def __init__(self, url):
                self.url = url
            def geturl(self):
                return self.url
            def read(self, n):
                return b'{"status":"ok"}'
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False

        requests = []
        class FakeOpener:
            def open(self, request, timeout):
                requests.append(request)
                return FakeResponse(request.full_url)

        with mock.patch.object(pub, "build_opener", return_value=FakeOpener()):
            for path in sorted(pub.STAGING_ATTESTED_PATHS):
                self.assertEqual(
                    pub.site_get(pub.STAGING, path, token="synthetic-stage-health"),
                    {"status": "ok"},
                )
        self.assertEqual(len(requests), 3)
        self.assertTrue(all(req.get_method() == "GET" for req in requests))
        self.assertTrue(all(
            req.get_header("Oai-sites-authorization") == "Bearer synthetic-stage-health"
            for req in requests
        ))

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
        build = {"artifact_id": base, "version": "1.2.126",
                 "build_instance_id": "1.2.126-20261022-HOME-5D4BA415AA32",
                 "source_tree_sha256": digest}
        deep = {"artifact_id": base, "version": "1.2.126",
                "build_instance_id": build["build_instance_id"],
                "status": "ok", "deep_verified": True,
                "mismatch_count": 0, "files_verified": 81,
                "manifest_file_count": 81, "source_tree_sha256": digest}
        pub.check_live(build, deep, base, digest)
        for override in ({"mismatch_count": 1}, {"files_verified": 79},
                         {"source_tree_sha256": "b" * 64},
                         {"manifest_file_count": 80},
                         {"build_instance_id": "1.2.126-DRIFT"},
                         {"version": "1.2.125"}):
            with self.subTest(override=override):
                with self.assertRaises(ValueError):
                    pub.check_live(build, deep | override, base, digest)

    def test_live_build_and_deep_split_brain_fails_closed(self):
        base = "JUDUN-1.2.126-5D4BA415AA32"
        digest = "a"*64
        instance = "1.2.126-20261022-HOME-5D4BA415AA32"
        build = {"artifact_id": base, "version": "1.2.126",
                 "build_instance_id": instance, "source_tree_sha256": digest}
        deep = {"artifact_id": base, "version": "1.2.126",
                "build_instance_id": instance, "source_tree_sha256": digest,
                "status": "ok", "deep_verified": True, "mismatch_count": 0,
                "files_verified": 81, "manifest_file_count": 81}
        for drift in ({"source_tree_sha256": "b"*64},
                      {"version": "1.2.125"},
                      {"build_instance_id": "unrelated-instance"}):
            with self.subTest(drift=drift):
                with self.assertRaises(ValueError):
                    pub.check_live(build | drift, deep, base, digest)
        for drift in ({"source_tree_sha256": "b"*64},
                      {"version": "1.2.125"},
                      {"build_instance_id": "unrelated-instance"}):
            with self.subTest(deep_drift=drift):
                with self.assertRaises(ValueError):
                    pub.check_live(build, deep | drift, base, digest)

    def test_publisher_opens_one_exact_release_pr_without_writing_main(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        pinned = self.pubkey.read_bytes()
        old = json.dumps({"target_artifact_id": info["base_artifact_id"]}).encode()
        branch = "release/" + info["release_id"] + "-" + sha256(m).hexdigest()[:24]
        existing = False
        existing_pr = False
        current_main = "a"*40
        candidate_sha = "e"*40
        calls = []
        def fake_http(method, endpoint, token, body=None, missing_ok=False):
            nonlocal existing, existing_pr
            calls.append((method, endpoint, body))
            if endpoint == "/git/ref/heads/main" and method == "GET":
                return {"object": {"sha": current_main}}
            if endpoint == "/git/ref/heads/" + branch and method == "GET":
                return {"object": {"sha": candidate_sha}} if existing else None
            if endpoint == "/git/refs" and method == "POST":
                self.assertEqual(body, {"ref": "refs/heads/" + branch, "sha": "e"*40})
                existing = True
                return {}
            if endpoint.startswith("/git/commits/"):
                if endpoint.endswith("e"*40):
                    return {"tree": {"sha": "d"*40}, "parents": [{"sha": "a"*40}]}
                if endpoint.endswith("f"*40):
                    return {"tree": {"sha": "d"*40}, "parents": [
                        {"sha": "e"*40}, {"sha": current_main}]}
                return {"tree": {"sha": "b"*40}}
            if endpoint.startswith("/contents/channel/stable.json"):
                return {"content": base64.b64encode(old).decode()}
            if endpoint.startswith("/contents/keys/release_signing_public.pem"):
                return {"content": base64.b64encode(pinned).decode()}
            if endpoint.startswith("/contents/releases/"):
                return None
            if endpoint == "/git/blobs":
                return {"sha": pub.git_blob_oid(base64.b64decode(body["content"]))}
            if endpoint == "/git/trees":
                return {"sha": "d"*40}
            if endpoint == "/git/commits":
                return {"sha": "e"*40}
            request = {"number": 24, "state": "open",
                       "head": {"sha": candidate_sha, "ref": branch}, "base": {"ref": "main"}}
            if endpoint.startswith("/pulls?") and method == "GET":
                return [request] if existing_pr else []
            if endpoint == "/pulls" and method == "POST":
                self.assertEqual(body["head"], branch)
                self.assertEqual(body["base"], "main")
                existing_pr = True
                return request
            raise AssertionError(endpoint)
        verify_called = []
        with mock.patch.object(pub, "github", side_effect=fake_http):
            result = pub.publish_atomic(m, sig, cms, info,
                                        self.pubkey, "test-only", lambda: verify_called.append(True))
        self.assertEqual(result, {"candidate_commit": "e"*40,
                                  "pull_request": f"https://github.com/{pub.REPO}/pull/24"})
        self.assertEqual(verify_called, [True])
        posts = [call for call in calls if call[0] == "POST" and call[1] == "/git/blobs"]
        self.assertEqual(len(posts), 3)
        self.assertEqual([x["path"] for x in next(body for meth, end, body in calls
                          if end == "/git/trees")["tree"]],
                         [info["payload_path"], "channel/stable.json.sig.b64",
                          "channel/stable.json"])
        self.assertFalse(any(method == "PATCH" for method, _, _ in calls))
        with mock.patch.object(pub, "github", side_effect=fake_http):
            self.assertEqual(pub.publish_atomic(
                m, sig, cms, info, self.pubkey, "test-only", None), result)
            current_main = "c"*40
            candidate_sha = "f"*40
            self.assertEqual(pub.publish_atomic(
                m, sig, cms, info, self.pubkey, "test-only", None),
                result | {"candidate_commit": candidate_sha})
        for endpoint in ("/git/refs", "/git/commits", "/pulls"):
            self.assertEqual(sum(method == "POST" and path == endpoint
                                 for method, path, _ in calls), 1)

    def test_cli_signed_pr_opened_without_sites_owner_token_but_not_merged(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        options = ["publisher", "--publish", "--public-key", str(self.pubkey),
                   "--expected-base-artifact", info["base_artifact_id"],
                   "--expected-source-tree-sha256", info["expected_source_tree_sha256"]]
        for name, value in (("manifest", m), ("signature", sig), ("payload", cms),
                            ("candidate-acceptance", b"private synthetic receipt")):
            path = self.root / ("cli-" + name)
            path.write_bytes(value)
            options.extend(["--" + name, str(path)])
        with (
            mock.patch("sys.argv", options),
            mock.patch.dict(pub.os.environ, {"GITHUB_TOKEN": "synthetic-git"}),
            mock.patch.object(pub, "RELEASE_KEY_SHA256",
                              sha256(self.pubkey.read_bytes()).hexdigest()),
            mock.patch.object(pub, "check_candidate_receipt") as qa,
            mock.patch.object(pub, "check_live"),
            mock.patch.object(pub, "live_get", return_value={"status": "ready", "version": "1.2.126"}),
            mock.patch.object(pub, "verify_staging_live",
                              side_effect=ValueError("Sites owner token must not be used")) as stage,
            mock.patch.object(pub, "publish_atomic",
                              return_value={"pull_request": "synthetic"}) as publish,
            mock.patch.object(pub, "verify_dual_site") as post_merge,
            mock.patch("builtins.print") as output,
        ):
            self.assertEqual(pub.run(), 0)
            qa.assert_called_once()
            publish.assert_called_once()
            stage.assert_not_called()
            post_merge.assert_not_called()
            output.assert_any_call("STAGING_PROOF_REQUIRED_BY_PROTECTED_PR_GATE", flush=True)
            self.assertEqual(output.call_args.args[0], "DIRECT_DEPLOY_RELEASE_PR_OPENED_NOT_DEPLOYED")

    def test_cli_verify_published_uses_oidc_not_sites_bypass(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        options = ["publisher", "--verify-published", "--public-key", str(self.pubkey),
                   "--expected-base-artifact", info["base_artifact_id"],
                   "--expected-source-tree-sha256", info["expected_source_tree_sha256"]]
        for name, value in (("manifest", m), ("signature", sig), ("payload", cms)):
            path = self.root / ("verify-" + name)
            path.write_bytes(value)
            options.extend(["--" + name, str(path)])
        with (
            mock.patch("sys.argv", options),
            mock.patch.object(pub, "RELEASE_KEY_SHA256",
                              sha256(self.pubkey.read_bytes()).hexdigest()),
            mock.patch.object(pub, "verify_published_channel",
                              return_value="a" * 40) as verify_channel,
            mock.patch.object(pub, "verify_dual_site_oidc") as oidc,
            mock.patch.object(pub, "verify_dual_site",
                              side_effect=AssertionError("Legacy Sites path called")),
            mock.patch("builtins.print"),
        ):
            self.assertEqual(pub.run(), 0)
            verify_channel.assert_called_once()
            oidc.assert_called_once()
            self.assertEqual(oidc.call_args.args[0]["expected_display_version"], info["expected_display_version"])

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
                 "display_version": info["expected_display_version"],
                 "version": "1.2.127", "source_tree_sha256": "a"*64,
                 "status": "ok", "manifest_status": "ok", "payment_mode": "ecpay_live"}
        deep = {"artifact_id": target, "build_instance_id": info["target_build_instance_id"],
                "version": "1.2.127", "source_tree_sha256": "a"*64,
                "status": "ok", "deep_verified": True, "mismatch_count": 0,
                "files_verified": 81, "manifest_file_count": 81}
        def live_good(path):
            return ({"/health/build": build, "/health/artifact?deep=true": deep,
                     "/health/ready": {"status": "ready", "version": "1.2.127"}})[path]
        with mock.patch.object(pub, "live_get", side_effect=live_good):
            result = pub.verify_target_live(info, attempts=1, interval=0)
        self.assertEqual(result["managed_files"], 81)
        self.assertEqual(result["version"], "v1.2.127")

        for drift in ({"mismatch_count": 1}, {"manifest_file_count": 82},
                      {"manifest_file_count": 82, "files_verified": 82},
                      {"deep_verified": False}, {"deep_verified": None},
                      {"version": "1.2.126"},
                      {"source_tree_sha256": "b"*64},
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

    def test_post_publish_build_identity_drift_or_missing_tree_cannot_pass(self):
        m, _, _ = self.sample()
        info = json.loads(m)
        build = {"artifact_id": info["target_artifact_id"],
                 "build_instance_id": info["target_build_instance_id"],
                 "display_version": "v1.2.127", "version": "1.2.127",
                 "source_tree_sha256": "a"*64,
                 "status": "ok", "manifest_status": "ok", "payment_mode": "ecpay_live"}
        deep = build | {"status": "ok", "deep_verified": True,
                        "mismatch_count": 0, "files_verified": 81,
                        "manifest_file_count": 81}
        for drift in ({"version": "1.2.126"},
                      {"source_tree_sha256": "b"*64},
                      {"source_tree_sha256": None},
                      {"source_tree_sha256": ""},
                      {"source_tree_sha256": "not-a-sha256"}):
            def live(path):
                return {"/health/build": build | drift,
                        "/health/artifact?deep=true": deep,
                        "/health/ready": {"status": "ready", "version": "1.2.127"}}[path]
            with self.subTest(drift=drift):
                with mock.patch.object(pub, "live_get", side_effect=live):
                    with self.assertRaisesRegex(
                            ValueError, "DIRECT_DEPLOY_PUBLISHED_BUT_VPS_DEPLOYMENT_NOT_VERIFIED"):
                        pub.verify_target_live(info, attempts=1, interval=0)

    def test_previous_readiness_and_wrong_payment_mode_cannot_pass(self):
        manifest, _, _ = self.sample()
        target = json.loads(manifest)
        build = {
            "artifact_id": target["target_artifact_id"],
            "build_instance_id": target["target_build_instance_id"],
            "version": "1.2.127", "display_version": "v1.2.127",
            "status": "ok", "manifest_status": "ok", "payment_mode": "test_unlock",
            "source_tree_sha256": "a" * 64,
        }
        deep = build | {"deep_verified": True, "mismatch_count": 0,
                        "files_verified": 81, "manifest_file_count": 81}
        states = {"/health/build": build, "/health/artifact?deep=true": deep,
                  "/health/ready": {"status": "ready", "version": "1.2.126"}}
        with self.assertRaisesRegex(ValueError, "LIVE_READINESS_MISMATCH"):
            pub.verify_target_live(target, getter=states.__getitem__,
                                   attempts=1, payment_mode="test_unlock")
        states["/health/ready"]["version"] = "1.2.127"
        with self.assertRaisesRegex(ValueError, "LIVE_PAYMENT_MODE_MISMATCH"):
            pub.verify_target_live(target, getter=states.__getitem__, attempts=1)
        self.assertEqual(pub.verify_target_live(target, getter=states.__getitem__,
                                               attempts=1, payment_mode="test_unlock")["managed_files"], 81)

    def test_future_signed_releases_require_both_target_pins(self):
        manifest, _, _ = self.sample()
        for field in ("expected_managed_file_count", "expected_source_tree_sha256"):
            target = json.loads(manifest)
            del target[field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "SIGNED_TARGET_"):
                pub.verify_target_live(target, attempts=1)

    def test_candidate_acceptance_is_bound_to_the_signed_release(self):
        manifest, _, _ = self.sample()
        target = json.loads(manifest)
        evidence = {
            "schema": "judun-candidate-acceptance-v1",
            **{key: target[key] for key in ("release_id", "base_artifact_id",
                "target_artifact_id", "target_build_instance_id", "payload_sha256")},
            "source_tree_sha256": target["expected_source_tree_sha256"],
            "managed_file_count": target["expected_managed_file_count"],
            "checks": {name: {"status": "pass", "evidence": "fixture evidence"}
                       for name in pub.CANDIDATE_CHECKS},
        }
        receipt = json.dumps(evidence).encode()
        target["candidate_acceptance_sha256"] = sha256(receipt).hexdigest()
        pub.check_candidate_receipt(target, receipt)
        with self.assertRaisesRegex(ValueError, "CANDIDATE_ACCEPTANCE_SHA_MISMATCH"):
            pub.check_candidate_receipt(target, receipt + b" ")
        for invalid, expected_error in (
            (evidence | {"target_build_instance_id": "different-instance"},
             "CANDIDATE_ACCEPTANCE_IDENTITY_MISMATCH"),
            (evidence | {"checks": {}}, "CANDIDATE_ACCEPTANCE_CHECK_MISSING"),
            (evidence | {"checks": evidence["checks"] | {
                "rollback_after_migration": {"status": "fail", "evidence": "old app cannot read DB"}
            }}, "CANDIDATE_ACCEPTANCE_CHECK_NOT_PASSED"),
        ):
            invalid_receipt = json.dumps(invalid).encode()
            with self.subTest(error=expected_error), self.assertRaisesRegex(ValueError, expected_error):
                pub.check_candidate_receipt(
                    target | {"candidate_acceptance_sha256": sha256(invalid_receipt).hexdigest()},
                    invalid_receipt,
                )

    def test_non_v189_cannot_use_unsigned_candidate_receipt(self):
        manifest, _, _ = self.sample()
        with self.assertRaisesRegex(ValueError, "SIGNED_CANDIDATE_ACCEPTANCE_REQUIRED"):
            pub.expected_candidate_receipt(json.loads(manifest), allow_v189=True)

    def test_legacy_exemption_applies_only_to_the_existing_channel(self):
        target = json.loads((Path(__file__).resolve().parents[1] / "channel/stable.json").read_bytes())
        # The fixture is the historical manifest, not the moving stable
        # channel once a newer signed release has been installed.
        if target["release_id"] != pub.V189_RELEASE["release_id"]:
            target = pub.V189_RELEASE.copy()
        self.assertEqual(pub.expected_target_integrity(target), (98, pub.V189_TREE_SHA256))
        self.assertIsNone(pub.expected_candidate_receipt(target, allow_v189=True))
        for changed_fields in (
            {"base_artifact_id": "JUDUN-1.2.187-OTHER"},
            {"target_artifact_id": "JUDUN-1.2.189-OTHER"},
            {"target_build_instance_id": "1.2.189-OTHER"},
            {"expected_managed_file_count": 95},
            {"expected_source_tree_sha256": pub.V189_TREE_SHA256},
        ):
            with self.subTest(changed_fields=changed_fields), self.assertRaisesRegex(
                    ValueError, "SIGNED_CANDIDATE_ACCEPTANCE_REQUIRED"):
                pub.expected_candidate_receipt(target | changed_fields, allow_v189=True)

    def test_post_publish_old_live_version_cannot_claim_success(self):
        m, sig, cms = self.sample()
        info = json.loads(m)
        with mock.patch.object(pub, "live_get", return_value={
                "artifact_id": info["base_artifact_id"]}):
            with self.assertRaisesRegex(
                    ValueError, "DIRECT_DEPLOY_PUBLISHED_BUT_VPS_DEPLOYMENT_NOT_VERIFIED"):
                pub.verify_target_live(info, attempts=2, interval=0)


    def test_git_blob_oid_matches_git_and_is_sensitive_to_byte_changes(self):
        data = b"judun-release-verification\n"
        expected = subprocess.run(["git", "hash-object", "--stdin"],
                                  input=data, stdout=subprocess.PIPE,
                                  check=True).stdout.decode().strip()
        self.assertEqual(pub.git_blob_oid(data), expected)
        self.assertNotEqual(pub.git_blob_oid(data + b"!"), expected)

    def test_interrupted_publication_recovery_requires_exact_signed_tree(self):
        m, signature, cms = self.sample()
        target = json.loads(m)
        expected = {
            target["payload_path"]: cms,
            "channel/stable.json.sig.b64": signature,
            "channel/stable.json": m,
        }
        observed = []
        def read_only(method, endpoint, token, body=None, missing_ok=False):
            observed.append((method, endpoint))
            self.assertEqual(method, "GET")
            if endpoint.startswith("/contents/keys/"):
                return {"content": base64.b64encode(self.pubkey.read_bytes()).decode()}
            if endpoint == "/git/ref/heads/main":
                return {"object": {"sha": "a"*40}}
            if endpoint.startswith("/contents/channel/stable.json"):
                return {"content": base64.b64encode(m).decode()}
            if endpoint == "/git/commits/" + "a"*40:
                return {"tree": {"sha": "b"*40}}
            if endpoint.startswith("/git/trees/"):
                return {"truncated": False, "tree": [
                    {"path": name, "sha": pub.git_blob_oid(raw), "type": "blob",
                     "mode": "100644"} for name, raw in expected.items()]}
            raise AssertionError("unexpected URL: " + endpoint)
        with mock.patch.object(pub, "github", side_effect=read_only):
            self.assertEqual(pub.verify_published_channel(
                m, signature, cms, target, self.pubkey), "a"*40)
        self.assertEqual(len(observed), 5)
        # Any replaced CMS bytes must prevent a false-positive recovery.
        with mock.patch.object(pub, "github", side_effect=read_only):
            with self.assertRaisesRegex(
                    ValueError, "DIRECT_DEPLOY_RECOVERY_SIGNED_BYTES_NOT_IN_SAME_COMMIT"):
                pub.verify_published_channel(
                    m, signature, base64.b64encode(b"wrong cms"), target,
                    self.pubkey)

    def test_interrupted_recovery_rejects_wrong_channel_without_git_writes(self):
        m, signature, cms = self.sample()
        target = json.loads(m)
        def wrong_channel(method, endpoint, token, body=None, missing_ok=False):
            self.assertEqual(method, "GET")
            if endpoint.startswith("/contents/keys/"):
                return {"content": base64.b64encode(self.pubkey.read_bytes()).decode()}
            if endpoint == "/git/ref/heads/main":
                return {"object": {"sha": "a"*40}}
            if endpoint.startswith("/contents/channel/stable.json"):
                return {"content": base64.b64encode(b"not matching").decode()}
            raise AssertionError(endpoint)
        with mock.patch.object(pub, "github", side_effect=wrong_channel):
            with self.assertRaisesRegex(ValueError,
                                       "DIRECT_DEPLOY_RECOVERY_SIGNED_CHANNEL_MISMATCH"):
                pub.verify_published_channel(m, signature, cms, target,
                                             self.pubkey)

