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

    def observe(self, readings, *, latest=None, elapsed=65):
        with ExitStack() as stack:
            temp = Path(stack.enter_context(TemporaryDirectory()))
            stack.enter_context(patch.dict(os.environ, RUNNER_TEMP=str(temp), GITHUB_RUN_ID="123"))
            stack.enter_context(patch.object(readback, "signed_target", return_value={}))
            stack.enter_context(patch.object(readback.oidc, "verify_candidate", side_effect=readings))
            stack.enter_context(patch.object(readback.agent, "request_commit", return_value=latest or self.commit))
            stack.enter_context(patch.object(readback.time, "sleep"))
            stack.enter_context(patch.object(readback.time, "monotonic", side_effect=[0, 0, elapsed]))
            path = temp / "judun-staging-readback.json"
            try:
                readback.attest(self.commit)
            except ValueError:
                self.assertFalse(path.exists())
                raise
            return json.loads(path.read_text())

    def test_stable_two_pass_receipt(self):
        result = self.observe([self.live, self.live])
        self.assertEqual(result["candidate_commit"], self.commit)
        self.assertEqual(result["first"], result["second"])
        self.assertEqual(result["observed_seconds"], 65)
        self.assertEqual(result["result"], "PASS")

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

    def test_malformed_commit_rejected_before_network(self):
        with patch.object(readback, "signed_target") as fetch, self.assertRaises(ValueError):
            readback.attest("main")
        fetch.assert_not_called()
