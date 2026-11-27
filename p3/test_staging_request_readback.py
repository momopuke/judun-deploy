"""Regression tests for issuing a receipt only after a stable live readback."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import staging_request_readback as readback


class StagingReadbackTest(unittest.TestCase):
    commit = "a" * 40
    live = {"version": "v1.2.189", "managed_files": 98, "payment_mode": "test_unlock"}

    qa = {"native_qa_status": "PASS", "native_qa_receipt_sha256": "a" * 64,
          "native_qa_file_count": 98}

    def observe(self, readings, *, latest=None, elapsed=65, retry_checks=0):
        # The real client returns fresh dicts including the summary on every call.
        readings = [{"native_qa": dict(self.qa), **x} if isinstance(x, dict) else x
                    for x in readings]
        with ExitStack() as stack:
            temp = Path(stack.enter_context(TemporaryDirectory()))
            stack.enter_context(patch.dict(os.environ, RUNNER_TEMP=str(temp), GITHUB_RUN_ID="123"))
            stack.enter_context(patch.object(readback, "signed_target", return_value={"expected_managed_file_count": 98}))
            stack.enter_context(patch.object(readback.oidc, "verify_candidate", side_effect=readings))
            stack.enter_context(patch.object(readback.agent, "request_commit", return_value=latest or self.commit))
            stack.enter_context(patch.object(readback.time, "sleep"))
            stack.enter_context(patch.object(readback.time, "monotonic", side_effect=[0] + [0] * retry_checks + [0, elapsed]))
            path = temp / "judun-staging-readback.json"
            try:
                readback.attest(self.commit)
            except (ValueError, OSError):
                self.assertFalse(path.exists())
                raise
            return json.loads(path.read_text())

    def test_stable_two_pass_receipt(self):
        result = self.observe([self.live, self.live])
        self.assertEqual(result["candidate_commit"], self.commit)
        self.assertEqual(result["first"], result["second"])
        self.assertEqual(result["observed_seconds"], 65)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["native_qa"], self.qa)
        self.assertEqual(result["native_qa_first"], self.qa)
        self.assertEqual(result["native_qa_second"], self.qa)

    def test_changed_native_qa_is_pending_not_health_failure(self):
        other = {**self.qa, "native_qa_receipt_sha256": "b" * 64}
        result = self.observe([self.live, {**self.live, "native_qa": other}])
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["native_qa"]["native_qa_status"], "PENDING")
        self.assertEqual(result["native_qa_first"], self.qa)
        self.assertEqual(result["native_qa_second"], other)

    def test_no_receipt_for_drift_or_short_interval(self):
        for readings, elapsed in (([self.live, {}], 65), ([self.live, self.live], 59)):
            with self.subTest(elapsed=elapsed), self.assertRaisesRegex(ValueError, "interval"):
                self.observe(readings, elapsed=elapsed)

    def test_superseded_request_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "superseded"):
            self.observe([self.live, self.live], latest="b" * 40)

    def test_failed_second_read_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "verification failed"):
            self.observe([self.live, ValueError("verification failed")])

    def test_gateway_denial_requires_two_subsequent_verified_readings(self):
        url = readback.oidc.GATEWAY + readback.oidc.PREFIX + "/health/build"
        denied = readback.HTTPError(url, 403, "Forbidden", {}, None)
        result = self.observe([denied, self.live, self.live], retry_checks=1)
        self.assertEqual(result["result"], "PASS")
        with self.assertRaises(readback.HTTPError):
            self.observe([denied, denied, denied], retry_checks=2)

    def test_token_issuer_denial_fails_immediately(self):
        denied = readback.HTTPError("https://pipelines.actions.githubusercontent.com/", 403,
                                    "Forbidden", {}, None)
        with self.assertRaises(readback.HTTPError):
            self.observe([denied])

    def test_invalid_oidc_bootstrap_fails_immediately(self):
        with self.assertRaises(readback.oidc.Denied):
            self.observe([readback.oidc.Denied("OIDC_RUNNER_BOOTSTRAP_MISSING")])

    def test_feature_summary_is_independent_of_health_pass(self):
        r = self.observe([self.live, self.live])
        self.assertEqual(r["feature_qa"]["feature_qa_status"], "PENDING")
        self.assertEqual(r["feature_qa_builds"], [])

    def test_feature_double_readback_and_stale_hash(self):
        target = {"target_artifact_id": "JUDUN-1.2.195-FIXTURE",
                  "target_build_instance_id": "1.2.195-FIXTURE",
                  "expected_display_version": "v1.2.195",
                  "expected_source_tree_sha256": "b"*64,
                  "expected_managed_file_count": 98}
        b = {"status": "ok", "manifest_status": "ok", "payment_mode": "test_unlock",
             "version": "1.2.195", "artifact_id": target["target_artifact_id"],
             "build_instance_id": target["target_build_instance_id"],
             "source_tree_sha256": "b"*64, **self.qa,
             "feature_qa_status": "EVIDENCE_READY_NOT_RELEASE_APPROVAL",
             "feature_receipt_sha256": "c"*64, "feature_plan_sha256": "d"*64}
        a, observed = readback.feature_readback(target, [b,b], [b,b], self.qa)
        self.assertEqual(a["feature_receipt_sha256"], "c"*64)
        self.assertEqual(len(observed), 2)
        bad = {**b, "feature_receipt_sha256": "e"*64}
        a, observed = readback.feature_readback(target, [b,b], [b,bad], self.qa)
        self.assertEqual(a["feature_qa_status"], "PENDING")
        self.assertEqual(observed, [])

    def test_malformed_commit_rejected_before_network(self):
        with patch.object(readback, "signed_target") as fetch, self.assertRaises(ValueError):
            readback.attest("main")
        fetch.assert_not_called()
