import hashlib
import importlib.util
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
P=HERE/'judun_v190_stage_finalize_v4.py'
spec=importlib.util.spec_from_file_location('judun_v190_stage_finalize_v4',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
ZIP=HERE/'judun_work/Judun_v1.2.190_STAGE_SANDBOX_E2E_R1_UNSIGNED_QA_HOLD.zip'

class StageV4GateTests(unittest.TestCase):
    def setUp(self):
        self.base={
            'JUDUN_STAGING_SESSION':'A'*64,
            'JUDUN_STAGING_ECPAY_SANDBOX':'1',
        }
        self.initial_cmd=['/srv/judun-staging/venv/bin/python','-I','-B','/srv/judun-staging/staging_release.py','serve']

    def test_native_full(self):
        env=dict(self.base,JUDUN_STAGING='1', APP_DATA_DIR='/var/lib/judun-staging',
                 PUBLIC_BASE_URL='https://judun-test.tony870490.chatgpt.site',
                 ENABLE_TEST_MODE='true',COOP_MODE='simulation')
        mode,reason,out=m.stage_environment_gate(env)
        self.assertEqual((mode,reason),('NATIVE','ok'));self.assertEqual(out,env)

    def test_launcher_initial_env_missing_all_late_set_flags(self):
        mode,reason,out=m.stage_environment_gate(self.base,launcher=True)
        self.assertEqual((mode,reason),('LAUNCHER_ATTESTED','ok'))
        for k,value in {'JUDUN_STAGING':'1','APP_DATA_DIR':'/var/lib/judun-staging',
                 'COOP_MODE':'simulation','ENABLE_TEST_MODE':'true',
                 'PUBLIC_BASE_URL':'https://judun-test.tony870490.chatgpt.site'}.items():
            self.assertEqual(out[k],value)
        self.assertNotIn('JUDUN_STAGING',self.base)

    def test_missing_late_flags_do_not_pass_for_other_process(self):
        self.assertEqual(m.stage_environment_gate(self.base)[0],'REJECT')

    def test_initial_explicit_nonstage_flag_reject(self):
        self.assertEqual(m.stage_environment_gate({**self.base,'JUDUN_STAGING':'0'},launcher=True)[0],'REJECT')

    def test_initial_data_path_production_reject(self):
        self.assertEqual(m.stage_environment_gate({**self.base,'APP_DATA_DIR':'/var/www/advisor'},launcher=True)[0],'REJECT')

    def test_initial_data_path_stage_allowed(self):
        for d in m.STAGE_DATA_ROOTS:
            with self.subTest(d=d):self.assertEqual(m.stage_environment_gate({**self.base,'APP_DATA_DIR':d},launcher=True)[0],'LAUNCHER_ATTESTED')

    def test_initial_prod_host_reject(self):
        self.assertEqual(m.stage_environment_gate({**self.base,'PUBLIC_BASE_URL':'https://judun.142-93-91-214.sslip.io'},launcher=True)[0],'REJECT')

    def test_initial_unset_host_can_be_reconstructed(self):
        self.assertEqual(m.stage_environment_gate(self.base,launcher=True)[0],'LAUNCHER_ATTESTED')

    def test_initial_stage_host_allowed(self):
        for host in m.STAGING_HOSTS:
            with self.subTest(host=host):self.assertEqual(m.stage_environment_gate({**self.base,'PUBLIC_BASE_URL':host},launcher=True)[0],'LAUNCHER_ATTESTED')

    def test_explicit_false_test_mode_reject(self):
        self.assertEqual(m.stage_environment_gate({**self.base,'ENABLE_TEST_MODE':'false'},launcher=True)[0],'REJECT')

    def test_explicit_live_coop_reject(self):
        self.assertEqual(m.stage_environment_gate({**self.base,'COOP_MODE':'live'},launcher=True)[0],'REJECT')

    def test_sandbox_absent_reject(self):
        self.assertEqual(m.stage_environment_gate({'JUDUN_STAGING_SESSION':'A'*64},launcher=True)[0],'REJECT')

    def test_session_absent_reject(self):
        self.assertEqual(m.stage_environment_gate({'JUDUN_STAGING_ECPAY_SANDBOX':'1'},launcher=True)[0],'REJECT')

    def test_live_merchant_env_reject(self):
        for k in m.LIVE_ENV_KEYS:
            with self.subTest(k=k):self.assertEqual(m.stage_environment_gate({**self.base,k:'set'},launcher=True)[0],'REJECT')

    def test_worker_import_script_syntax(self):
        compile(m.WORKER,'worker','exec');compile(P.read_text(),'controller','exec')

    def test_pin_R1_original_app_and_pdf_sha(self):
        with zipfile.ZipFile(ZIP) as z:
            self.assertEqual(hashlib.sha256(z.read('payload/app.py')).hexdigest(),m.APP_SHA)
            self.assertEqual(hashlib.sha256(z.read('payload/pdf_queue.py')).hexdigest(),m.PDF_SHA)

    def test_late_env_not_override_original_process(self):
        s=P.read_text();self.assertIn('updated=dict(env,**required)',s)
        self.assertIn('return pid, cwd, cmd, worker_env',s)
        self.assertNotIn('os.environ.update(',s)

    def test_bound_data_samefile_fail_closed(self):
        s=P.read_text();self.assertIn("Path(worker_env['APP_DATA_DIR']) / 'app_data.db').samefile(DB)",s)
        self.assertIn("samefile('/var/lib/judun-staging/app_data.db')",s)

    def test_launcher_unit_mainpid_binding(self):
        s=P.read_text();self.assertIn('pid in launcher_pids and stage_launcher_contract(cmd)',s)
        self.assertIn('if unit==LAUNCHER_UNIT: launcher_pids.add(mainpid)',s)

    def test_root_owned_launcher_contract_positive(self):
        contract = '''STAGE_ROOT = Path("/srv/judun-staging")
STAGE_DATA = Path("/var/lib/judun-staging")
JUDUN_STAGING="1"
ENABLE_TEST_MODE="true"
COOP_MODE="simulation"
APP_DATA_DIR=str(STAGE_DATA)
PUBLIC_BASE_URL=STAGE_URL
sys.path.insert(0, str(path))
from app import app
uvicorn.run(app, host="127.0.0.1", port=8011
'''
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'staging_release.py';f.write_text(contract);f.chmod(0o644)
            with patch.object(m,'LAUNCHER',f):
                cmd=self.initial_cmd[:-2]+[str(f),'serve']
                if os.geteuid()==0:self.assertTrue(m.stage_launcher_contract(cmd))
                f.write_text(contract.replace('ENABLE_TEST_MODE="true"','ENABLE_TEST_MODE="false"'))
                self.assertFalse(m.stage_launcher_contract(cmd))

    def test_untrusted_cmdline_reject(self):
        self.assertFalse(m.stage_launcher_contract(['/usr/bin/python3','/srv/judun-staging/staging_release.py','serve']))
        self.assertFalse(m.stage_launcher_contract(['/srv/judun-staging/venv/bin/python','-I','-B','/var/www/advisor/staging_release.py','serve']))

    def test_do_not_change_live_channel_or_payment(self):
        s=P.read_text()
        self.assertNotIn('channel/stable.json',s)
        self.assertNotIn('UPDATE payment_orders',s)
        self.assertNotIn('systemctl restart',s)

if __name__=='__main__':unittest.main(verbosity=2)