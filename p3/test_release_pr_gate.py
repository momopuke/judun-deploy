"""Exercise the trusted PR gate against real disposable Git objects."""

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest import TestCase, mock

import release_pr_gate as gate


class ReleasePullRequestGateTests(TestCase):
    def setUp(self):
        sandbox = tempfile.TemporaryDirectory()
        self.addCleanup(sandbox.cleanup)
        self.directory = Path(sandbox.name)
        self.repo = self.directory / "repo"
        self.repo.mkdir()
        old_cwd = Path.cwd()
        self.addCleanup(os.chdir, old_cwd)
        os.chdir(self.repo)
        gate.git("init", "-q", "-b", "main")
        gate.git("config", "user.email", "gate@example.invalid")
        gate.git("config", "user.name", "Disposable gate test")
        self.key = self.directory / "signing.pem"
        self.public = self.directory / "public.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "ED25519", "-out", self.key], check=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", self.key, "-pubout", "-out", self.public], check=True,
        )
        public = self.public.read_bytes()
        pin = mock.patch.object(gate.release, "RELEASE_KEY_SHA256", hashlib.sha256(public).hexdigest())
        pin.start()
        self.addCleanup(pin.stop)
        self.write(gate.KEY, public)
        self.base_metadata = self.release(190)
        self.base = self.commit("Existing signed release")

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def commit(self, message):
        gate.git("add", "--all")
        gate.git("commit", "-qm", message)
        return gate.git("rev-parse", "HEAD").decode().strip()

    def release(self, version, **fields):
        cms = f"nonproduction synthetic content {version}".encode()
        metadata = {
            "schema": "judun-autodeploy-v1", "release_id": f"v1.2.{version}-test-fixture",
            "base_artifact_id": f"JUDUN-1.2.{version - 1}-TESTFIXTURE",
            "target_artifact_id": f"JUDUN-1.2.{version}-TESTFIXTURE",
            "target_build_instance_id": f"1.2.{version}-TESTFIXTURE",
            "expected_display_version": f"v1.2.{version}",
            "expected_managed_file_count": 98, "expected_source_tree_sha256": "a" * 64,
            "candidate_acceptance_sha256": "b" * 64,
            "payload_path": f"releases/v1.2.{version}-test.cms.b64",
            "payload_sha256": hashlib.sha256(cms).hexdigest(), "noop": False,
        } | fields
        self.write(gate.MANIFEST, (json.dumps(metadata) + "\n").encode())
        signature = subprocess.check_output([
            "openssl", "pkeyutl", "-sign", "-inkey", self.key, "-rawin", "-in", gate.MANIFEST,
        ])
        self.write(gate.SIGNATURE, base64.b64encode(signature))
        self.write(metadata["payload_path"], base64.b64encode(cms))
        return metadata

    def verify(self, head, *, base=None, same_repository=True):
        return gate.classify_and_verify(base or self.base, head, same_repository, check_live=False)

    def test_signed_release_survives_unrelated_main_changes(self):
        gate.git("checkout", "-qb", "candidate", self.base)
        self.release(191)
        head = self.commit("Candidate")
        gate.git("checkout", "-q", "main")
        self.write("README.md", b"Unrelated documentation")
        newer_base = self.commit("Docs")
        self.assertEqual(self.verify(head, base=newer_base), "signed release PR")

    def test_unrelated_fork_pr_only_passes_non_release_scope(self):
        self.write("README.md", b"Unrelated documentation")
        self.assertEqual(self.verify(self.commit("Docs"), same_repository=False), "non-release PR")

    def test_valid_release_pr_from_fork_rejects(self):
        self.release(191)
        with self.assertRaisesRegex(ValueError, "PR_RELEASE_FORK_FORBIDDEN"):
            self.verify(self.commit("Candidate"), same_repository=False)

    def test_release_cannot_mix_other_changes_or_edit_key_alone(self):
        self.release(191)
        self.write(".github/workflows/foreign.yml", b"Not part of a release")
        with self.assertRaisesRegex(ValueError, "PR_RELEASE_FILE_SET"):
            self.verify(self.commit("Mixed"))
        gate.git("reset", "--hard", self.base)
        self.write(gate.KEY, b"changed")
        with self.assertRaisesRegex(ValueError, "PR_RELEASE_FILE_SET"):
            self.verify(self.commit("Key change"))

    def test_missing_signature_or_tampered_payload_rejects(self):
        metadata = self.release(191)
        self.write(gate.SIGNATURE, (self.directory / "repo" / gate.SIGNATURE).read_bytes()[:-4])
        self.write(metadata["payload_path"], base64.b64encode(b"changed"))
        with self.assertRaisesRegex(ValueError, "CMS_PAYLOAD_SHA"):
            self.verify(self.commit("Tampered"))
        gate.git("reset", "--hard", self.base)
        self.release(191)
        gate.git("checkout", self.base, "--", gate.SIGNATURE)
        with self.assertRaisesRegex(ValueError, "PR_RELEASE_FILE_SET"):
            self.verify(self.commit("Missing signature change"))

    def test_wrong_signer_and_bad_qa_hash_reject(self):
        self.release(191, candidate_acceptance_sha256="bad")
        with self.assertRaisesRegex(ValueError, "SIGNED_CANDIDATE_ACCEPTANCE_REQUIRED"):
            self.verify(self.commit("Unattested"))
        gate.git("reset", "--hard", self.base)
        subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", self.key], check=True)
        self.release(191)
        with self.assertRaisesRegex(ValueError, "ED25519_SIGNATURE_INVALID"):
            self.verify(self.commit("Wrong signer"))

    def test_concurrent_release_base_rejects(self):
        gate.git("checkout", "-qb", "candidate", self.base)
        self.release(192, base_artifact_id=self.base_metadata["target_artifact_id"])
        head = self.commit("Candidate")
        gate.git("checkout", "-q", "main")
        self.release(191)
        with self.assertRaisesRegex(ValueError, "PR_RELEASE_STALE_SIGNED_BASE"):
            self.verify(head, base=self.commit("Competing release"))

    def test_prod_identity_verified_before_release_gate_passes(self):
        self.release(191)
        head = self.commit("Candidate")
        with mock.patch.object(gate.release, "verify_target_live",
                               side_effect=ValueError("Synthetic unavailable live base")) as live:
            with self.assertRaisesRegex(ValueError, "unavailable live base"):
                gate.classify_and_verify(self.base, head, True)
        live.assert_called_once_with(self.base_metadata, attempts=1)

    def test_signed_pr_without_verified_oidc_staging_fails_before_merge(self):
        self.release(191)
        head = self.commit("Signed candidate needing authenticated stage")
        with mock.patch.object(
            gate.oidc, "verify_candidate",
            side_effect=ValueError("JUDUN_STAGE_OIDC_UNVERIFIED"),
        ):
            with self.assertRaisesRegex(ValueError, "OIDC_UNVERIFIED"):
                gate.classify_and_verify(self.base, head, True,
                                         check_live=False, check_stage=True)

    def test_signed_pr_rejects_wrong_oidc_staging_candidate(self):
        self.release(191)
        head = self.commit("Signed candidate must be on stage")
        with mock.patch.object(
            gate.oidc, "verify_candidate",
            side_effect=ValueError("DIRECT_DEPLOY_LIVE_TARGET_BUILD_MISMATCH"),
        ) as stage:
            with self.assertRaisesRegex(ValueError, "BUILD_MISMATCH"):
                gate.classify_and_verify(self.base, head, True,
                                         check_live=False, check_stage=True)
        stage.assert_called_once()
        self.assertEqual(stage.call_args.args[0]["expected_display_version"], "v1.2.191")

    def test_signed_pr_passes_only_after_oidc_staging_health(self):
        self.release(191)
        head = self.commit("Real candidate preflight fixture")
        with mock.patch.object(gate.oidc, "verify_candidate") as stage:
            self.assertEqual(gate.classify_and_verify(
                self.base, head, True, check_live=False, check_stage=True,
            ), "signed release PR")
        self.assertEqual(stage.call_args.args[0]["expected_display_version"], "v1.2.191")

    def test_nonrelease_pr_not_blocked_by_missing_oidc_gateway(self):
        self.write("README.md", b"Docs-only change requires no staging network")
        head = self.commit("Docs")
        with mock.patch.object(gate.oidc, "verify_candidate") as stage:
            self.assertEqual(gate.classify_and_verify(
                self.base, head, True, check_live=False, check_stage=True,
            ), "non-release PR")
        stage.assert_not_called()

    def test_workflow_reports_on_event_head_and_rejects_newer_push(self):
        gate.git("checkout", "-qb", "candidate", self.base)
        self.write("README.md", b"Unrelated documentation")
        head = self.commit("Docs")
        gate.git("update-ref", "refs/pull/24/head", head)
        gate.git("remote", "add", "origin", self.repo)
        event = self.directory / "event.json"
        event.write_text(json.dumps({"pull_request": {
            "number": 24,
            "head": {"sha": head, "repo": {"full_name": "synthetic/fork"}},
            "base": {"ref": "main"},
        }}))
        with (
            mock.patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event),
                                        "GITHUB_REPOSITORY": gate.release.REPO,
                                        "GITHUB_RUN_ID": "1234",
                                        "GITHUB_TOKEN": "synthetic-workflow-token"}),
            mock.patch.object(gate.release, "github") as status,
            mock.patch("builtins.print"),
        ):
            self.assertEqual(gate.run(), 0)
            gate.git("update-ref", "refs/pull/24/head", self.base)
            self.assertEqual(gate.run(), 1)
        self.assertEqual([call.args[:2] for call in status.call_args_list],
                         [("POST", "/statuses/" + head)] * 4)
        self.assertEqual([call.args[3]["state"] for call in status.call_args_list],
                         ["pending", "success", "pending", "failure"])
        self.assertTrue(all(call.args[3]["context"] == gate.CONTEXT
                            for call in status.call_args_list))
