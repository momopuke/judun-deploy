"""SHA-pinned v124 to v125 report retrieval timeout; no data or template changes."""
from __future__ import annotations
import ast,datetime,hashlib,json,os,stat,tempfile
from pathlib import Path,PurePosixPath
BASE_APP_SHA256 = '17d7ac26eab85daadbdbf8feb76b0d7af8f83fe471baef331b7c455634708ed8'
BASE_VERSION = '1.2.124'
TARGET_VERSION = '1.2.125'
BASE_ARTIFACT = 'JUDUN-1.2.124-17D7AC26EAB8'
BASE_TREE_SHA256 = 'd655470d06b96f5131c95d3e52e2bf47fdd38e29200d9b85b787037a74b2c3c8'
TARGET_SIGNATURE = 'JUDUN_1.2.125_REPORT_RETRIEVAL_TIMEOUT_20261022'
TARGET_APP_SHA256 = 'c94c757a01cfbb947ff3ce38ba79bf80fd1cc39eead2925628ab05d90e1a5b19'
TARGET_ARTIFACT = 'JUDUN-1.2.125-C94C757A01CF'
TARGET_INSTANCE = '1.2.125-20261022-RETRIEVE-C94C757A01CF'
FORMAL_EVIDENCE_SHA256 = 'cb2530901faf1cf044105e83e74ad099ee8c5974fda2bb34307a79257b79dc4d'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def transform(source, *, expected_sha256=BASE_APP_SHA256):
    if not source or len(source)>16_000_000 or sha(source)!=expected_sha256:raise ValueError('CURRENT_APP_SHA_MISMATCH')
    text=source.decode();tree=ast.parse(text);lines=text.splitlines(keepends=True);edits=[]
    fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='serve_search')
    original=ast.get_source_segment(text,fn)
    before='timer=setTimeout(()=>controller.abort(),18000)'
    after='timer=setTimeout(()=>controller.abort(),90000)'
    if original.count(before)!=1 or after in original:raise ValueError('RETRIEVAL_TIMEOUT_DRIFT')
    changed=original.replace(before,after,1)
    if changed.replace(after,before,1)!=original:raise ValueError('UNRELATED_SEARCH_CHANGE')
    edits.append((fn.lineno-1,fn.end_lineno,changed+'\n'))
    values={'APP_VERSION':(BASE_VERSION,TARGET_VERSION),'RELEASE_REVISION':(BASE_VERSION,TARGET_VERSION),'BUILD_SIGNATURE':('JUDUN_1.2.124_STREAMING_EVIDENCE_SEARCH_20261022',TARGET_SIGNATURE)}
    found=set()
    for n in tree.body:
        if not isinstance(n,ast.Assign) or len(n.targets)!=1 or not isinstance(n.targets[0],ast.Name) or n.targets[0].id not in values:continue
        key=n.targets[0].id;a,b=values[key]
        if key in found or n.lineno!=n.end_lineno or not isinstance(n.value,ast.Constant) or n.value.value!=a:raise ValueError('RELEASE_METADATA_DRIFT')
        found.add(key);edits.append((n.lineno-1,n.end_lineno,key+' = '+repr(b)+'\n'))
    if found!=set(values):raise ValueError('RELEASE_METADATA_MISSING')
    result=list(lines)
    for start,end,replacement in sorted(edits,reverse=True):result[start:end]=[replacement]
    raw=''.join(result).encode();compile(raw,'<report-retrieval-timeout>','exec')
    return raw

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
