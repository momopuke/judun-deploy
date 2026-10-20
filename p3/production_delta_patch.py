"""Signed v1.2.114 -> v1.2.115 P3 surgical patch. Never run outside the signed agent.

The original agent verifies Ed25519/CMS, live artifact identity, takes a rollback
archive and re-verifies the final app. This script independently checks ALL
managed source files and fails closed on any drift before changing either file.
"""
from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import stat
import sys
import tempfile

BASE_VERSION = "1.2.114"
TARGET_VERSION = "1.2.115"
BASE_ARTIFACT = "JUDUN-1.2.114-AA38F0567A4D"
TARGET_ARTIFACT = "JUDUN-1.2.115-21P3A85DF204"
TARGET_INSTANCE = "1.2.115-20261021-P3-21P3A85DF204"
TARGET_SIGNATURE = "JUDUN_1.2.115_P3_PAID_PRICE_NAV_SAFE_20261021"
OLD = "const preferred = tier === 'promax' ? 'report-five-themes' : 'report-price-items';"
NEW = "const preferred = 'report-price-items';"
OLD_COMPLETION = "if (String(data.status || '').includes('完成')) {"
NEW_COMPLETION = ("if (String(data.status || '').includes('完成') "
                  "&& !/(?:未完成|未能完成|完成失敗|失敗|取消|中止)/.test(String(data.status || '')) "
                  "&& (!tierMonitor || !task || task.state === 'completed')) {")
MAX_SOURCE = 16_000_000


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def computed_tree_sha(files: list) -> str:
    # Match the historical authoritative BUILD_PAYLOAD.ps1 byte-for-byte:
    # ordinal path sort; PATH NUL DECIMAL_SIZE NUL LOWERCASE_SHA256 LF,
    # including one final LF even for the last entry. This is NOT
    # path/NUL/hash/NUL/size and cannot omit the trailing newline.
    rows = ''.join(
        f"{x['path']}\0{x['size']}\0{x['sha256']}\n"
        for x in sorted(files, key=lambda x: x['path'])
    )
    return sha(rows.encode('utf-8'))


def inspect_managed_source(root: pathlib.Path, *, version: str = BASE_VERSION,
                           artifact: str = BASE_ARTIFACT) -> tuple[dict, bytes]:
    manifest = json.loads((root / 'DEPLOY_MANIFEST.json').read_text('utf-8'))
    if (manifest.get('schema') != 'judun.deploy-manifest.v1'
            or manifest.get('version') != version
            or manifest.get('artifact_id') != artifact):
        raise ValueError('LIVE_ARTIFACT_OR_VERSION_MISMATCH')
    files = manifest.get('files')
    if not isinstance(files, list) or len(files) < 79:
        raise ValueError('INCOMPLETE_LIVE_SOURCE_MANIFEST')
    paths = [entry.get('path') for entry in files if isinstance(entry, dict)]
    if len(paths) != len(files) or len(paths) != len(set(paths)) or paths.count('app.py') != 1:
        raise ValueError('MANIFEST_DUPLICATE_OR_MISSING_APP')
    if any(x in paths for x in ('RELEASE.json', 'VERSION.txt')):
        raise ValueError('ADDITIONAL_VERSION_SOURCE_REQUIRES_REVIEW')
    if computed_tree_sha(files) != manifest.get('source_tree_sha256'):
        raise ValueError('SOURCE_TREE_DIGEST_MISMATCH')
    app_data = None
    for item in files:
        name = item['path']
        if (not isinstance(name, str) or name.startswith('/') or '\\' in name
                or '..' in pathlib.PurePosixPath(name).parts):
            raise ValueError('UNSAFE_MANAGED_PATH')
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('ESCAPING_MANAGED_PATH')
        b = path.read_bytes()
        if len(b) != item.get('size') or sha(b) != item.get('sha256'):
            raise ValueError('UNREVIEWED_LIVE_FILE_DRIFT')
        if name == 'app.py':
            app_data = b
    if not app_data or len(app_data) > MAX_SOURCE:
        raise ValueError('MISSING_OR_OVERSIZED_APP')
    return manifest, app_data


