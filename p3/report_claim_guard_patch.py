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

BASE_APP_SHA256 = 'c597f753f43b6401d1fae82b2ec3e1be1482e8b3f79179fdf27e84f2c1de7e8b'
BASE_VERSION = '1.2.122'
TARGET_VERSION = '1.2.123'
BASE_ARTIFACT = 'JUDUN-1.2.122-C597F753F43B'
BASE_TREE_SHA256 = '2feb05ae52987ea2ecc119bc08017e863e2f17169c970fa4a234101394e5022d'
TARGET_SIGNATURE = 'JUDUN_1.2.123_REPORT_CLAIM_GUARD_20261022'
TARGET_APP_SHA256 = 'c506047e2a5f0ee740a13edb838664eb147311b7a4dc8ba9c1ed579ac8ed6dcd'
TARGET_ARTIFACT = 'JUDUN-1.2.123-C506047E2A5F'
TARGET_INSTANCE = '1.2.123-20261022-CLAIMS-C506047E2A5F'
FORMAL_EVIDENCE_SHA256 = 'cb2530901faf1cf044105e83e74ad099ee8c5974fda2bb34307a79257b79dc4d'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()

HELPERS = 'def _judun_risk_score(value):\n    """Validate the declared 0–10 scale; never guess a percentage conversion."""\n    import re\n    from decimal import Decimal, InvalidOperation\n    if isinstance(value, bool) or value is None:\n        return \'待核對\'\n    text = str(value).strip()\n    if len(text) > 60:\n        return \'待核對\'\n    match = re.fullmatch(r\'(\\d{1,2}(?:\\.\\d{1,4})?)\\s*(?:/\\s*10)?\', text)\n    if not match:\n        return \'待核對\'\n    try:\n        score = Decimal(match.group(1))\n    except InvalidOperation:\n        return \'待核對\'\n    if not score.is_finite() or not 0 <= score <= 10:\n        return \'待核對\'\n    return format(score.normalize(), \'f\') + \'/10\'\n\n\ndef _judun_guard_report_claims(data):\n    """Guard copied render data only; leave stored analysis and amounts intact."""\n    import copy\n    import re\n    result = copy.deepcopy(data) if isinstance(data, dict) else {}\n    result[\'risk_score\'] = _judun_risk_score(result.get(\'risk_score\'))\n    rows = result.get(\'items_analysis\')\n    # Exact backend evidence labels, never free-form model claims of approval.\n    model_only = (isinstance(rows, list) and bool(rows)\n                  and all(isinstance(row, dict) and row.get(\'source_level\') == \'C\'\n                          for row in rows))\n    if not model_only:\n        return result\n    claims = [\n        (r\'(?:工項單價|本案價格|報價價格)與(?:公開)?市場行情相符\',\n         \'本案價格目前僅有模型情境估算，仍須同規格詢價核對\'),\n        (r\'(?:符合|落在)(?:一般|公開)?市場(?:行情|合理)?區間\',\n         \'僅可與模型情境估算對照，仍須同規格詢價核對\'),\n        (r\'本案工項與價格皆屬合理範圍\',\n         \'本案價格比較屬模型情境估算，尚未核驗為同規格市場價格\'),\n    ]\n    def walk(value):\n        if isinstance(value, dict):\n            return {key: walk(item) for key, item in value.items()}\n        if isinstance(value, list):\n            return [walk(item) for item in value]\n        if not isinstance(value, str):\n            return value\n        phrases = claims + [\n            (\'並無重大惡意缺漏\', \'施工安全與契約責任仍待專業核對\'),\n            (\'即可安心簽約\', \'仍應核對完整契約與施工條件，再決定是否簽約\'),\n            (\'即可進行簽約動工\', \'仍應核對完整契約與施工條件，再決定是否簽約動工\'),\n        ]\n        for pattern, replacement in phrases:\n            def replace(match):\n                context = value[max(0, match.start()-24):match.start()]\n                if re.search(r\'(?:不代表|不保證|不能認定|無法認定|未能確認|不得宣稱)[^。；\\n]{0,8}$\', context):\n                    return match.group(0)\n                return replacement\n            value = re.sub(pattern, replace, value)\n        return value\n    # Apply only to generated commentary, never source URLs, quoted customer\n    # specifications, numerical fields, prices, evidence records or entitlements.\n    for key in [\'advisor_summary\', \'final_decision\', \'categories\', \'top5_actions\',\n                \'action_guides\', \'advanced_guides\']:\n        if key in result:\n            result[key] = walk(result[key])\n    for row in result[\'items_analysis\']:\n        for key in [\'comment\', \'action_tip\', \'estimate_assumptions\']:\n            if key in row:\n                row[key] = walk(row[key])\n    return result\n'
GROUNDING_ADDITION = '\n風險分數 risk_score 必須使用0至10的量尺，回傳「數值/10」（例如僅作格式說明：x.x/10）；資料不足回傳「待核對」，不可輸出百分制或未說明量尺的分數。價格區間若來自模型情境，不得稱為市場行情已驗證或保證合理；不能僅因補上品牌就宣稱可安心簽約或施工安全已確認。未知線徑、電路負載或施工安全規格應交由合格專業人員依現場確認，不要直接把示例規格寫成可用的固定要求。\n'

