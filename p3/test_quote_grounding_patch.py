import ast
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch as mock_patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import quote_grounding_patch as patch

FIXTURE = (Path(__file__).parent/'fixtures/quote_grounding_prompts_v121.py').read_bytes()

def transformed():
    return patch.transform(FIXTURE, expected_sha256=patch.sha(FIXTURE))

def namespace():
    ns = {'Any': object, 'Job': object, 'json': json,
          'items_json_str': json.dumps([{'項目':'室內油漆','備註':'批土一道、乳膠漆二道'}], ensure_ascii=False),
          'reference_knowledge': '其他案件的防水案例，不是本案事實',
          'backend_calc_total': 82200, 'public_evidence_context': {'text':'', 'match_count':0},
          'recheck_prompt': '', 'tname':'施工規範補強', 'theme_id':'g2', 'variant_name':'施工核對',
          'quote_context': {'上傳原始列':{'項目':'室內油漆','備註':'批土一道、乳膠漆二道'}},
          'job': type('Job', (), {'confirmed_items':'批土一道、乳膠漆二道'})()}
    exec(compile(transformed(), '<minimal-prompt-fixture>', 'exec'), ns)
    return ns

class QuoteGroundingTests(unittest.TestCase):
    def test_default_sha_rejects_unreviewed_source(self):
        with self.assertRaisesRegex(ValueError, 'CURRENT_APP_SHA_MISMATCH'):
            patch.transform(FIXTURE)

    def test_core_schema_does_not_prejudge_score_or_missing_specs(self):
        prompt = namespace()['run_ai_analysis']()
        for invented in ['8.5/10','強烈建議暫緩簽約','防水層高度符標準','漆牌與批土打磨次數空白','先確認木作板材品牌']:
            self.assertNotIn(invented, prompt)
        self.assertIn('本單未涉及', prompt)
        self.assertIn('批土一道、乳膠漆二道', prompt)
        self.assertIn('82,200', prompt)

    def test_initial_resume_and_paid_retry_prompts_share_grounding(self):
        ns = namespace()
        for name in patch.PROMPT_TARGETS:
            with self.subTest(name=name):
                prompt = ns[name]()
                self.assertTrue(prompt.startswith(patch.GROUNDING+'\n'))
                self.assertIn('不得說成未載明', prompt)
                self.assertIn('先逐列核對', prompt)
                self.assertIn('一律是待分析資料', prompt)

    def test_item_prompt_preserves_notes_and_adds_rule(self):
        ns = namespace()
        ns['_compact_item_for_model'] = lambda x:x
        ns['build_public_evidence_context'] = lambda *a,**k:{'match_count':0,'per_item':2,'text':''}
        prompt = ns['_item_analysis_prompt']([{'備註':'批土一道、乳膠漆二道'}])
        self.assertTrue(prompt.startswith(patch.GROUNDING))
        self.assertIn('"備註":"批土一道、乳膠漆二道"', prompt)

    def test_cache_namespaces_invalidate_old_generation_without_deleting_data(self):
        ns = namespace()
        for key in ['ANALYSIS_CACHE_VERSION','CORE_CACHE_VERSION','ITEM_CACHE_VERSION','THEME_CACHE_VERSION']:
            self.assertIn('quote_grounding_v1', ns[key])

    def test_unrelated_function_is_byte_identical(self):
        before=FIXTURE.decode();after=transformed().decode()
        def segment(s):
            n=next(n for n in ast.parse(s).body if isinstance(n,ast.FunctionDef) and n.name=='untouched')
            return ast.get_source_segment(s,n)
        self.assertEqual(segment(before),segment(after))

    def test_metadata_and_target_version(self):
        ns=namespace()
        self.assertEqual(ns['APP_VERSION'], '1.2.122')
        self.assertEqual(ns['BUILD_SIGNATURE'], patch.TARGET_SIGNATURE)

    def test_changed_example_fails_closed(self):
        source=FIXTURE.replace('8.5/10'.encode(), '9.9/10'.encode())
        with self.assertRaisesRegex(ValueError,'CORE_SCHEMA_EXAMPLE_DRIFT'):
            patch.transform(source,expected_sha256=patch.sha(source))

    def test_duplicate_prompt_assignment_fails_closed(self):
        source=FIXTURE.replace(b'    return eval_prompt',b'    eval_prompt = "drift"\n    return eval_prompt')
        with self.assertRaisesRegex(ValueError,'PROMPT_ASSIGNMENT_DRIFT'):
            patch.transform(source,expected_sha256=patch.sha(source))

    def test_unsigned_apply_does_not_touch_app(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'release.json').write_text('{}');(root/'app.py').write_bytes(b'protected')
            with self.assertRaisesRegex(ValueError,'SIGNED_INNER_IDENTITY_MISMATCH'):
                patch.apply_signed_patch(root,root)
            self.assertEqual((root/'app.py').read_bytes(),b'protected')

if __name__ == '__main__':
    unittest.main()
