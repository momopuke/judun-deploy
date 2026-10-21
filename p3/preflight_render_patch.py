"""Offline, SHA-pinned v1.2.120 readiness-render isolation candidate.

Transformation and planning are offline and do not import the application.
The explicit apply entry point requires the original signed-agent context and
checks every managed source file before changing app.py and its manifest.
The real renderer still runs; its disposable smoke case does not search the
production evidence corpus. Other threads/tasks continue normal retrieval.
"""
from __future__ import annotations

import ast
import hashlib
import datetime
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile

BASE_APP_SHA256 = "007c9edc1f8496018d5c9d91183990e2c54c7bf2fc3412a1a29d0798f13c6664"
BASE_VERSION = "1.2.120"
TARGET_VERSION = "1.2.121"
TARGET_SIGNATURE = "JUDUN_1.2.121_ISOLATED_PREFLIGHT_RENDER_20261021"
BASE_ARTIFACT = "JUDUN-1.2.120-79D711A55546"
BASE_TREE_SHA256 = "05699f7711d96800d4bcdf7c5f2cedfd3824f374ef9b3458548bd5741f1a3a46"
TARGET_APP_SHA256 = "a1111db99cb1da112b4f8658257a6a1ada7c10bd3bfc6c2a8c8ac3c4cfdb7243"
TARGET_ARTIFACT = "JUDUN-1.2.121-A1111DB99CB1"
TARGET_INSTANCE = "1.2.121-20261021-PREFLIGHT-A1111DB99CB1"
FORMAL_EVIDENCE_SHA256 = "cb2530901faf1cf044105e83e74ad099ee8c5974fda2bb34307a79257b79dc4d"
SCOPE = "_JUDUN_PREFLIGHT_RENDER_SCOPE"
PRELUDE = (
    "from contextvars import ContextVar as _JudunPreflightContextVar\n"
    "_JUDUN_PREFLIGHT_RENDER_SCOPE = _JudunPreflightContextVar(\n"
    "    'judun_preflight_render', default=False\n"
    ")\n\n"
)
FUNCTION_SHA256 = {
    "public_quote_matches": None,
    "report_renderer_smoke_test": "a31fd6fac8b8976a9874b0ec45cb1bbd09274d2393ec2fae1d48689b85f966df",
}
RENDER_CALL = "        rendered = build_html_report(smoke_job, include_chat=False)"
SCOPED_RENDER = (
    "        _judun_preflight_token = _JUDUN_PREFLIGHT_RENDER_SCOPE.set(True)\n"
    "        try:\n"
    "            rendered = build_html_report(smoke_job, include_chat=False)\n"
    "        finally:\n"
    "            _JUDUN_PREFLIGHT_RENDER_SCOPE.reset(_judun_preflight_token)"
)
MATCH_GUARD = (
    "    if _JUDUN_PREFLIGHT_RENDER_SCOPE.get():\n"
    "        return []\n"
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def transform(source: bytes, *, expected_sha256: str = BASE_APP_SHA256) -> bytes:
    """Fail on drift; return new bytes without writing any file.

    The optional digest exists for synthetic fixtures. Production callers must
    always use the default pinned digest and the original signed release agent.
    """
    if not source or len(source) > 16_000_000 or sha(source) != expected_sha256:
        raise ValueError("CURRENT_APP_SHA_MISMATCH")
    text = source.decode("utf-8")
    if SCOPE in text or "_JudunPreflightContextVar" in text:
        raise ValueError("PREFLIGHT_SCOPE_ALREADY_PRESENT")
    compile(source, "<original-app>", "exec")
    before = ast.parse(text)
    lines = text.splitlines(keepends=True)
    functions = {}
    for name in FUNCTION_SHA256:
        nodes = [n for n in before.body if isinstance(n, ast.FunctionDef) and n.name == name]
        if len(nodes) != 1 or nodes[0].decorator_list:
            raise ValueError("PREFLIGHT_FUNCTION_DRIFT")
        functions[name] = nodes[0]
    old_meta = {
        "APP_VERSION": BASE_VERSION,
        "RELEASE_REVISION": BASE_VERSION,
        "BUILD_SIGNATURE": "JUDUN_1.2.120_QUOTE_TOTAL_AUTHORITY_20261021",
    }
    new_meta = {
        "APP_VERSION": TARGET_VERSION,
        "RELEASE_REVISION": TARGET_VERSION,
        "BUILD_SIGNATURE": TARGET_SIGNATURE,
    }
    edits = []
    seen = set()
    for n in before.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in old_meta:
            key = n.targets[0].id
            if key in seen or n.lineno != n.end_lineno or not isinstance(n.value, ast.Constant) or n.value.value != old_meta[key]:
                raise ValueError("RELEASE_METADATA_DRIFT")
            seen.add(key)
            edits.append((n.lineno - 1, n.end_lineno, key + " = " + repr(new_meta[key]) + "\n"))
    if seen != set(old_meta):
        raise ValueError("RELEASE_METADATA_MISSING")
    for name, n in functions.items():
        old = ast.get_source_segment(text, n)
        if expected_sha256 == BASE_APP_SHA256 and FUNCTION_SHA256[name] and sha(old.encode()) != FUNCTION_SHA256[name]:
            raise ValueError("FUNCTION_SHA_MISMATCH")
        if name == "report_renderer_smoke_test":
            if old.count(RENDER_CALL) != 1:
                raise ValueError("SMOKE_RENDER_CALL_DRIFT")
            new = old.replace(RENDER_CALL, SCOPED_RENDER, 1)
            edits.append((n.lineno - 1, n.end_lineno, new + "\n"))
        else:
            # Preserve the docstring, original retrieval and output unchanged.
            i = 1 if isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str) else 0
            edits.append((n.body[i].lineno - 1, n.body[i].lineno - 1, MATCH_GUARD))
            edits.append((n.lineno - 1, n.lineno - 1, PRELUDE))
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = [replacement]
    result = "".join(lines).encode()
    compile(result, "<isolated-preflight-candidate>", "exec")
    # Reverse every intended change byte-for-byte. This also protects homepage,
    # paid reports, PDF templates, totals and every unrelated source statement.
    restored = result.decode()
    restored = restored.replace(PRELUDE, "", 1).replace(MATCH_GUARD, "", 1).replace(SCOPED_RENDER, RENDER_CALL, 1)
    after = ast.parse(restored)
    restored_lines = restored.splitlines(keepends=True)
    for n in after.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and n.targets[0].id in old_meta:
            key = n.targets[0].id
            original = next(x for x in before.body if isinstance(x, ast.Assign) and len(x.targets) == 1 and isinstance(x.targets[0], ast.Name) and x.targets[0].id == key)
            restored_lines[n.lineno - 1:n.end_lineno] = [text.splitlines(keepends=True)[original.lineno - 1]]
    if "".join(restored_lines).encode() != source:
        raise ValueError("UNRELATED_SOURCE_CHANGED")
    return result