def transform(source, *, expected_sha256=BASE_APP_SHA256):
    if not source or len(source)>16_000_000 or sha(source)!=expected_sha256:
        raise ValueError('CURRENT_APP_SHA_MISMATCH')
    text=source.decode();tree=ast.parse(text);lines=text.splitlines(keepends=True);edits=[]
    if 'def _judun_guard_report_claims(' in text:
        raise ValueError('GUARD_ALREADY_PRESENT')
    funcs={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    target=funcs.get('_judun_guard_report_totals')
    if target is None:raise ValueError('RENDER_GUARD_FUNCTION_MISSING')
    returns=[n for n in target.body if isinstance(n,ast.Return)]
    if len(returns)!=1 or not isinstance(returns[0].value,ast.Name) or returns[0].value.id!='result':
        raise ValueError('RENDER_GUARD_RETURN_DRIFT')
    n=returns[0];edits.append((n.lineno-1,n.end_lineno,'    return _judun_guard_report_claims(result)\n'))
    edits.append((target.lineno-1,target.lineno-1,HELPERS+'\n\n'))
    values={'APP_VERSION':(BASE_VERSION,TARGET_VERSION),'RELEASE_REVISION':(BASE_VERSION,TARGET_VERSION),
        'BUILD_SIGNATURE':('JUDUN_1.2.122_QUOTE_FACT_GROUNDING_20261021',TARGET_SIGNATURE),
        'ANALYSIS_CACHE_VERSION':('analysis_v122_quote_grounding_v1','analysis_v123_quote_grounding_v2'),
        'CORE_CACHE_VERSION':('core_v122_quote_grounding_v1','core_v123_quote_grounding_v2'),
        'ITEM_CACHE_VERSION':('item_v122_quote_grounding_v1','item_v123_quote_grounding_v2'),
        'THEME_CACHE_VERSION':('theme_v122_quote_grounding_v1','theme_v123_quote_grounding_v2')}
    found=set()
    for n in tree.body:
        if not isinstance(n,ast.Assign) or len(n.targets)!=1 or not isinstance(n.targets[0],ast.Name):continue
        key=n.targets[0].id
        if key not in values and key!='QUOTE_FACT_GROUNDING_RULES':continue
        if key in found or not isinstance(n.value,ast.Constant) or n.lineno!=n.end_lineno:raise ValueError('METADATA_DRIFT')
        found.add(key)
        if key=='QUOTE_FACT_GROUNDING_RULES':value=n.value.value+GROUNDING_ADDITION
        else:
            old,value=values[key]
            if n.value.value!=old:raise ValueError('METADATA_DRIFT')
        edits.append((n.lineno-1,n.end_lineno,key+' = '+repr(value)+'\n'))
    if found!=set(values)|{'QUOTE_FACT_GROUNDING_RULES'}:raise ValueError('METADATA_MISSING')
    old='"risk_score": "依本案資料判定；資料不足須說明"';new='"risk_score": "依本案判定的0至10數值/10；資料不足回傳待核對"'
    if text.count(old)!=1:raise ValueError('RISK_SCHEMA_DRIFT')
    index=next(i for i,line in enumerate(lines) if old in line);edits.append((index,index+1,lines[index].replace(old,new)))
    # Previous-case comparison must not silently interpret an unknown scale.
    old_risk="        try:return float(str(data.get('risk_score') or '').split('/')[0].strip())"
    new_risk="        try:return float(_judun_risk_score(data.get('risk_score')).split('/')[0])"
    if text.count(old_risk)!=1:raise ValueError('RECHECK_RISK_DRIFT')
    index=next(i for i,line in enumerate(lines) if old_risk in line);edits.append((index,index+1,lines[index].replace(old_risk,new_risk)))
    chunks=[];inverse=[];cursor=0;out_lines=0
    for start,end,replacement in sorted(edits,key=lambda e:(e[0],e[1])):
        if start<cursor:raise ValueError('OVERLAPPING_PATCH_EDITS')
        chunks.append(''.join(lines[cursor:start]));out_lines+=start-cursor
        count=len(replacement.splitlines(keepends=True));inverse.append((out_lines,out_lines+count,''.join(lines[start:end])))
        chunks.append(replacement);out_lines+=count;cursor=end
    chunks.append(''.join(lines[cursor:]));result=''.join(chunks).encode();compile(result,'<report-claim-guard>','exec')
    restored=result.decode().splitlines(keepends=True)
    for start,end,old in reversed(inverse):restored[start:end]=[old]
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
