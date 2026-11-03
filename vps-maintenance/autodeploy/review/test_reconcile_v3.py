import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('sc_reconcile_v3',Path(__file__).with_name('reconcile_v3.py'))
r=importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

def digest(b):return hashlib.sha256(b).hexdigest()
class ClassificationTests(unittest.TestCase):
    def test_exact_host_fingerprint(self):
        self.assertEqual(digest(r.UNIT_SERVICE_260.encode()),'ed365efa923a6210147cfdbffd4b812891ea992b5e832bf95ddbad367034e730')
    def test_exact_host_bytes_length(self):self.assertEqual(len(r.UNIT_SERVICE_260.encode()),424)
    def test_old_timeout_detected(self):self.assertEqual(r.service_variant(r.UNIT_SERVICE_260.encode()),'SAFE_260_TIMEOUT_ONLY')
    def test_new_timeout_detected(self):self.assertEqual(r.service_variant(r.UNIT_SERVICE.encode()),'CURRENT')
    def test_service_missing(self):self.assertEqual(r.service_variant(None),'MISSING')
    def test_safe_comments_on_current(self):self.assertEqual(r.service_variant((r.UNIT_SERVICE+'#some comment\n').encode()),'CURRENT')
    def test_old_timeout_comment_variant_blocked(self):self.assertEqual(r.service_variant((r.UNIT_SERVICE_260+'#some comment\n').encode()),'UNKNOWN')
    def test_old_timeout_other_directive_blocked(self):self.assertEqual(r.service_variant((r.UNIT_SERVICE_260+'Environment=SECRET=VALUE\n').encode()),'UNKNOWN')
    def test_old_timeout_changed_exec_blocked(self):self.assertEqual(r.service_variant(r.UNIT_SERVICE_260.replace('ExecStart=/usr/bin/python3','ExecStart=/bin/sh').encode()),'UNKNOWN')
    def test_old_timeout_changed_memory_blocked(self):self.assertEqual(r.service_variant(r.UNIT_SERVICE_260.replace('MemoryMax=180M','MemoryMax=400M').encode()),'UNKNOWN')
    def test_unknown_agent_blocked(self):
        x=r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'bad',r.PUB_SHA256.encode(),r.UNIT_TIMER_180.encode(),None,False,False)
        self.assertEqual(x,'BLOCK_UNKNOWN_AGENT')
    def test_missing_pub_blocks(self):
        with patch.object(r,'agent_variant',return_value='CURRENT'):
            self.assertEqual(r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'fake',None,r.UNIT_TIMER_180.encode(),None,False,False),'BLOCK_UNTRUSTED_PARTIAL_CODE')
    def test_unknown_pub_blocks(self):
        with patch.object(r,'agent_variant',return_value='CURRENT'):
            self.assertEqual(r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'fake',b'fake',r.UNIT_TIMER_180.encode(),None,False,False),'BLOCK_UNKNOWN_TRUST_ROOT')
    def test_unresolved_state_blocked(self):
        with patch.object(r,'agent_variant',return_value='CURRENT'),patch.object(r,'digest',return_value=r.PUB_SHA256):
            self.assertEqual(r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'fake',b'fake',r.UNIT_TIMER_180.encode(),b'garbage',False,False),'BLOCK_UNRESOLVED_STATE')
    def test_unverified_timer_blocked(self):
        with patch.object(r,'agent_variant',return_value='CURRENT'),patch.object(r,'digest',return_value=r.PUB_SHA256):
            self.assertEqual(r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'fake',b'fake',r.UNIT_TIMER_180.encode(),None,True,False),'BLOCK_UNVERIFIED_ACTIVE_TIMER')
    def test_running_service_blocked(self):
        with patch.object(r,'agent_variant',return_value='CURRENT'),patch.object(r,'digest',return_value=r.PUB_SHA256):
            self.assertEqual(r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'fake',b'fake',r.UNIT_TIMER_180.encode(),None,False,True),'BLOCK_SERVICE_RUNNING')
    def test_legacy_agent_with_state_blocked(self):
        state={'last_sequence':1,'operation':'status','status':'applied','code_installed':False,'release_id':'SC-VPS-v10-20261104-a1'}
        with patch.object(r,'agent_variant',return_value='KNOWN_LEGACY'),patch.object(r,'digest',return_value=r.PUB_SHA256):
            self.assertEqual(r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'fake',b'fake',r.UNIT_TIMER_180.encode(),json.dumps(state).encode(),True,False),'BLOCK_LEGACY_AGENT_HAS_HISTORY')
    def test_bad_timer_blocked(self):
        with patch.object(r,'agent_variant',return_value='CURRENT'),patch.object(r,'digest',return_value=r.PUB_SHA256),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(r.reconcile_prechecked(r.UNIT_SERVICE_260.encode(),b'fake',b'fake',b'[Unit]\nExecStart=bad',None,False,False),'BLOCK_UNKNOWN_TIMER_UNIT')
    def test_not_altering_v10_service(self):self.assertNotIn('systemctl restart',Path(r.__file__).read_text())
    def test_agent_pin_immutable(self):self.assertIn('/7219554c0c21ed4031e0856b3749e7fca5b8cd23/',r.AGENT_URL)