def patch_app(original: bytes) -> bytes:
    text = original.decode('utf-8')
    tree = ast.parse(text)
    if ('FastAPI(' not in text or '@app.get("/status/{job_id}")' not in text):
        raise ValueError('UNEXPECTED_APP_STRUCTURE')
    assignments = [stmt for stmt in tree.body if isinstance(stmt, ast.Assign)
                   and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                   and stmt.targets[0].id == 'GLOBAL_JS']
    if len(assignments) != 1 or not isinstance(assignments[0].value, ast.Constant) or not isinstance(assignments[0].value.value, str):
        raise ValueError('GLOBAL_JS_MODULE_LITERAL_MISMATCH')
    js = assignments[0].value.value
    if (text.count(OLD) != 1 or text.count(OLD_COMPLETION) != 1
            or js.count(OLD) != 1 or js.count(OLD_COMPLETION) != 1):
        raise ValueError('EXPECTED_TWO_UNIQUE_LIVE_JS_STATEMENTS')
    for snippet, fn in [(OLD, 'window.unlockTier ='), (OLD_COMPLETION, 'function checkMicroStatus(')]:
        pos = js.index(snippet)
        head = js.rfind(fn, max(0, pos - 16000), pos)
        if head < 0 or re.search(r'\b(?:async\s+)?function\s+[A-Za-z_$]\w*\s*\(', js[head + len(fn):pos]):
            raise ValueError('JS_FUNCTION_CONTEXT_DRIFT')
    original_version = f'APP_VERSION = "{BASE_VERSION}"'
    if text.count(original_version) != 1:
        raise ValueError('VERSION_CONSTANT_MISMATCH')
    original_revision = f'RELEASE_REVISION = "{BASE_VERSION}"'
    if text.count(original_revision) != 1:
        raise ValueError('RELEASE_REVISION_CONSTANT_MISMATCH')
    sig_pattern = r'^BUILD_SIGNATURE = "JUDUN_1\.2\.114_[A-Z0-9_]{8,160}"$'
    if len(re.findall(sig_pattern, text, flags=re.MULTILINE)) != 1:
        raise ValueError('BUILD_SIGNATURE_CONSTANT_MISMATCH')
    changed = text.replace(OLD, NEW, 1).replace(OLD_COMPLETION, NEW_COMPLETION, 1)
    changed = changed.replace(original_version, f'APP_VERSION = "{TARGET_VERSION}"', 1)
    changed = changed.replace(original_revision, f'RELEASE_REVISION = "{TARGET_VERSION}"', 1)
    changed = re.sub(sig_pattern, f'BUILD_SIGNATURE = "{TARGET_SIGNATURE}"', changed, count=1, flags=re.MULTILINE)
    if changed.count(NEW) != 1 or changed.count(NEW_COMPLETION) != 1:
        raise ValueError('AMBIGUOUS_PATCH_RESULT')
    compile(changed, '<signed-current-patched-app>', 'exec')
    return changed.encode('utf-8')


def plan_update(root: pathlib.Path) -> tuple[bytes, bytes]:
    manifest, before = inspect_managed_source(root)
    after = patch_app(before)
    original_formal_hash = manifest.get('formal_evidence_sha256')
    for item in manifest['files']:
        if item['path'] == 'app.py':
            item.update(size=len(after), sha256=sha(after))
    manifest.update(version=TARGET_VERSION, release_revision=TARGET_VERSION,
                    display_version='v' + TARGET_VERSION,
                    build_signature=TARGET_SIGNATURE, artifact_id=TARGET_ARTIFACT,
                    build_instance_id=TARGET_INSTANCE,
                    source_tree_sha256=computed_tree_sha(manifest['files']),
                    built_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'))
    if manifest.get('formal_evidence_sha256') != original_formal_hash:
        raise ValueError('FORMAL_DATA_PROTECTION_ERROR')
    return after, (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()


def replace_file_exclusive_temp(target: pathlib.Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix='.judun-signed-', dir=target.parent)
    try:
        os.fchmod(fd, stat.S_IMODE(target.stat().st_mode))
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def apply(root: pathlib.Path, release_dir: pathlib.Path) -> None:
    config = json.loads((release_dir / 'release.json').read_text('utf-8'))
    expected = {'base_artifact_id': BASE_ARTIFACT,
                'target_artifact_id': TARGET_ARTIFACT,
                'target_build_instance_id': TARGET_INSTANCE}
    if any(config.get(k) != v for k, v in expected.items()):
        raise ValueError('SIGNED_INNER_RELEASE_IDENTITY_MISMATCH')
    if (os.getenv('JUDUN_BASE_ARTIFACT_ID') != BASE_ARTIFACT or
        os.getenv('JUDUN_TARGET_ARTIFACT_ID') != TARGET_ARTIFACT or
        os.getenv('JUDUN_TARGET_BUILD_INSTANCE_ID') != TARGET_INSTANCE):
        raise ValueError('SIGNED_AGENT_ENVIRONMENT_MISMATCH')
    new_app, new_manifest = plan_update(root)
    if os.getenv('JUDUN_SIMULATE') == '1':
        print('P3_SIGNED_PATCH_DRY_RUN_PASS')
        return
    replace_file_exclusive_temp(root / 'app.py', new_app)
    replace_file_exclusive_temp(root / 'DEPLOY_MANIFEST.json', new_manifest)
    # The original signed agent restores its backup if this gate fails.
    after_manifest, current_app = inspect_managed_source(
        root, version=TARGET_VERSION, artifact=TARGET_ARTIFACT)
    if (current_app != new_app or
            after_manifest.get('build_signature') != TARGET_SIGNATURE or
            after_manifest.get('build_instance_id') != TARGET_INSTANCE):
        raise ValueError('POST_WRITE_INTEGRITY_MISMATCH')
    print('P3_SIGNED_PATCH_STAGED_WITH_BACKUP')


def main():
    root = pathlib.Path(sys.argv[1]).resolve()
    rel = pathlib.Path(sys.argv[2]).resolve()
    apply(root, rel)

if __name__ == '__main__':
    main()
