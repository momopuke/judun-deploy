"""SHA-pinned v122→123 prompt correction; no customer data changes.

Read source as text/AST only. Never import the application.
"""
from __future__ import annotations
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile

BASE_APP_SHA256 = 'c506047e2a5f0ee740a13edb838664eb147311b7a4dc8ba9c1ed579ac8ed6dcd'
BASE_VERSION = '1.2.123'
TARGET_VERSION = '1.2.124'
BASE_ARTIFACT = 'JUDUN-1.2.123-C506047E2A5F'
BASE_TREE_SHA256 = '898f7905196c40b1b722f0c7530cf331a1909141f90d398a55c6043be0e0756f'
TARGET_SIGNATURE = 'JUDUN_1.2.124_STREAMING_EVIDENCE_SEARCH_20261022'
TARGET_APP_SHA256 = '17d7ac26eab85daadbdbf8feb76b0d7af8f83fe471baef331b7c455634708ed8'
TARGET_ARTIFACT = 'JUDUN-1.2.124-17D7AC26EAB8'
TARGET_INSTANCE = '1.2.124-20261022-SEARCH-17D7AC26EAB8'
FORMAL_EVIDENCE_SHA256 = 'cb2530901faf1cf044105e83e74ad099ee8c5974fda2bb34307a79257b79dc4d'



def sha(raw):return hashlib.sha256(raw).hexdigest()
HELPER = 'def _judun_iter_search_evidence(db_path):\n    """Stream eligible search rows in one read snapshot; never cache the corpus."""\n    import json\n    from contextlib import closing\n    from pathlib import Path\n    import sqlite3\n    from evidence_store import current_qa_pass, PRICE_POLICY_VERSION\n    uri = Path(db_path).resolve().as_uri() + \'?mode=ro\'\n    with closing(sqlite3.connect(uri, uri=True, timeout=15)) as db:\n        db.execute(\'BEGIN\')\n        cases = {}\n        auto_cids = set()\n        for (payload,) in db.execute(\'SELECT payload FROM cases ORDER BY id\'):\n            case = json.loads(payload)\n            cid = case[\'id\']\n            is_auto = case.get(\'source_line\') == \'AUTO\'\n            if is_auto:\n                auto_cids.add(cid)\n            if case.get(\'price_qa_decision\') in {\'HOLD\', \'REJECTED\'}:\n                continue\n            if is_auto and (case.get(\'source_status\') != \'active\'\n                            or not current_qa_pass(case.get(\'validation_policy_version\'),\n                                                   case.get(\'auto_qa_decision\'),\n                                                   case.get(\'auto_qa_rules\'))):\n                continue\n            cases[str(cid)] = case\n        for (payload,) in db.execute(\'SELECT payload FROM quote_records ORDER BY rowid\'):\n            row = json.loads(payload)\n            cid = str(row[\'case_id\'])\n            case = cases.get(cid)\n            if not case or row.get(\'price_qa_decision\') in {\'HOLD\', \'REJECTED\'}:\n                continue\n            if cid in auto_cids and (row.get(\'price_qa_decision\') != \'PASS\'\n                                      or row.get(\'price_qa_policy_version\') != PRICE_POLICY_VERSION):\n                continue\n            row_item = str(row.get(\'item\') or \'\')\n            spec = str(row.get(\'specification\') or \'\')\n            title = str(case.get(\'title\') or row.get(\'logical_case_title\') or \'\')\n            context = _evidence_compact_text(\' \'.join((row_item, spec, title)))\n            if not context:\n                continue\n            has_price = any(row.get(key) is not None for key in (\n                \'unit_price_twd\', \'amount_twd\', \'amount_low_twd\', \'amount_high_twd\',\n                \'amount_upper_twd\', \'amount_upper_exclusive_twd\')) or bool(str(row.get(\'raw_price_text\') or \'\').strip())\n            if not has_price:\n                continue\n            yield {\'row\':row, \'case\':case, \'cid\':cid, \'context\':context,\n                   \'row_item\':_evidence_compact_text(row_item),\n                   \'unit\':_evidence_compact_text(row.get(\'unit\')),\n                   \'region\':_evidence_compact_text(case.get(\'region\')).replace(\'臺\',\'台\'),\n                   \'status\':str(row.get(\'review_status\') or \'\')}\n'