class MutationTests(unittest.TestCase):
    def test_backup_exact_bytes(self):
        with tempfile.TemporaryDirectory() as td,patch.object(r,'BACKUP',Path(td)/'backup'):
            p=Path(td)/'service';old=r.UNIT_SERVICE_260.encode();b=r.make_backup(p,old)
            self.assertEqual(b.read_bytes(),old)
            self.assertEqual(b.stat().st_mode & 0o777,0o600)
    def test_backup_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'real').mkdir();(p/'link').symlink_to(p/'real')
            with patch.object(r,'BACKUP',p/'link'),self.assertRaisesRegex(r.Stop,'BACKUP_DIRECTORY_UNSAFE'):
                r.make_backup(p/'service',b'old')
    def test_atomic_update_exact(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'file';p.write_bytes(b'old');p.chmod(0o644)
            r.atomic_update_existing(p,b'old',b'new')
            self.assertEqual(p.read_bytes(),b'new')
            self.assertEqual(p.stat().st_mode&0o777,0o644)
    def test_atomic_update_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'file';p.write_bytes(b'old')
            with self.assertRaisesRegex(r.Stop,'CONCURRENT_FILE_CHANGE'):r.atomic_update_existing(p,b'wrong',b'new')
            self.assertEqual(p.read_bytes(),b'old')
    def test_atomic_update_symlink_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'real').write_bytes(b'old');(p/'link').symlink_to(p/'real')
            with self.assertRaisesRegex(r.Stop,'SYMLINK_NOT_ALLOWED'):r.atomic_update_existing(p/'link',b'old',b'new')
            self.assertEqual((p/'real').read_bytes(),b'old')

class MainIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        d=Path(self.tmp.name);self.d=d
        for k,v in [('BASE',d/'code'),('AGENT',d/'code/pull_agent.py'),('PUB',d/'code/release-signing-public.pem'),('STATE',d/'state/state.json'),('SERVICE',d/'sc-vps-autodeploy.service'),('TIMER',d/'sc-vps-autodeploy.timer'),('BACKUP',d/'backups'),('ENROLL_LOCK',d/'enroll.lock')]:
            t=patch.object(r,k,v);t.start();self.addCleanup(t.stop)
        r.BASE.mkdir();r.STATE.parent.mkdir()
        self.old=b'old agent';self.new=b'new agent';self.pub=b'known key'
        for k,v in [('AGENT_SHA256',digest(self.new)),('LEGACY_AGENT_SHA256',digest(self.old)),('PUB_SHA256',digest(self.pub))]:
            t=patch.object(r,k,v);t.start();self.addCleanup(t.stop)
        r.PUB.write_bytes(self.pub)
        r.TIMER.write_text(r.UNIT_TIMER_180)
        r.SERVICE.write_text(r.UNIT_SERVICE_260)
        self.timer_running=False
        t=patch.object(r,'systemd_state',side_effect=lambda unit:'active' if 'timer' in unit and self.timer_running else 'inactive')
        t.start();self.addCleanup(t.stop)
        for attr,fx in [('protected_ok',lambda:None),('proc',lambda *a,**kw:''),('fetch_trusted_agent',lambda:self.new)]:
            t=patch.object(r,attr,side_effect=fx);t.start();self.addCleanup(t.stop)
        self.started=0
        def fake_first():
            self.started+=1
            r.STATE.write_text(json.dumps({'last_sequence':1,'operation':'status','status':'applied','code_installed':False,'release_id':'SC-VPS-v10-20261104-a1'}))
        t=patch.object(r,'run_first_status',side_effect=fake_first);t.start();self.addCleanup(t.stop)
        t=patch.object(r,'enable_timer',side_effect=lambda:setattr(self,'timer_running',True));t.start();self.addCleanup(t.stop)
        self.lock=Path('/run/sc-vps-autodeploy-enroll.lock')
        # No second agent on this test host; lock is released at program exit.
    def call(self):
        with patch.object(r.os,'geteuid',return_value=0),patch.object(r.sys,'argv',['r3']):
            with contextlib.redirect_stdout(io.StringIO()) as cap:
                rc=r.main()
            return rc,cap.getvalue()
    def test_trusted_legacy_agent_and_260_upgrade_once(self):
        r.AGENT.write_bytes(self.old)
        rc,out=self.call()
        self.assertEqual(rc,0)
        self.assertTrue(self.timer_running)
        self.assertEqual(self.started,1)
        self.assertEqual(r.AGENT.read_bytes(),self.new)
        self.assertEqual(r.SERVICE.read_text(),r.UNIT_SERVICE)
        self.assertIn('ENROLLMENT_RECOVERED_AND_VERIFIED',out)
        self.assertEqual(len(list(r.BACKUP.glob('*.bak'))),2)
    def test_known_current_agent_260_upgrade(self):
        r.AGENT.write_bytes(self.new)
        rc,out=self.call()
        self.assertEqual(rc,0)
        self.assertEqual(self.started,1)
        self.assertEqual(len(list(r.BACKUP.glob('*.bak'))),1)
        self.assertEqual(r.SERVICE.read_text(),r.UNIT_SERVICE)
    def test_readonly_status_failure_restores_files(self):
        r.AGENT.write_bytes(self.old)
        with patch.object(r,'run_first_status',side_effect=r.Stop('SIMULATED_FAIL')):
            with self.assertRaisesRegex(r.Stop,'SIMULATED_FAIL'):self.call()
        self.assertEqual(r.AGENT.read_bytes(),self.old)
        self.assertEqual(r.SERVICE.read_text(),r.UNIT_SERVICE_260)
        self.assertFalse(self.timer_running)
    def test_unknown_agent_prevents_any_mutation(self):
        r.AGENT.write_bytes(b'invalid')
        with self.assertRaisesRegex(r.Stop,'BLOCK_UNKNOWN_AGENT'):self.call()
        self.assertEqual(r.SERVICE.read_text(),r.UNIT_SERVICE_260)
        self.assertFalse(r.BACKUP.exists())
    def test_status_pass_timer_active_upgrades_timeout_not_runs_status(self):
        r.AGENT.write_bytes(self.new)
        self.timer_running=True
        r.STATE.write_text(json.dumps({'last_sequence':1,'operation':'status','status':'applied','code_installed':False,'release_id':'SC-VPS-v10-20261104-a1'}))
        rc,out=self.call()
        self.assertEqual(rc,0)
        self.assertEqual(self.started,0)
        self.assertEqual(r.SERVICE.read_text(),r.UNIT_SERVICE)
        self.assertIn('ENROLLMENT_RECOVERED_AND_VERIFIED',out)
    def test_unresolved_state_no_mutation(self):
        r.AGENT.write_bytes(self.new)
        r.STATE.write_text(json.dumps({'last_sequence':1,'operation':'apply','status':'in_progress'}))
        with self.assertRaisesRegex(r.Stop,'BLOCK_UNRESOLVED_STATE'):self.call()
        self.assertEqual(r.SERVICE.read_text(),r.UNIT_SERVICE_260)
    def test_foreign_service_no_mutation(self):
        r.AGENT.write_bytes(self.new)
        r.SERVICE.write_text(r.UNIT_SERVICE_260.replace('ExecStart=/usr/bin/python3','ExecStart=/bin/sh'))
        with self.assertRaisesRegex(r.Stop,'BLOCK_UNKNOWN_SERVICE_UNIT'):self.call()
        self.assertFalse(r.BACKUP.exists())
    def test_legacy_agent_status_pass_no_mutation(self):
        r.AGENT.write_bytes(self.old)
        self.timer_running=True
        r.STATE.write_text(json.dumps({'last_sequence':1,'operation':'status','status':'applied','code_installed':False,'release_id':'SC-VPS-v10-20261104-a1'}))
        with self.assertRaisesRegex(r.Stop,'BLOCK_LEGACY_AGENT_HAS_HISTORY'):self.call()
        self.assertFalse(r.BACKUP.exists())

if __name__=='__main__':unittest.main()
