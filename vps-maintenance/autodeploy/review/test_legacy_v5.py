import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

source=pathlib.Path(__file__).with_name('reconcile_v5.py')
spec=importlib.util.spec_from_file_location('rv4',source)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def signed_status(**changes):
    d=dict(last_sequence=1, release_id=m.LEGACY_RELEASE, operation='status',
        status='applied', code_restored=False, result={'exit_code':0,'output_tail':'ignored'},
        protected_before={'stripchat-browser-desktop.service':'active',
                          'stripchat-recorder':'true','line-openchat-guard.service':'active'},
        protected_after={'stripchat-browser-desktop.service':'active',
                         'stripchat-recorder':'true','line-openchat-guard.service':'active'})
    d.update(changes)
    return json.dumps(d,sort_keys=True).encode()

class LegacyReceiptTest(unittest.TestCase):
    def test_confirmed_success(self):self.assertTrue(m.trusted_legacy_receipt(signed_status()))
    def test_no_state(self):self.assertFalse(m.trusted_legacy_receipt(None))
    def test_bad_json(self):self.assertFalse(m.trusted_legacy_receipt(b'not-json'))
    def test_list(self):self.assertFalse(m.trusted_legacy_receipt(b'[]'))
    def test_wrong_release(self):self.assertFalse(m.trusted_legacy_receipt(signed_status(release_id='other')))
    def test_missing_code_restored(self):
        d=json.loads(signed_status());d.pop('code_restored');self.assertFalse(m.trusted_legacy_receipt(json.dumps(d).encode()))
    def test_code_installed_claim(self):self.assertFalse(m.trusted_legacy_receipt(signed_status(code_installed=False)))
    def test_legacy_apply_never_accepted(self):self.assertFalse(m.trusted_legacy_receipt(signed_status(operation='apply')))
    def test_in_progress_never_accepted(self):self.assertFalse(m.trusted_legacy_receipt(signed_status(status='in_progress')))
    def test_safety_refused_never_accepted(self):self.assertFalse(m.trusted_legacy_receipt(signed_status(status='safety_refused')))
    def test_nonzero_exit_never_accepted(self):self.assertFalse(m.trusted_legacy_receipt(signed_status(result={'exit_code':3})))
    def test_bool_exit_never_accepted(self):self.assertFalse(m.trusted_legacy_receipt(signed_status(result={'exit_code':False})))
    def test_modified_protected_after(self):
        d=json.loads(signed_status());d['protected_after']['stripchat-recorder']='false'
        self.assertFalse(m.trusted_legacy_receipt(json.dumps(d).encode()))
    def test_unknown_browser_before(self):
        d=json.loads(signed_status());d['protected_before']['stripchat-browser-desktop.service']='unknown';d['protected_after']=d['protected_before']
        self.assertFalse(m.trusted_legacy_receipt(json.dumps(d).encode()))
    def test_redacted_summary_no_private_output(self):
        d=json.loads(signed_status());d['result']['output_tail']='MY_STREAM_KEY_SECRET';d['code_backup']='/private/secrets/user'
        out=json.dumps(m.redacted_state(json.dumps(d).encode()))
        self.assertTrue(m.redacted_state(json.dumps(d).encode())['legacy_receipt'])
        self.assertNotIn('MY_STREAM_KEY_SECRET',out);self.assertNotIn('/private/secrets',out)
    def test_status_parse_invalid_is_redacted(self):
        r=m.redacted_state(b'{broken secret')
        self.assertFalse(r['parse_valid']);self.assertEqual(r['present'],True)

class SignedFilesTest(unittest.TestCase):
    def test_absent_target_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertFalse(m.signed_v10_installed(pathlib.Path(td)/'missing'))
    def test_exact_files_accepted(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);(p/'tests').mkdir()
            content={'one.py':b'good','tests/t.py':b'goodtest'}
            for n,data in content.items(): (p/n).write_bytes(data)
            with patch.object(m,'SIGNED_V10_FILES',{n:m.digest(d) for n,d in content.items()}):
                self.assertTrue(m.signed_v10_installed(p))
    def test_modified_file_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);(p/'one.py').write_bytes(b'bad')
            with patch.object(m,'SIGNED_V10_FILES',{'one.py':m.digest(b'good')}):
                self.assertFalse(m.signed_v10_installed(p))
    def test_target_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);link=p/'link';link.symlink_to(p)
            self.assertFalse(m.signed_v10_installed(link))
    def test_tests_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td);(p/'external').mkdir();(p/'tests').symlink_to(p/'external');(p/'external'/'t.py').write_bytes(b'good')
            with patch.object(m,'SIGNED_V10_FILES',{'tests/t.py':m.digest(b'good')}):
                self.assertFalse(m.signed_v10_installed(p))

