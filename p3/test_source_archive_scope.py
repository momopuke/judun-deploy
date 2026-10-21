"""Synthetic archive tests; no production recipient keys or private app files."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_archive_scope import inspect_source_archive


def build(path: Path, files: list[tuple[str, bytes, str]]):
    with tarfile.open(path, "w:gz") as tar:
        for name, contents, kind in files:
            entry = tarfile.TarInfo(name)
            if kind == "symlink":
                entry.type = tarfile.SYMTYPE
                entry.linkname = "../../etc/shadow"
                tar.addfile(entry)
            else:
                entry.size = len(contents)
                tar.addfile(entry, BytesIO(contents))


PATCH = b"BASE='JUDUN-1.2.113-B64EB3788457';VERSION='1.2.114';SIGNATURE='TEST_RELEASE'\n"


class SourceArchiveScopeTests(unittest.TestCase):
    def test_delta_archive_is_never_claimed_to_contain_authoritative_app(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "delta.tar.gz"
            build(archive, [("apply_resilience.py", PATCH, "file"),
                            ("data_expansion_web.py", b"# source", "file")])
            outcome = inspect_source_archive(
                archive, expected_version="1.2.114",
                required_patch="apply_resilience.py",
            )
            self.assertEqual(outcome["scope"], "DELTA_ONLY_NO_APP_PY")
            self.assertEqual(outcome["declared_version"], "1.2.114")
            self.assertEqual(outcome["declared_base_artifact"], "JUDUN-1.2.113-B64EB3788457")
            self.assertFalse(outcome["original_runtime_source_verified"])

    def test_presence_does_not_authorize_unverified_full_app(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "snapshot.tar.gz"
            build(archive, [("runtime/app.py", b"APP_VERSION='1.2.114'\n", "file")])
            outcome = inspect_source_archive(archive)
            self.assertEqual(outcome["scope"], "APP_PRESENT_UNVERIFIED")
            self.assertFalse(outcome["original_runtime_source_verified"])

    def test_duplicate_member_symlink_or_traversal_must_fail(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "unsafe.tar.gz"
            for members in [
                [("apply_resilience.py", PATCH, "file"),
                 ("apply_resilience.py", PATCH, "file")],
                [("apply_resilience.py", PATCH, "file"),
                 ("steal", b"", "symlink")],
                [("../app.py", b"unsafe", "file")],
                [("app\\evil.py", b"unsafe", "file")],
            ]:
                with self.subTest(members=members):
                    build(archive, members)
                    with self.assertRaisesRegex(ValueError, "UNSAFE_OR_DUPLICATE_MEMBER|LINK_OR_SPECIAL_MEMBER"):
                        inspect_source_archive(archive)

    def test_expected_patch_version_is_not_inferred_from_filename(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "v1.2.114.tar.gz"
            build(archive, [("apply_resilience.py", PATCH, "file")])
            with self.assertRaisesRegex(ValueError, "PATCH_VERSION_MISMATCH"):
                inspect_source_archive(
                    archive, expected_version="1.2.115", required_patch="apply_resilience.py",
                )
            with self.assertRaisesRegex(ValueError, "REQUIRED_PATCH_NOT_IN_ARCHIVE"):
                inspect_source_archive(
                    archive, expected_version="1.2.114", required_patch="apply_wrong.py",
                )

    def test_conflicting_or_nonliteral_patch_version_fails(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "v1.2.114.tar.gz"
            build(archive, [
                ("apply_resilience.py", PATCH, "file"),
                ("apply_other.py", b"VERSION='1.2.112'\n", "file"),
            ])
            with self.assertRaisesRegex(ValueError, "CONFLICTING_PATCH_VERSION"):
                inspect_source_archive(archive)
            build(archive, [("apply_resilience.py", b"VERSION=compute_value()\n", "file")])
            with self.assertRaisesRegex(ValueError, "INVALID_PATCH_METADATA"):
                inspect_source_archive(archive, required_patch="apply_resilience.py")


if __name__ == "__main__":
    unittest.main()
