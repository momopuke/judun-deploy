import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

src=Path(__file__).with_name('reconcile_v1.py')
spec=importlib.util.spec_from_file_location('reconciler',src)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class DecisionTests(unittest.TestCase):
    def dec(self,a=True,p=True,s=True,t=True,state='STATUS_PASS',timer=True,busy=False):
        return m.decide(a,p,s,t,state,timer,busy)
    def test_idempotent_good(self):self.assertEqual(self.dec(),'ALREADY_HEALTHY')
    def test_stopped_timer_restart(self):self.assertEqual(self.dec(timer=False),'ENABLE_TIMER')
    def test_missing_state_readonly(self):self.assertEqual(self.dec(state='MISSING',timer=False),'FIRST_STATUS')
    def test_missing_timer_unit(self):self.assertEqual(self.dec(t=False,state='MISSING',timer=False),'RESTORE_MISSING_MANAGED_UNITS')
    def test_missing_service_unit(self):self.assertEqual(self.dec(s=False,state='MISSING',timer=False),'RESTORE_MISSING_MANAGED_UNITS')
    def test_no_artifacts(self):self.assertEqual(self.dec(a=False,p=False,s=False,t=False,state='MISSING',timer=False),'INSTALL_FRESH')
    def test_missing_agent_unsafe(self):self.assertEqual(self.dec(a=False,state='MISSING',timer=False),'BLOCK_UNTRUSTED_PARTIAL_CODE')
    def test_missing_key_unsafe(self):self.assertEqual(self.dec(p=False,state='MISSING',timer=False),'BLOCK_UNTRUSTED_PARTIAL_CODE')
    def test_unknown_state_block(self):self.assertEqual(self.dec(state='UNRESOLVED',timer=False),'BLOCK_UNRESOLVED_STATE')
    def test_unknown_active_timer_block(self):self.assertEqual(self.dec(state='MISSING'),'BLOCK_UNVERIFIED_ACTIVE_TIMER')
    def test_running_service_block(self):self.assertEqual(self.dec(busy=True),'BLOCK_SERVICE_RUNNING')
    def test_verified_state_missing_unit_block(self):self.assertEqual(self.dec(t=False),'BLOCK_MISSING_UNIT_AFTER_SUCCESS')

class FileTests(unittest.TestCase):
    def test_canonical_units(self):
        self.assertIn('TimeoutStartSec=900s',m.UNIT_SERVICE)
        self.assertIn('Unit=sc-vps-autodeploy.service',m.UNIT_TIMER_300)
        self.assertNotIn('stripchat-browser-desktop.service',m.UNIT_SERVICE)
    def test_state_valid(self):
        x=dict(last_sequence=1,operation='status',status='applied',code_installed=False,release_id='SC-VPS-v10-20261104-a1')
        self.assertEqual(m.valid_state(json.dumps(x).encode()),'STATUS_PASS')
    def test_state_no_code_flag(self):
        x=dict(last_sequence=1,operation='status',status='applied',release_id='SC-VPS-v10-20261104-a1')
        self.assertEqual(m.valid_state(json.dumps(x).encode()),'UNRESOLVED')
    def test_state_bad_json(self):self.assertEqual(m.valid_state(b'{'),'UNKNOWN')
    def test_empty_state(self):self.assertEqual(m.valid_state(None),'MISSING')
    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'a').write_text('GOOD');(p/'b').symlink_to(p/'a')
            with self.assertRaises(m.Stop):m.safe_read(p/'b')
    def test_foreign_unit_rejected(self):
        with self.assertRaises(m.Stop):m.ensure_known_unit(m.SERVICE,b'bad content',{m.UNIT_SERVICE.encode()})
    def test_missing_unit_created_exact(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'service';m.install_missing_unit(p,m.UNIT_SERVICE)
            self.assertEqual(p.read_text(),m.UNIT_SERVICE)
            with self.assertRaises(m.Stop):m.install_missing_unit(p,m.UNIT_SERVICE)

if __name__=='__main__':unittest.main()