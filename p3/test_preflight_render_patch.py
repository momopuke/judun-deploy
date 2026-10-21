"""Readiness must render honestly without locking/loading production evidence."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import threading
import unittest
import tempfile
import json
import os
from unittest.mock import patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight_render_patch as patch

FIXTURE = '''APP_VERSION = '1.2.120'
RELEASE_REVISION = '1.2.120'
BUILD_SIGNATURE = 'JUDUN_1.2.120_QUOTE_TOTAL_AUTHORITY_20261021'

def public_quote_matches(item_name: str, limit: int = 3) -> list[dict]:
    """Normal retrieval retains its existing behavior."""
    return rank_public_evidence_records(item_name, limit=limit)

def report_renderer_smoke_test() -> tuple[bool, str]:
    smoke_job = object()
    try:
        rendered = build_html_report(smoke_job, include_chat=False)
    except Exception as exc:
        return False, type(exc).__name__
    if 'report-price-items' not in rendered:
        return False, 'incomplete'
    return True, 'rendered'

def unrelated():
    return 'homepage/payment/pdf/confirmed-total behavior is unchanged'
'''


def namespace(render=None, rank=None, source=FIXTURE):
    raw = source.encode()
    changed = patch.transform(raw, expected_sha256=patch.sha(raw))
    values = {
        'rank_public_evidence_records': rank or (lambda item, limit: [{'item': item, 'limit': limit}]),
    }
    values['build_html_report'] = render or (lambda job, **kw: 'report-price-items ' + repr(values['public_quote_matches']('smoke')))
    exec(compile(changed, '<synthetic-preflight-fixture>', 'exec'), values)
    return values


class PreflightRenderTests(unittest.TestCase):
    def test_unsigned_apply_stops_before_reading_or_writing_application(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root/'app.py').write_bytes(b'protected production app')
            (root/'release.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'SIGNED_INNER_IDENTITY_MISMATCH'):
                patch.apply_signed_patch(root, root)
            self.assertEqual((root/'app.py').read_bytes(), b'protected production app')

    def test_original_agent_context_is_required_before_source_plan(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            identity = {'base_artifact_id':patch.BASE_ARTIFACT,'target_artifact_id':patch.TARGET_ARTIFACT,'target_build_instance_id':patch.TARGET_INSTANCE,'base_source_tree_sha256':patch.BASE_TREE_SHA256,'target_app_sha256':patch.TARGET_APP_SHA256}
            (root/'release.json').write_text(json.dumps(identity))
            with mock_patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, 'ORIGINAL_SIGNED_AGENT_REQUIRED'):
                    patch.apply_signed_patch(root, root)
            self.assertEqual({p.name for p in root.iterdir()}, {'release.json'})

    def test_readonly_plan_checks_every_source_file_and_preserves_originals(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for i in range(80):
                (root/f'module_{i}.txt').write_bytes(str(i).encode())
            (root/'app.py').write_text(FIXTURE)
            rows=[{'path':p.name,'size':p.stat().st_size,'sha256':patch.sha(p.read_bytes())} for p in sorted(root.iterdir())]
            tree=patch.tree_sha(rows)
            candidate=patch.transform(FIXTURE.encode(), expected_sha256=patch.sha(FIXTURE.encode()))
            manifest={'schema':'judun.deploy-manifest.v1','version':patch.BASE_VERSION,'artifact_id':patch.BASE_ARTIFACT,'source_tree_sha256':tree,'formal_evidence_sha256':patch.FORMAL_EVIDENCE_SHA256,'files':rows}
            (root/'DEPLOY_MANIFEST.json').write_text(json.dumps(manifest))
            originals={p.name:p.read_bytes() for p in root.iterdir()}
            with mock_patch.object(patch,'BASE_TREE_SHA256',tree), mock_patch.object(patch,'BASE_APP_SHA256',patch.sha(FIXTURE.encode())), mock_patch.object(patch,'TARGET_APP_SHA256',patch.sha(candidate)), mock_patch.object(patch,'transform',return_value=candidate):
                app,new_manifest=patch.plan_signed_patch(root)
                self.assertEqual(app,candidate)
                self.assertEqual(new_manifest['artifact_id'],patch.TARGET_ARTIFACT)
                self.assertEqual(new_manifest['formal_evidence_sha256'],manifest['formal_evidence_sha256'])
                self.assertEqual({p.name:p.read_bytes() for p in root.iterdir()}, originals)
                (root/'module_79.txt').write_text('drift')
                with self.assertRaisesRegex(ValueError,'MANAGED_SOURCE_FILE_DRIFT'):
                    patch.plan_signed_patch(root)
                self.assertEqual((root/'app.py').read_bytes(), originals['app.py'])

    def test_production_default_rejects_synthetic_or_changed_source(self):
        with self.assertRaisesRegex(ValueError, 'CURRENT_APP_SHA_MISMATCH'):
            patch.transform(FIXTURE.encode())

    def test_real_renderer_still_runs_and_never_retrieves_evidence(self):
        calls = []
        def rank(*args, **kwargs):
            self.fail('smoke attempted production retrieval')
        values = namespace(rank=rank)
        def render(job, *, include_chat):
            calls.append(include_chat)
            self.assertEqual(values['public_quote_matches']('smoke'), [])
            return 'report-price-items'
        values['build_html_report'] = render
        self.assertEqual(values['report_renderer_smoke_test'](), (True, 'rendered'))
        self.assertEqual(calls, [False])

    def test_normal_report_retrieval_is_unchanged(self):
        values = namespace()
        self.assertEqual(values['public_quote_matches']('油漆', limit=2), [{'item': '油漆', 'limit': 2}])
        values['report_renderer_smoke_test']()
        self.assertEqual(values['public_quote_matches']('水電'), [{'item': '水電', 'limit': 3}])

    def test_renderer_exception_is_not_reported_as_ready_and_resets_scope(self):
        values = namespace(render=lambda *a, **k: (_ for _ in ()).throw(RuntimeError('failed')))
        self.assertEqual(values['report_renderer_smoke_test'](), (False, 'RuntimeError'))
        self.assertFalse(values[patch.SCOPE].get())
        self.assertTrue(values['public_quote_matches']('normal'))

    def test_bad_renderer_output_still_fails(self):
        values = namespace(render=lambda *a, **k: 'broken output')
        self.assertEqual(values['report_renderer_smoke_test'](), (False, 'incomplete'))
        self.assertFalse(values[patch.SCOPE].get())

    def test_nested_scope_restores_prior_context(self):
        values = namespace()
        token = values[patch.SCOPE].set(True)
        try:
            self.assertTrue(values['report_renderer_smoke_test']()[0])
            self.assertTrue(values[patch.SCOPE].get())
        finally:
            values[patch.SCOPE].reset(token)
        self.assertFalse(values[patch.SCOPE].get())

    def test_parallel_customer_request_is_not_given_smoke_data(self):
        entered, release = threading.Event(), threading.Event()
        values = namespace()
        def render(*a, **kw):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test synchronization failed')
            self.assertEqual(values['public_quote_matches']('smoke'), [])
            return 'report-price-items'
        values['build_html_report'] = render
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(values['report_renderer_smoke_test'])
            try:
                self.assertTrue(entered.wait(3))
                self.assertTrue(values['public_quote_matches']('customer'))
                self.assertFalse(values[patch.SCOPE].get())
            finally:
                release.set()
            self.assertTrue(future.result(timeout=3)[0])

    def test_smoke_does_not_wait_for_customer_evidence_lock(self):
        lock = threading.Lock()
        def rank(*args, **kw):
            if not lock.acquire(timeout=.05):
                raise RuntimeError('blocked by production evidence lock')
            lock.release()
            return [1]
        values = namespace(rank=rank)
        with lock:
            self.assertTrue(values['report_renderer_smoke_test']()[0])

    def test_async_context_does_not_leak_to_other_task(self):
        values = namespace()
        async def smoke():
            token = values[patch.SCOPE].set(True)
            try:
                await asyncio.sleep(0)
                return values['public_quote_matches']('smoke')
            finally:
                values[patch.SCOPE].reset(token)
        async def normal():
            await asyncio.sleep(0)
            return values['public_quote_matches']('customer')
        async def run():
            return await asyncio.gather(smoke(), normal())
        isolated, customer = asyncio.run(run())
        self.assertEqual(isolated, [])
        self.assertTrue(customer)

    def test_repeated_smoke_calls_do_not_accumulate_context(self):
        values = namespace()
        for _ in range(100):
            self.assertTrue(values['report_renderer_smoke_test']()[0])
            self.assertFalse(values[patch.SCOPE].get())
        self.assertTrue(values['public_quote_matches']('customer'))

    def test_duplicate_or_missing_function_is_rejected(self):
        for source in [FIXTURE + '\ndef public_quote_matches(x):\n    return []\n', FIXTURE.replace('def public_quote_matches(', 'def renamed(')]:
            with self.subTest(source=source[-80:]), self.assertRaisesRegex(ValueError, 'PREFLIGHT_FUNCTION_DRIFT'):
                patch.transform(source.encode(), expected_sha256=patch.sha(source.encode()))

    def test_metadata_or_renderer_statement_drift_is_rejected(self):
        for source in [FIXTURE.replace("'1.2.120'", "'1.2.119'", 1), FIXTURE.replace('include_chat=False', 'include_chat=True')]:
            with self.subTest(source=source[-80:]), self.assertRaises(ValueError):
                patch.transform(source.encode(), expected_sha256=patch.sha(source.encode()))

    def test_patch_cannot_be_applied_twice(self):
        changed = patch.transform(FIXTURE.encode(), expected_sha256=patch.sha(FIXTURE.encode()))
        with self.assertRaisesRegex(ValueError, 'PREFLIGHT_SCOPE_ALREADY_PRESENT'):
            patch.transform(changed, expected_sha256=patch.sha(changed))


if __name__ == '__main__':
    unittest.main()
