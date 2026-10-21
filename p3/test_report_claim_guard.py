import ast
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_claim_guard_functions import _judun_guard_report_claims as guard, _judun_risk_score as risk
import report_claim_guard_patch as patch

FIXTURE = '''APP_VERSION = '1.2.122'
RELEASE_REVISION = '1.2.122'
BUILD_SIGNATURE = 'JUDUN_1.2.122_QUOTE_FACT_GROUNDING_20261021'
ANALYSIS_CACHE_VERSION = 'analysis_v122_quote_grounding_v1'
CORE_CACHE_VERSION = 'core_v122_quote_grounding_v1'
ITEM_CACHE_VERSION = 'item_v122_quote_grounding_v1'
THEME_CACHE_VERSION = 'theme_v122_quote_grounding_v1'
QUOTE_FACT_GROUNDING_RULES = 'Existing grounding rules'

def compare_risk(data):
        try:return float(str(data.get('risk_score') or '').split('/')[0].strip())
        except:return None

def core_prompt():
    return {"risk_score": "依本案資料判定；資料不足須說明"}

def _judun_guard_report_totals(data, raw_items):
    result = dict(data)
    return result

def build_html_report(data):
    return _judun_guard_report_totals(data, [])

def build_report_context_from_job(data):
    return _judun_guard_report_totals(data, [])
'''

class ReportClaimGuardTests(unittest.TestCase):
    def test_unknown_scale_is_not_guessed(self):
        for value in [28,100, '28', '28/100','120/10','-1/10',None,True,False,'NaN','Infinity','1e200','5/0','5/100','5/10<script>']:
            with self.subTest(value=value):self.assertEqual(risk(value),'待核對')

    def test_known_scale_preserves_numeric_precision(self):
        for value, expected in [(0,'0/10'),(10,'10/10'),('2.8/10','2.8/10'),(' 5.25 / 10 ','5.25/10'),(7.5,'7.5/10'),('5.000','5/10')]:
            with self.subTest(value=value):self.assertEqual(risk(value),expected)

    def test_model_only_market_claim_is_qualified_and_amount_unchanged(self):
        data={'risk_score':28,'original_total_price':82200,'advisor_summary':'工項單價與公開市場行情相符；油漆已寫批土一道、乳膠漆二道。','final_decision':'本案工項與價格皆屬合理範圍，並無重大惡意缺漏，補齊品牌即可安心簽約。','items_analysis':[{'source_level':'C','original_price':30000,'reference_price_low':24000,'reference_price_high':38000,'comment':'單價1,500元落在一般市場合理區間','note':'客戶原單：符合市場區間','url':'https://example.com/符合市場區間'}]}
        before=copy.deepcopy(data);out=guard(data)
        self.assertEqual(data,before)
        self.assertEqual(out['risk_score'],'待核對')
        self.assertEqual(out['original_total_price'],82200)
        for key in ['original_price','reference_price_low','reference_price_high','note','url']:
            self.assertEqual(out['items_analysis'][0][key],data['items_analysis'][0][key])
        self.assertNotIn('市場行情相符',out['advisor_summary'])
        self.assertIn('批土一道、乳膠漆二道',out['advisor_summary'])
        self.assertNotIn('即可安心簽約',out['final_decision'])
        self.assertNotIn('落在一般市場合理區間',out['items_analysis'][0]['comment'])

    def test_verified_evidence_commentary_is_not_rewritten(self):
        for level in ['A','B']:
            data={'risk_score':'2.8/10','advisor_summary':'本案價格與公開市場行情相符','items_analysis':[{'source_level':level}]}
            self.assertEqual(guard(data),data)

    def test_negated_claims_remain_negated_and_unchanged(self):
        value='不代表符合市場區間；不得宣稱即可安心簽約。'
        self.assertEqual(guard({'advisor_summary':value,'items_analysis':[{'source_level':'C'}]})['advisor_summary'],value)

    def test_nested_guides_and_categories_are_consistent(self):
        data={'items_analysis':[{'source_level':'C'}],'categories':[{'comment':'單價1,800元符合市場區間'}],'advanced_guides':{'g1':'補齊即可進行簽約動工'}}
        out=guard(data);self.assertIn('模型情境',out['categories'][0]['comment']);self.assertNotIn('即可進行',out['advanced_guides']['g1'])

    def test_unknown_evidence_shape_does_not_trigger_broad_claim_rewrite(self):
        for rows in [None,[],[None],[{'source_level':'unknown'}]]:
            data={'advisor_summary':'本案價格與公開市場行情相符','items_analysis':rows}
            self.assertEqual(guard(data)['advisor_summary'],data['advisor_summary'])

    def test_html_and_export_context_share_the_same_guard_without_mutation(self):
        raw=FIXTURE.encode();changed=patch.transform(raw,expected_sha256=patch.sha(raw));ns={};exec(changed,ns)
        data={'risk_score':28,'advisor_summary':'工項單價與公開市場行情相符','items_analysis':[{'source_level':'C','original_price':82200}]};before=copy.deepcopy(data)
        screen=ns['build_html_report'](data);pdf=ns['build_report_context_from_job'](data)
        self.assertEqual(screen,pdf);self.assertEqual(screen['risk_score'],'待核對');self.assertEqual(data,before)
        self.assertIsNone(ns['compare_risk'](data));self.assertEqual(ns['compare_risk']({'risk_score':'2.8/10'}),2.8)
        self.assertEqual(ns['APP_VERSION'],'1.2.123')

    def test_sha_or_source_drift_is_refused(self):
        with self.assertRaisesRegex(ValueError,'CURRENT_APP_SHA_MISMATCH'):patch.transform(FIXTURE.encode())
        raw=FIXTURE.replace('    return result','    return {"drift": True}').encode()
        with self.assertRaisesRegex(ValueError,'RENDER_GUARD_RETURN_DRIFT'):patch.transform(raw,expected_sha256=patch.sha(raw))

    def test_unsigned_apply_does_not_modify_application(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'release.json').write_text('{}');(root/'app.py').write_bytes(b'protected')
            with self.assertRaisesRegex(ValueError,'SIGNED_INNER_IDENTITY_MISMATCH'):patch.apply_signed_patch(root,root)
            self.assertEqual((root/'app.py').read_bytes(),b'protected')

if __name__ == '__main__':unittest.main()
