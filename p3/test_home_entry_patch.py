import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock
import home_entry_patch as patch

FIXTURE='''APP_VERSION = '1.2.125'
RELEASE_REVISION = '1.2.125'
BUILD_SIGNATURE = 'JUDUN_1.2.125_REPORT_RETRIEVAL_TIMEOUT_20261022'
def untouched():
    return 'existing price analysis, payment, report and PDF'
def serve_home():
    html_part = '<main>original upload and consent</main>'
    js_part = '<script>original()</script>'
    return HTMLResponse(content=get_base_html(f"{BRAND_NAME}｜{PRODUCT_NAME}", html_part + js_part))
'''.encode()

def apply(raw=FIXTURE):
    return patch.transform(raw,expected_sha256=hashlib.sha256(raw).hexdigest())

class HomeEntryPatchTests(unittest.TestCase):
    def test_original_page_and_handlers_preserved_with_one_entry_layer(self):
        out=apply()
        before=ast.parse(FIXTURE);after=ast.parse(out)
        old={n.name:ast.dump(n) for n in before.body if isinstance(n,ast.FunctionDef)}
        new={n.name:ast.dump(n) for n in after.body if isinstance(n,ast.FunctionDef)}
        self.assertEqual(old['untouched'],new['untouched'])
        ns={'BRAND_NAME':'brand','PRODUCT_NAME':'product','get_base_html':lambda t,c:'<html><head><script>const nested=\"</body>\";</script></head><body>'+c+'</body></html>','HTMLResponse':lambda **kw:kw['content']}
        exec(compile(out,'<home-entry-fixture>','exec'),ns)
        page=ns['serve_home']()
        self.assertEqual(page.count('id="judun-home-entry-script"'),1)
        self.assertEqual(page.count('id="judun-home-entry-style"'),1)
        self.assertIn('<main>original upload and consent</main>',page)
        self.assertIn('<script>original()</script>',page)
        self.assertLess(page.index('judun-home-entry-style'),page.index('</head>'))
        self.assertLess(page.index('judun-home-entry-script'),page.rindex('</body>'))
        self.assertIn('const nested="</body>";',page)
    def test_document_boundary_drift_fails_before_responding(self):
        ns={'BRAND_NAME':'brand','PRODUCT_NAME':'product','get_base_html':lambda *args:'<html></html>','HTMLResponse':lambda **kw:kw}
        exec(compile(apply(),'<fixture>','exec'),ns)
        with self.assertRaisesRegex(RuntimeError,'HOME_DOCUMENT_BOUNDARY_DRIFT'):ns['serve_home']()
    def test_unknown_source_refused(self):
        with self.assertRaisesRegex(ValueError,'CURRENT_APP_SHA_MISMATCH'):patch.transform(FIXTURE)
    def test_return_drift_refused(self):
        with self.assertRaisesRegex(ValueError,'HOME_RETURN_DRIFT'):apply(FIXTURE.replace(b'html_part + js_part',b'html_part'))
    def test_duplicate_home_refused(self):
        with self.assertRaisesRegex(ValueError,'HOME_FUNCTION_DRIFT'):apply(FIXTURE+b'\ndef serve_home():\n    return None\n')
    def test_wrong_metadata_refused(self):
        with self.assertRaisesRegex(ValueError,'RELEASE_METADATA_DRIFT'):apply(FIXTURE.replace(b"'1.2.125'",b"'1.2.124'"))
    def test_original_agent_required_before_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            identity={'base_artifact_id':patch.BASE_ARTIFACT,'target_artifact_id':patch.TARGET_ARTIFACT,'target_build_instance_id':patch.TARGET_INSTANCE,'base_source_tree_sha256':patch.BASE_TREE_SHA256,'target_app_sha256':patch.TARGET_APP_SHA256}
            (root/'release.json').write_text(json.dumps(identity))
            with mock.dict(os.environ,{},clear=True):
                with self.assertRaisesRegex(ValueError,'ORIGINAL_SIGNED_AGENT_REQUIRED'):patch.apply_signed_patch(root,root)
            self.assertEqual([p.name for p in root.iterdir()],['release.json'])

if __name__=='__main__':unittest.main()