def tree_sha(files: list[dict]) -> str:
    return sha("".join(f"{r['path']}\t{r['sha256']}\t{r['size']}\n" for r in sorted(files, key=lambda r: r['path'])).encode())


def plan_signed_patch(root: Path) -> tuple[bytes, dict]:
    """Read and check all 81 managed files; do not change anything."""
    manifest = json.loads((root / "DEPLOY_MANIFEST.json").read_bytes())
    if (manifest.get("schema") != "judun.deploy-manifest.v1"
            or manifest.get("version") != BASE_VERSION
            or manifest.get("artifact_id") != BASE_ARTIFACT
            or manifest.get("source_tree_sha256") != BASE_TREE_SHA256
            or manifest.get("formal_evidence_sha256") != FORMAL_EVIDENCE_SHA256):
        raise ValueError("SIGNED_BASE_IDENTITY_DRIFT")
    rows = manifest.get("files")
    if not isinstance(rows, list) or len(rows) != 81 or len({r['path'] for r in rows}) != 81:
        raise ValueError("BASE_MANAGED_FILE_LIST_DRIFT")
    if tree_sha(rows) != BASE_TREE_SHA256:
        raise ValueError("BASE_MANIFEST_TREE_MISMATCH")
    app_row = None
    for row in rows:
        name = row['path']
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or path.as_posix() != name:
            raise ValueError("UNSAFE_MANAGED_SOURCE_PATH")
        file = root / path
        if not file.resolve().is_relative_to(root.resolve()) or file.is_symlink():
            raise ValueError("SOURCE_PATH_ESCAPE")
        raw = file.read_bytes()
        if type(row['size']) is not int or len(raw) != row['size'] or sha(raw) != row['sha256']:
            raise ValueError("MANAGED_SOURCE_FILE_DRIFT")
        if name == 'app.py':
            app_row = row
    if app_row is None or app_row['sha256'] != BASE_APP_SHA256:
        raise ValueError("BASE_APP_MANIFEST_MISMATCH")
    app = transform((root / 'app.py').read_bytes())
    if sha(app) != TARGET_APP_SHA256:
        raise ValueError("TARGET_APP_SHA_MISMATCH")
    app_row.update(size=len(app), sha256=TARGET_APP_SHA256)
    manifest.update(version=TARGET_VERSION, release_revision=TARGET_VERSION,
                    display_version='v' + TARGET_VERSION, build_signature=TARGET_SIGNATURE,
                    artifact_id=TARGET_ARTIFACT, build_instance_id=TARGET_INSTANCE,
                    source_tree_sha256=tree_sha(rows),
                    built_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'))
    return app, manifest


def apply_signed_patch(root: Path, release: Path) -> None:
    """Entry point exclusively for the original verified, backup-capable agent."""
    expected = {'base_artifact_id': BASE_ARTIFACT, 'target_artifact_id': TARGET_ARTIFACT,
                'target_build_instance_id': TARGET_INSTANCE,
                'base_source_tree_sha256': BASE_TREE_SHA256, 'target_app_sha256': TARGET_APP_SHA256}
    identity = json.loads((release / 'release.json').read_bytes())
    if any(identity.get(k) != v for k, v in expected.items()):
        raise ValueError("SIGNED_INNER_IDENTITY_MISMATCH")
    for key in ('base_artifact_id', 'target_artifact_id', 'target_build_instance_id'):
        if os.environ.get('JUDUN_' + key.upper()) != expected[key]:
            raise ValueError("ORIGINAL_SIGNED_AGENT_REQUIRED")
    app, manifest = plan_signed_patch(root)
    updates = {'app.py': app, 'DEPLOY_MANIFEST.json': (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()}
    for name, raw in updates.items():
        path = root / name
        fd, temporary = tempfile.mkstemp(prefix='.judun-preflight-', dir=root)
        try:
            os.fchmod(fd, stat.S_IMODE(path.stat().st_mode))
            with os.fdopen(fd, 'wb') as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    if sha((root / 'app.py').read_bytes()) != TARGET_APP_SHA256:
        raise ValueError('INSTALLED_APP_SHA_MISMATCH')


if __name__ == '__main__':
    import sys
    apply_signed_patch(Path(sys.argv[1]), Path(sys.argv[2]))