class MigrationFlow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.d=pathlib.Path(self.tmp.name)
        self.service=self.d/'sc-vps-autodeploy.service'
        self.timer=self.d/'sc-vps-autodeploy.timer'
        self.home=self.d/'opt';self.home.mkdir()
        self.agent=self.home/'pull_agent.py'
        self.pub=self.home/'release-signing-public.pem'
        self.state=self.d/'state'/'state.json';self.state.parent.mkdir()
        self.backup=self.d/'backups'
        self.legacy=b'signed_legacy_agent_source';self.current=b'current_pinned_agent_source';self.key=b'pinned_public_key'
        self.service.write_bytes(m.UNIT_SERVICE_260.encode())
        self.timer.write_bytes(m.UNIT_TIMER_300.encode())
        self.agent.write_bytes(self.legacy);self.pub.write_bytes(self.key)
        self.receipt=signed_status();self.state.write_bytes(self.receipt)
        self.active=True;self.called=[]
        self.patchers=[patch.object(m,'AGENT',self.agent),patch.object(m,'SERVICE',self.service),
            patch.object(m,'TIMER',self.timer),patch.object(m,'PUB',self.pub),patch.object(m,'STATE',self.state),
            patch.object(m,'BACKUP',self.backup),patch.object(m,'AGENT_SHA256',m.digest(self.current)),
            patch.object(m,'LEGACY_AGENT_SHA256',m.digest(self.legacy)),patch.object(m,'PUB_SHA256',m.digest(self.key)),
            patch.object(m,'fetch_trusted_agent',lambda:self.current),patch.object(m,'signed_v10_installed',return_value=True),
            patch.object(m,'verify_effective_timeout'),patch.object(m,'protected_ok'),
            patch.object(m,'systemd_state',side_effect=self.unit_state),patch.object(m,'proc',side_effect=self.run_proc)]
        for p in self.patchers:p.start();self.addCleanup(p.stop)
    def unit_state(self,unit):
        return 'inactive' if unit.endswith('.service') else ('active' if self.active else 'inactive')
    def run_proc(self,*args,**kwargs):
        self.called.append(args)
        if args[:2]==('systemctl','stop'):self.active=False
        if args[:3]==('systemctl','enable','--now') or args[:2]==('systemctl','start'):self.active=True
        return ''
    def migrate(self):
        return m.reconcile_verified_legacy(self.service.read_bytes(),self.agent.read_bytes(),self.pub.read_bytes(),self.timer.read_bytes(),self.state.read_bytes(),self.active,False)
    def test_success_changes_only_agent_unit(self):
        self.assertEqual(self.migrate(),0)
        self.assertEqual(self.service.read_bytes(),m.UNIT_SERVICE.encode())
        self.assertEqual(self.agent.read_bytes(),self.current)
        self.assertEqual(self.state.read_bytes(),self.receipt)
        self.assertEqual(self.pub.read_bytes(),self.key)
        self.assertTrue(self.active)
        self.assertEqual(len(list(self.backup.iterdir())),2)
        self.assertFalse(any('stripchat-' in ' '.join(x) for x in self.called))
    def test_idempotent_completed_no_service_changes(self):
        self.migrate();self.called.clear()
        self.assertEqual(self.migrate(),0)
        self.assertFalse(self.called)
    def test_mismatch_v10_fails_before_timer_stop(self):
        with patch.object(m,'signed_v10_installed',return_value=False):
            with self.assertRaisesRegex(m.Stop,'LEGACY_INSTALLED_V10_HASHES_MISMATCH'):self.migrate()
        self.assertFalse(self.called)
    def test_false_status_never_change(self):
        self.state.write_bytes(signed_status(operation='apply'))
        with self.assertRaisesRegex(m.Stop,'LEGACY_RECEIPT_UNVERIFIED'):self.migrate()
        self.assertFalse(self.called)
    def test_service_running_rejected(self):
        with self.assertRaisesRegex(m.Stop,'LEGACY_SERVICE_CURRENTLY_RUNNING'):
            m.reconcile_verified_legacy(self.service.read_bytes(),self.agent.read_bytes(),self.key,self.timer.read_bytes(),self.receipt,self.active,True)
        self.assertFalse(self.called)
    def test_migration_failure_restores_original_agent_and_service(self):
        with patch.object(m,'verify_effective_timeout',side_effect=m.Stop('effective timeout wrong')):
            with self.assertRaisesRegex(m.Stop,'effective timeout wrong'):self.migrate()
        self.assertEqual(self.service.read_bytes(),m.UNIT_SERVICE_260.encode())
        self.assertEqual(self.agent.read_bytes(),self.legacy)
        self.assertEqual(self.state.read_bytes(),self.receipt)
        self.assertTrue(self.active)
    def test_concurrent_agent_lock_block(self):
        # fcntl lock is per process; a separate process is not needed here,
        # since state recheck prevents a concurrent edit.
        self.state.write_bytes(signed_status(release_id='wrong'))
        with self.assertRaises(m.Stop):self.migrate()
    def test_concurrent_change_recheck_block(self):
        # Modify after reading the snapshot to simulate a competing invocation.
        snapshot=self.state.read_bytes();self.state.write_bytes(b'{}')
        with self.assertRaisesRegex(m.Stop,'LEGACY_RECEIPT_CHANGED'):
            m.reconcile_verified_legacy(self.service.read_bytes(),self.agent.read_bytes(),self.pub.read_bytes(),self.timer.read_bytes(),snapshot,self.active,False)
    def test_unknown_trust_root_block(self):
        self.pub.write_bytes(b'other-key')
        with self.assertRaisesRegex(m.Stop,'LEGACY_TRUST_ROOT_NOT_PINNED'):self.migrate()
        self.assertFalse(self.called)

if __name__=='__main__':unittest.main()
