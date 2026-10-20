"""P3 offline safety contracts for original FastAPI source patch staging."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patch_authoritative_app import apply_app_patch, write_staging
from patch_paid_preference import OLD, NEW, OLD_COMPLETION, NEW_COMPLETION


def sample_app() -> bytes:
    code = '''from __future__ import annotations
class FastAPI:
    pass
app = FastAPI()
def receive_status():
    return True
@app.get("/status/{job_id}")
def get_status(job_id):
    return None
'''
    # Patch occurs INSIDE original Python triple-quoted HTML/JS, not Python
    # checkout logic. The patcher MUST parse both Python versions successfully.
    code = code.replace("class FastAPI:\n    pass\n",
        "class FastAPI:\n    def get(self, path):\n        return lambda fn: fn\n")
    html = (
        'GLOBAL_JS = r"""<!DOCTYPE html><html lang="zh-Hant">'
        '<header>用專業守護家</header><style>h1{color:navy}</style><script>\n'
        'window.unlockTier = function(btn, jobId, tier) {\n' + OLD +
        '\n};\nfunction checkMicroStatus(jobId, activeBtn, preferredSectionId) {\n'
        'const task = {state: \'completed\'};\n'
        + OLD_COMPLETION +
        '\n console.log(jobId);\n}\n</script></html>"""\n'
    )
    # Use a triple-double-quoted Python literal with single JS literals.
    return (code + html).encode("utf-8")


class SourcePatchTests(unittest.TestCase):
    def test_byte_exact_source_and_python_parser_preserved(self):
        raw = sample_app()
        sha = hashlib.sha256(raw).hexdigest()
        patched, meta = apply_app_patch(raw, sha)
        self.assertEqual(
            patched, raw.decode().replace(OLD, NEW, 1).replace(
                OLD_COMPLETION, NEW_COMPLETION, 1
            ).encode(),
        )
        compile(patched, "<patched>", "exec")
        self.assertTrue(meta["fastapi_route_preserved"])
        self.assertEqual(meta["replacements"], 2)
        self.assertFalse(meta["production_deployed"])

    def test_refuses_source_drift_and_invalid_source(self):
        raw = sample_app()
        sha = hashlib.sha256(raw).hexdigest()
        for source, h in [
            (raw, "0"*64),
            (raw, ""),
            (raw.replace(OLD.encode(), b"const preferred = 'report-five-themes';"), sha),
            (raw + OLD.encode(), sha),
            (raw.replace(OLD_COMPLETION.encode(), b"if (data.ok) {"), sha),
            (b"<html>" + raw, sha),
        ]:
            with self.subTest(size=len(source)):
                with self.assertRaises(ValueError):
                    apply_app_patch(source, h)

    def test_refuses_js_only_page_and_python_syntax_error(self):
        raw = sample_app()
        source = raw.replace(b"GLOBAL_JS = r", b"", 1)
        with self.assertRaises(ValueError):
            apply_app_patch(source, hashlib.sha256(source).hexdigest())
        source = raw.replace(b"from __future__ import annotations\n", b"if:\n", 1)
        with self.assertRaises(ValueError):
            apply_app_patch(source, hashlib.sha256(source).hexdigest())

    def test_staging_refuses_overwrite_and_creates_restricted_file(self):
        raw = sample_app()
        patched, _ = apply_app_patch(raw, hashlib.sha256(raw).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root/"original.py"
            source.write_bytes(raw)
            output = root/"staging"/"app.py"
            write_staging(source, output, patched)
            self.assertEqual(output.read_bytes(), patched)
            self.assertEqual(source.read_bytes(), raw)
            with self.assertRaises(ValueError):
                write_staging(source, output, patched)
            with self.assertRaises(ValueError):
                write_staging(source, source, patched)
            with self.assertRaises(ValueError):
                write_staging(source, root/"candidate.bin", patched)

    def test_does_not_cross_js_function_boundary(self):
        raw = sample_app()
        s = raw.decode().replace("window.unlockTier = function(btn, jobId, tier) {",
            "window.unlockTier = function(btn, jobId, tier) {\n"
            "function unexpectedNamedFunction() {}")
        content = s.encode()
        with self.assertRaises(ValueError):
            apply_app_patch(content, hashlib.sha256(content).hexdigest())


if __name__ == "__main__":
    unittest.main()
