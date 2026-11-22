import hashlib
import importlib.util
import io
import unittest
import zipfile
from pathlib import Path

HERE=Path(__file__).parent
P=HERE/'judun_v190_stage_finalize_v3.py'
spec=importlib.util.spec_from_file_location('judun_v190_stage_finalize_v3',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ZIP=HERE/'judun_work/Judun_v1.2.190_STAGE_SANDBOX_E2E_R1_UNSIGNED_QA_HOLD.zip'

class StageGateTests(unittest.TestCase):
    def setUp(self):
        self.e={
            'APP_DATA_DIR':'/var/lib/judun-staging',
            'JUDUN_STAGING_ECPAY_SANDBOX':'1',
            'PUBLIC_BASE_URL':'https://judun-stage.142-93-91-214.sslip.io',
            'ENABLE_TEST_MODE':'true',
            'COOP_MODE':'simulation',
            'JUDUN_STAGING_SESSION':'A'*40,
        }
    def test_r1_pin_source(self):
        with zipfile.ZipFile(ZIP) as z:
            for filename,expected in [('payload/app.py',m.APP_SHA),('payload/pdf_queue.py',m.PDF_SHA)]:
                self.assertEqual(hashlib.sha256(z.read(filename)).hexdigest(),expected)
    def test_worker_compiles(self):
        compile(m.WORKER,'<one-shot-worker>','exec')
    def test_native_flag(self):
        e={**self.e,'JUDUN_STAGING':'1'}
        self.assertEqual(m.stage_environment_gate(e),('NATIVE','ok'))
    def test_missing_flag_with_strong_stage_evidence(self):
        self.assertEqual(m.stage_environment_gate(self.e),('HTTP_ATTESTED','ok'))
    def test_empty_flag_with_strong_stage_evidence(self):
        self.assertEqual(m.stage_environment_gate({**self.e,'JUDUN_STAGING':''}),('HTTP_ATTESTED','ok'))
    def test_explicit_false_failclosed(self):
        self.assertEqual(m.stage_environment_gate({**self.e,'JUDUN_STAGING':'0'})[0],'REJECT')
    def test_missing_sandbox_failclosed(self):
        e={k:v for k,v in self.e.items() if k!='JUDUN_STAGING_ECPAY_SANDBOX'}
        self.assertEqual(m.stage_environment_gate(e)[0],'REJECT')
    def test_prod_directory_rejected(self):
        self.assertEqual(m.stage_environment_gate({**self.e,'APP_DATA_DIR':'/var/www/advisor'})[0],'REJECT')
    def test_wrong_public_host_rejected(self):
        self.assertEqual(m.stage_environment_gate({**self.e,'PUBLIC_BASE_URL':'https://judun.142-93-91-214.sslip.io'})[0],'REJECT')
    def test_live_ecpay_rejected(self):
        for k in m.LIVE_ENV_KEYS:
            with self.subTest(k=k):
                self.assertEqual(m.stage_environment_gate({**self.e,k:'exists'})[0],'REJECT')
    def test_missing_session_rejected(self):
        self.assertEqual(m.stage_environment_gate({**self.e,'JUDUN_STAGING_SESSION':''})[0],'REJECT')
    def test_test_mode_rejected(self):
        self.assertEqual(m.stage_environment_gate({**self.e,'ENABLE_TEST_MODE':'false'})[0],'REJECT')
    def test_coop_mode_rejected(self):
        self.assertEqual(m.stage_environment_gate({**self.e,'COOP_MODE':'live'})[0],'REJECT')
    def test_dynamicuser_directories_allowed(self):
        for d in m.STAGE_DATA_ROOTS:
            with self.subTest(d=d):
                self.assertEqual(m.stage_environment_gate({**self.e,'APP_DATA_DIR':d})[0],'HTTP_ATTESTED')
    def test_file_not_prod_imports(self):
        c=P.read_text()
        self.assertIn("appdir.resolve().is_relative_to(Path('/srv/judun-staging'))",c)
        self.assertIn("samefile('/var/lib/judun-staging/app_data.db')",c)
    def test_no_changes_to_payment_or_live_release(self):
        c=P.read_text()
        self.assertNotIn('UPDATE payment_orders ', c)
        self.assertNotIn('channel/stable.json',c)

if __name__=='__main__':unittest.main(verbosity=2)