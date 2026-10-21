"""SHA-pinned v125 to v126 homepage entries; preserves existing brand and forms."""
from __future__ import annotations
import ast,datetime,hashlib,json,os,stat,tempfile
from pathlib import Path,PurePosixPath
BASE_APP_SHA256 = 'c94c757a01cfbb947ff3ce38ba79bf80fd1cc39eead2925628ab05d90e1a5b19'
BASE_VERSION = '1.2.125'
TARGET_VERSION = '1.2.126'
BASE_ARTIFACT = 'JUDUN-1.2.125-C94C757A01CF'
BASE_TREE_SHA256 = '389121cc6f1a4cb3d712a02d9fdbf007f1eaee30b43088fe262f0e5ac7965a9f'
TARGET_SIGNATURE = 'JUDUN_1.2.126_HOME_SCENARIO_ENTRY_20261022'
TARGET_APP_SHA256 = '6cf18cdb1b765e1721753badafe14c138b7814b9d1a94a2a327fcdbf021672a9'
TARGET_ARTIFACT = 'JUDUN-1.2.126-6CF18CDB1B76'
TARGET_INSTANCE = '1.2.126-20261022-HOME-6CF18CDB1B76'
FORMAL_EVIDENCE_SHA256 = 'cb2530901faf1cf044105e83e74ad099ee8c5974fda2bb34307a79257b79dc4d'

def sha(raw):return hashlib.sha256(raw).hexdigest()

def entry_markup():
    assets = Path(__file__).resolve().parent.parent / 'p0'
    # In the original signed payload the two assets sit alongside this module.
    if not assets.is_dir():
        assets = Path(__file__).resolve().parent
    css = (assets/'home-entry.css').read_text()
    js = (assets/'home-entry.js').read_text()
    if '</style' in css.lower() or '</script' in js.lower():
        raise ValueError('ENTRY_ASSET_CLOSING_TAG')
    return ('<style id="judun-home-entry-style">'+css+'</style>',
            '<script id="judun-home-entry-script">'+js+'</script>')

def transform(source, *, expected_sha256=BASE_APP_SHA256):
    if not source or len(source)>16_000_000 or sha(source)!=expected_sha256:
        raise ValueError('CURRENT_APP_SHA_MISMATCH')
    text=source.decode();tree=ast.parse(text);lines=text.splitlines(keepends=True);edits=[]
    homes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='serve_home']
    if len(homes)!=1:raise ValueError('HOME_FUNCTION_DRIFT')
    fn=homes[0];original=ast.get_source_segment(text,fn)
    before='    return HTMLResponse(content=get_base_html(f"{BRAND_NAME}｜{PRODUCT_NAME}", html_part + js_part))'
    if original.count(before)!=1 or 'judun-home-entry-script' in text:
        raise ValueError('HOME_RETURN_DRIFT')
    css,js=entry_markup()
    after=('    home_page = get_base_html(f"{BRAND_NAME}｜{PRODUCT_NAME}", html_part + js_part)\n'
           '    if home_page.count("</head>") != 1 or not home_page.endswith("</body></html>"):\n'
           '        raise RuntimeError("HOME_DOCUMENT_BOUNDARY_DRIFT")\n'
           '    home_page = home_page.replace("</head>", '+repr(css+'\n</head>')+', 1)\n'
           '    home_page = home_page[:-len("</body></html>")] + '+repr(js+'\n</body></html>')+'\n'
           '    return HTMLResponse(content=home_page)')
    changed=original.replace(before,after,1)
    if changed.replace(after,before,1)!=original:raise ValueError('UNRELATED_HOME_CHANGE')
    edits.append((fn.lineno-1,fn.end_lineno,changed+'\n'))
    values={'APP_VERSION':(BASE_VERSION,TARGET_VERSION),'RELEASE_REVISION':(BASE_VERSION,TARGET_VERSION),'BUILD_SIGNATURE':('JUDUN_1.2.125_REPORT_RETRIEVAL_TIMEOUT_20261022',TARGET_SIGNATURE)}
    found=set()
    for n in tree.body:
        if not isinstance(n,ast.Assign) or len(n.targets)!=1 or not isinstance(n.targets[0],ast.Name) or n.targets[0].id not in values:continue
        key=n.targets[0].id;a,b=values[key]
        if key in found or n.lineno!=n.end_lineno or not isinstance(n.value,ast.Constant) or n.value.value!=a:raise ValueError('RELEASE_METADATA_DRIFT')
        found.add(key);edits.append((n.lineno-1,n.end_lineno,key+' = '+repr(b)+'\n'))
    if found!=set(values):raise ValueError('RELEASE_METADATA_MISSING')
    chunks=[];inverse=[];cursor=0;out_lines=0
    for start,end,replacement in sorted(edits):
        chunks.append(''.join(lines[cursor:start]));out_lines+=start-cursor
        count=len(replacement.splitlines(keepends=True));inverse.append((out_lines,out_lines+count,''.join(lines[start:end])))
        chunks.append(replacement);out_lines+=count;cursor=end
    chunks.append(''.join(lines[cursor:]));raw=''.join(chunks).encode();compile(raw,'<home-entry>','exec')
    restored=raw.decode().splitlines(keepends=True)
    for start,end,old in reversed(inverse):restored[start:end]=[old]
    if ''.join(restored).encode()!=source:raise ValueError('UNRELATED_SOURCE_CHANGED')
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