def transform(source, *, expected_sha256=BASE_APP_SHA256):
    if not source or len(source)>16_000_000 or sha(source)!=expected_sha256:raise ValueError('CURRENT_APP_SHA_MISMATCH')
    text=source.decode();tree=ast.parse(text);lines=text.splitlines(keepends=True);edits=[]
    if 'def _judun_iter_search_evidence(' in text:raise ValueError('STREAM_SEARCH_ALREADY_PRESENT')
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    for name in ['_public_evidence_search_index','rank_public_evidence_records','build_public_evidence_context']:
        if name not in functions:raise ValueError('SEARCH_FUNCTION_MISSING')
    fn=functions['_public_evidence_search_index'];old=ast.get_source_segment(text,fn)
    if old.count('    with _JUDUN_EVIDENCE_CACHE_LOCK:')!=1:raise ValueError('INDEX_LOCK_DRIFT')
    new=old.replace('    with _JUDUN_EVIDENCE_CACHE_LOCK:',"    if data is None:\n        return public_evidence_revision_tag(), _judun_iter_search_evidence(DATA_DIR / 'public_evidence.db')\n    with _JUDUN_EVIDENCE_CACHE_LOCK:",1)
    new=new.replace('tuple[str, list[dict]]','tuple[str, Any]',1)
    edits.append((fn.lineno-1,fn.end_lineno,new+'\n'));edits.append((fn.lineno-1,fn.lineno-1,HELPER+'\n\n'))
    fn=functions['rank_public_evidence_records'];old=ast.get_source_segment(text,fn)
    replacements={
        '    scored: list[dict] = []':'    best_by_case: dict[str, dict] = {}',
        '        scored.append({"score": round(score, 2), "match_reason": "、".join(dict.fromkeys(reasons)) or "同類工項公開參考", "record": row, "case": case})':
        '        hit = {"score": round(score, 2), "match_reason": "、".join(dict.fromkeys(reasons)) or "同類工項公開參考", "record": row, "case": case}\n        cid = str(row.get("case_id") or "")\n        previous = best_by_case.get(cid)\n        if previous is None or (hit["score"], str(case.get("published") or "")) > (previous["score"], str(previous["case"].get("published") or "")):\n            best_by_case.pop(cid, None)\n            best_by_case[cid] = hit',
        '    scored.sort(key=':'    scored = list(best_by_case.values())\n    scored.sort(key=',
    }
    new=old
    for a,b in replacements.items():
        if new.count(a)!=1:raise ValueError('RANK_STATEMENT_DRIFT')
        new=new.replace(a,b,1)
    # Serialize uncached corpus scans with the existing re-entrant search lock.
    parsed=ast.parse(new);node=parsed.body[0];body_index=1 if isinstance(node.body[0],ast.Expr) and isinstance(node.body[0].value,ast.Constant) and isinstance(node.body[0].value.value,str) else 0
    body_line=node.body[body_index].lineno-1;parts=new.splitlines(keepends=True)
    new=''.join(parts[:body_line])+'    with _JUDUN_EVIDENCE_CACHE_LOCK:\n'+''.join('    '+line if line.strip() else line for line in parts[body_line:])
    edits.append((fn.lineno-1,fn.end_lineno,new+'\n'))
    fn=functions['build_public_evidence_context'];old=ast.get_source_segment(text,fn)
    if old.count('    data = public_quote_data()')!=1:raise ValueError('CONTEXT_CORPUS_LOAD_DRIFT')
    new=old.replace('    data = public_quote_data()','    data = None  # Search streams eligible records; it never loads the full corpus.',1)
    edits.append((fn.lineno-1,fn.end_lineno,new+'\n'))
    values={'APP_VERSION':(BASE_VERSION,TARGET_VERSION),'RELEASE_REVISION':(BASE_VERSION,TARGET_VERSION),'BUILD_SIGNATURE':('JUDUN_1.2.123_REPORT_CLAIM_GUARD_20261022',TARGET_SIGNATURE)};found=set()
    for n in tree.body:
        if not isinstance(n,ast.Assign) or len(n.targets)!=1 or not isinstance(n.targets[0],ast.Name) or n.targets[0].id not in values:continue
        key=n.targets[0].id;a,b=values[key]
        if key in found or n.lineno!=n.end_lineno or not isinstance(n.value,ast.Constant) or n.value.value!=a:raise ValueError('RELEASE_METADATA_DRIFT')
        found.add(key);edits.append((n.lineno-1,n.end_lineno,key+' = '+repr(b)+'\n'))
    if found!=set(values):raise ValueError('RELEASE_METADATA_MISSING')
    chunks=[];inverse=[];cursor=0;out_lines=0
    for start,end,replacement in sorted(edits,key=lambda e:(e[0],e[1])):
        if start<cursor:raise ValueError('OVERLAPPING_PATCH_EDITS')
        chunks.append(''.join(lines[cursor:start]));out_lines+=start-cursor
        count=len(replacement.splitlines(keepends=True));inverse.append((out_lines,out_lines+count,''.join(lines[start:end])))
        chunks.append(replacement);out_lines+=count;cursor=end
    chunks.append(''.join(lines[cursor:]));result=''.join(chunks).encode();compile(result,'<streamed-search>','exec')
    restored=result.decode().splitlines(keepends=True)
    for start,end,original in reversed(inverse):restored[start:end]=[original]
    if ''.join(restored).encode()!=source:raise ValueError('UNRELATED_SOURCE_CHANGED')
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
        fd, temporary = tempfile.mkstemp(prefix='.judun-grounding-', dir=root)
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
