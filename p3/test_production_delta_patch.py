"""Offline acceptance for signed v1.2.115 P3 delta. No secrets or live writes."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from production_delta_patch import (
    BASE_ARTIFACT, BASE_VERSION, TARGET_ARTIFACT, TARGET_SIGNATURE,
    TARGET_VERSION, OLD, OLD_COMPLETION, NEW, NEW_COMPLETION,
    computed_tree_sha, computed_live_tree_sha, inspect_managed_source, patch_app, plan_update, sha,
)

def fixture(root):
    script = (
        'class FastAPI:\n'
        '    def get(self, path):\n'
        '        return lambda fn: fn\n'
        'app = FastAPI()\n'
        '@app.get("/status/{job_id}")\n'
        'def get_status(job_id):\n'
        '    return None\n'
        "APP_VERSION = '1.2.114'\n"
        "RELEASE_REVISION = '1.2.114'\n"
        "BUILD_SIGNATURE = 'JUDUN_1.2.114_EXPANSION_RESILIENCE_20261017'\n"
        "GLOBAL_JS = r'''window.unlockTier = function(tier) {\n"
        + OLD
        + "\n};\nfunction checkMicroStatus() {\n"
        + OLD_COMPLETION
        + "\n}\n}'''\n"
    ).encode("utf-8")
    (root / "app.py").write_bytes(script)
    rows = [{"path": "app.py", "size": len(script), "sha256": sha(script)}]
    for n in range(78):
        payload = ("safe fixture " + str(n)).encode()
        name = "fixture_%02d.txt" % n
        (root / name).write_bytes(payload)
        rows.append({"path": name, "size": len(payload), "sha256": sha(payload)})
    m = {"schema": "judun.deploy-manifest.v1",
         "version": BASE_VERSION,
         "artifact_id": BASE_ARTIFACT,
         "source_tree_sha256": computed_live_tree_sha(rows),
         "formal_evidence_sha256": "c" * 64, "files": rows}
    (root / "DEPLOY_MANIFEST.json").write_text(json.dumps(m), encoding="utf-8")
    return script

class DeltaReleaseTests(unittest.TestCase):
    def test_windows_build_payload_source_tree_golden_vector(self):
        # Independent reference computed from the archived original
        # BUILD_PAYLOAD.ps1: path, NUL, byte count, NUL, SHA, terminal LF.
        records = [
            {"path": "data/seed.txt", "size": 17, "sha256": "b" * 64},
            {"path": "app.py", "size": 321, "sha256": "a" * 64},
        ]
        self.assertEqual(
            computed_tree_sha(records),
            "38449d839681a109ba7aaed83385e58a1c878f4dc3395b53e0ab477ce674818e",
        )
        self.assertEqual(computed_tree_sha(records), computed_tree_sha(records[::-1]))
        old_broken = "\\n".join(
            f"{r['path']}\\0{r['sha256']}\\0{r['size']}"
            for r in sorted(records, key=lambda r: r["path"])
        )
        self.assertNotEqual(computed_tree_sha(records), sha(old_broken.encode("utf-8")))

    def test_live_v114_manifest_uses_distinct_tab_sha_size_tree(self):
        rows = [
            {"path": "data/seed.txt", "size": 17, "sha256": "b" * 64},
            {"path": "app.py", "size": 321, "sha256": "a" * 64},
        ]
        self.assertEqual(
            computed_live_tree_sha(rows),
            "cb6cf77bfaddc4ffc25a57125fbbf4ba60f0ec29977807be296c9cce34d750ee",
        )
        self.assertNotEqual(computed_live_tree_sha(rows), computed_tree_sha(rows))

    def test_dry_run_is_byte_precise_and_preserves_formal_qa(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            before = fixture(root)
            original, meta = inspect_managed_source(root)
            self.assertEqual(original["artifact_id"], BASE_ARTIFACT)
            self.assertEqual(meta, before)
            new_app, manifest_bytes = plan_update(root)
            next_manifest = json.loads(manifest_bytes)
            self.assertEqual(next_manifest["artifact_id"], TARGET_ARTIFACT)
            self.assertEqual(next_manifest["version"], TARGET_VERSION)
            self.assertEqual(next_manifest["formal_evidence_sha256"], "c" * 64)
            self.assertEqual(next_manifest["source_tree_sha256"], computed_live_tree_sha(next_manifest["files"]))
            self.assertEqual(new_app.decode().count(NEW), 1)
            self.assertEqual(new_app.decode().count(NEW_COMPLETION), 1)
            self.assertNotIn(OLD, new_app.decode())
            self.assertNotIn(OLD_COMPLETION, new_app.decode())
            self.assertIn("RELEASE_REVISION = '1.2.115'", new_app.decode())
            self.assertIn(TARGET_SIGNATURE, new_app.decode())
            self.assertEqual((root / "app.py").read_bytes(), before)
            self.assertEqual(json.loads((root / "DEPLOY_MANIFEST.json").read_text())["version"], BASE_VERSION)

    def test_drift_and_wrong_release_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = fixture(root)
            (root / "fixture_01.txt").write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "UNREVIEWED_LIVE_FILE_DRIFT"):
                plan_update(root)
            (root / "fixture_01.txt").write_bytes(b"safe fixture 1")
            with self.assertRaisesRegex(ValueError, "EXPECTED_TWO_UNIQUE_LIVE_JS_STATEMENTS"):
                patch_app(original + ("\n# " + OLD + "\n").encode())
            with self.assertRaisesRegex(ValueError, "RELEASE_METADATA_AST_DRIFT"):
                patch_app(original.replace(b"APP_VERSION = '1.2.114'", b"APP_VERSION = '1.2.113'"))
            bad = json.loads((root / "DEPLOY_MANIFEST.json").read_text())
            bad["artifact_id"] = "JUDUN-1.2.113-OTHER"
            (root / "DEPLOY_MANIFEST.json").write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "LIVE_ARTIFACT_OR_VERSION_MISMATCH"):
                plan_update(root)

if __name__ == "__main__":
    unittest.main()
