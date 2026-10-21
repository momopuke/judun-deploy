"""No-network regression for live-read-only HTTPS receiver preflight."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from https_receiver_live_preflight import audit_against_current_live
from test_https_receiver_bundle_audit import (
    BASE, TARGET, FORMAL, VERSION, make_members, save,
)


def response(path: str):
    if path == "/health/build":
        return {"status": "OK", "data": {
            "status": "ok", "version": "1.2.114", "artifact_id": BASE,
        }}
    if path == "/health/artifact?deep=true":
        return {"status": "OK", "data": {
            "status": "ok", "artifact_id": BASE, "version": "1.2.114",
            "deep_verified": True, "mismatch_count": 0,
            "files_verified": 81, "manifest_file_count": 81,
            "formal_evidence_sha256": FORMAL, "source_tree_sha256": "b" * 64,
        }}
    raise AssertionError("Unexpected URL attempted: " + path)


class LiveHttpsV3PreflightTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.bundle = Path(self.folder.name) / "valid.zip"
        save(self.bundle, make_members())

    def run_probe(self, response_fn=response):
        with patch("https_receiver_live_preflight.public_json", side_effect=response_fn) as get:
            outcome = audit_against_current_live(
                self.bundle, expected_target_artifact=TARGET,
                expected_version=VERSION,
            )
            self.assertEqual(
                [c.args[0] for c in get.call_args_list],
                ["/health/build", "/health/artifact?deep=true",
                 "/health/build", "/health/artifact?deep=true"],
            )
            return outcome

    def test_works_only_with_both_fresh_exact_live_checks(self):
        result = self.run_probe()
        self.assertTrue(result["live_deep_verified"])
        self.assertTrue(result["read_only_public_snapshot_double_checked"])
        self.assertTrue(result["same_deep_manifest_fields_before_after"])
        self.assertFalse(result["independent_vps_disk_sha_verified"])
        self.assertTrue(result["requires_receiver_atomic_base_match_at_apply"])
        self.assertFalse(result["production_upload_authorized_by_this_probe"])
        self.assertEqual(result["verified_live_artifact"], BASE)
        self.assertEqual(result["next_step"], "AUTHORIZED_RECEIVER_UPLOAD_NOT_PERFORMED")
        self.assertFalse(result["actual_vps_deployment"])

    def test_blocks_stale_or_partial_live_evidence(self):
        for key, value in (
            ("artifact_id", "JUDUN-1.2.113-STALE"),
            ("deep_verified", False),
            ("mismatch_count", 1),
            ("formal_evidence_sha256", "d" * 64),
        ):
            def bad_response(path):
                r = response(path)
                if path.endswith("deep=true"):
                    r["data"][key] = value
                return r
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.run_probe(bad_response)

    def test_deep_snapshot_must_include_all_files_and_tree_sha(self):
        for key, value in (
            ("source_tree_sha256", None),
            ("source_tree_sha256", "bad"),
            ("files_verified", 80),
            ("manifest_file_count", 80),
            ("version", "1.2.113"),
            ("deep_verified", "true"),
        ):
            def corrupt(path):
                r = response(path)
                if path.endswith("deep=true"):
                    r["data"][key] = value
                return r
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, "LIVE_IDENTITY_OR_INTEGRITY_DRIFT"):
                    self.run_probe(corrupt)

    def test_unreachable_live_does_not_accept_local_zip(self):
        def unavailable(path):
            return {"status": "NOT_VERIFIED"}
        with self.assertRaisesRegex(ValueError, "FRESH_LIVE_IDENTITY_UNAVAILABLE"):
            self.run_probe(unavailable)

    def test_blocks_concurrent_release_switch_during_local_zip_hash(self):
        calls = {"build": 0}

        def switched_after_first_read(path):
            if path == "/health/build":
                calls["build"] += 1
                if calls["build"] == 2:
                    return {"status": "OK", "data": {
                        "version": "1.2.115", "artifact_id": TARGET,
                    }}
            return response(path)

        with self.assertRaisesRegex(ValueError, "LIVE_CHANGED_DURING_PREFLIGHT"):
            self.run_probe(switched_after_first_read)

    def test_final_deep_endpoint_unavailable_fails_closed(self):
        calls = {"deep": 0}

        def deep_disappears(path):
            if path.endswith("deep=true"):
                calls["deep"] += 1
                if calls["deep"] == 2:
                    return {"status": "NOT_VERIFIED"}
            return response(path)

        with self.assertRaisesRegex(ValueError, "FINAL_DEEP_INTEGRITY_UNVERIFIED"):
            self.run_probe(deep_disappears)

    def test_same_artifact_but_changed_source_tree_hash_blocks(self):
        calls = {"deep": 0}

        def same_artifact_new_tree(path):
            r = response(path)
            if path.endswith("deep=true"):
                calls["deep"] += 1
                if calls["deep"] == 2:
                    r["data"]["source_tree_sha256"] = "d" * 64
            return r

        with self.assertRaisesRegex(ValueError, "DEEP_SNAPSHOT_CHANGED_DURING_PREFLIGHT"):
            self.run_probe(same_artifact_new_tree)

    def test_final_deep_file_count_and_formal_snapshot_drift_block(self):
        for field, new_value in (
            ("formal_evidence_sha256", "d" * 64),
            ("files_verified", 80),
            ("manifest_file_count", 80),
        ):
            calls = {"deep": 0}

            def changed(path):
                r = response(path)
                if path.endswith("deep=true"):
                    calls["deep"] += 1
                    if calls["deep"] == 2:
                        r["data"][field] = new_value
                return r

            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_probe(changed)

    def test_initial_split_brain_build_versions_are_rejected(self):
        def contradictory(path):
            r = response(path)
            if path == "/health/build":
                r["data"]["display_version"] = "v1.2.115"
            return r

        with self.assertRaisesRegex(ValueError, "FRESH_LIVE_IDENTITY_UNAVAILABLE"):
            self.run_probe(contradictory)

    def test_final_split_brain_build_versions_are_rejected(self):
        calls = {"build": 0}

        def contradictory_final(path):
            r = response(path)
            if path == "/health/build":
                calls["build"] += 1
                if calls["build"] == 2:
                    r["data"]["display_version"] = "1.2.115"
            return r

        with self.assertRaisesRegex(ValueError, "LIVE_CHANGED_DURING_PREFLIGHT"):
            self.run_probe(contradictory_final)

    def test_target_mismatch_blocks_even_with_clean_live(self):
        with patch("https_receiver_live_preflight.public_json", side_effect=response):
            with self.assertRaisesRegex(ValueError, "PACKAGE_TARGET_IDENTITY_MISMATCH"):
                audit_against_current_live(
                    self.bundle,
                    expected_target_artifact="JUDUN-1.2.999-UNAUTHORIZED",
                    expected_version=VERSION,
                )


if __name__ == "__main__":
    unittest.main()
