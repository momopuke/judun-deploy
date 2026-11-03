"""Exact legacy apply safety_refused v10 no-commit adoption tests."""
import importlib.util, json, pathlib, tempfile, unittest
from unittest.mock import patch

source=pathlib.Path(__file__).with_name('reconcile_v5.py')
spec=importlib.util.spec_from_file_location('rv5_refusal', source)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def refused(**updates):
    protected={'stripchat-browser-desktop.service':'active', 'stripchat-recorder':'true', 'line-openchat-guard.service':'active'}
    d={'last_sequence':1,'release_id':m.LEGACY_RELEASE,'operation':'apply','status':'safety_refused',
       'utc':'2026-11-04T00:08:00+00:00', 'code_restored':True, 'result':{'exit_code':3, 'output_tail':'SC VPS Rescue v10 | diagnosis_only\nReason: insufficient_reserve'},
       'protected_before':protected,'protected_after':dict(protected)}
    d.update(updates)
    return json.dumps(d,sort_keys=True).encode()


def report(status='diagnosis_only',**changes):
    d={'version':'10.0.0','status':status,'changes':[], 'reason':'insufficient_reserve',
       'utc':'2026-11-04T00:06:00+00:00', 'windows':[]}
    d.update(changes);return d

class LegacyRefusalReceipt(unittest.TestCase):
    def test_exact_legacy_refusal_admissible(self):self.assertTrue(m.legacy_refusal_receipt(refused()))
    def test_no_state(self):self.assertFalse(m.legacy_refusal_receipt(None))
    def test_corrupt_state(self):self.assertFalse(m.legacy_refusal_receipt(b'{broken'))
    def test_wrong_release(self):self.assertFalse(m.legacy_refusal_receipt(refused(release_id='fake')))
    def test_other_sequence(self):self.assertFalse(m.legacy_refusal_receipt(refused(last_sequence=2)))
    def test_boolean_sequence(self):self.assertFalse(m.legacy_refusal_receipt(refused(last_sequence=True)))
    def test_apply_only(self):self.assertFalse(m.legacy_refusal_receipt(refused(operation='status')))
    def test_safety_refused_only(self):self.assertFalse(m.legacy_refusal_receipt(refused(status='applied')))
    def test_exit_3_only(self):self.assertFalse(m.legacy_refusal_receipt(refused(result={'exit_code':2,'output_tail':'SC VPS Rescue v10 | diagnosis_only'})))
    def test_bool_exit_rejected(self):self.assertFalse(m.legacy_refusal_receipt(refused(result={'exit_code':True,'output_tail':'SC VPS Rescue v10 | diagnosis_only'})))
    def test_must_restore_code(self):self.assertFalse(m.legacy_refusal_receipt(refused(code_restored=False)))
    def test_code_installed_schema_rejected(self):self.assertFalse(m.legacy_refusal_receipt(refused(code_installed=False)))
    def test_output_tail_is_v10_diagnosis_only(self):self.assertFalse(m.legacy_refusal_receipt(refused(result={'exit_code':3,'output_tail':'SC VPS Rescue v10 | rollback_completed'})))
    def test_missing_output_tail(self):self.assertFalse(m.legacy_refusal_receipt(refused(result={'exit_code':3})))
    def test_missing_receipt_timestamp(self):self.assertFalse(m.legacy_refusal_receipt(refused(utc=None)))
    def test_unmatched_protected(self):self.assertFalse(m.legacy_refusal_receipt(refused(protected_after={'stripchat-recorder':'false'})))
    def test_unknown_browser(self):self.assertFalse(m.legacy_refusal_receipt(refused(protected_before={'stripchat-browser-desktop.service':'unknown'})))

class V10RunReports(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name);self.runs=self.root/'runs';self.runs.mkdir()
    def add(self, name, obj):
        p=self.runs/name;p.mkdir();(p/'state.json').write_text(json.dumps(obj));return p/'state.json'
    def check(self):return m.v10_diagnosis_only_verified(self.runs)
    def test_missing_runs_block(self):self.assertFalse(self.check())
    def test_sole_diagnosis_pass(self):self.add('20261104T000000Z-1',report());self.assertTrue(self.check())
    def test_receipt_time_matches(self):self.add('20261104T000000Z-1',report());self.assertTrue(m.v10_diagnosis_only_verified(self.runs,refused()))
    def test_report_unrelated_older_run_rejected(self):self.add('20261104T000000Z-1',report(utc='2026-11-03T00:06:00+00:00'));self.assertFalse(m.v10_diagnosis_only_verified(self.runs,refused()))
    def test_report_future_rejected(self):self.add('20261104T000000Z-1',report(utc='2026-11-04T00:09:00+00:00'));self.assertFalse(m.v10_diagnosis_only_verified(self.runs,refused()))
    def test_pending_commit_block(self):self.add('20261104T000000Z-1',report('commit_pending'));self.assertFalse(self.check())
    def test_commit_applied_block(self):self.add('20261104T000000Z-1',report('commit_applied'));self.assertFalse(self.check())
    def test_verified_persistent_block(self):self.add('20261104T000000Z-1',report('persistent_verified'));self.assertFalse(self.check())
    def test_already_persistent_block(self):self.add('20261104T000000Z-1',report('already_persistent_verified'));self.assertFalse(self.check())
    def test_rolled_back_then_diagnosis(self):
        self.add('20261103T000000Z-1',report('rollback_completed'));self.add('20261104T000000Z-1',report());self.assertTrue(self.check())
    def test_latest_rolled_back_not_enough(self):self.add('20261104T000000Z-1',report('rollback_completed'));self.assertFalse(self.check())
    def test_marker_config_before_block(self):self.add('20261104T000000Z-1',report(config_before='present'));self.assertFalse(self.check())
    def test_timer_even_diagnosis_block(self):self.add('20261104T000000Z-1',report(timer='sc-vps-v10-rollback-1.timer'));self.assertFalse(self.check())
    def test_changes_even_diagnosis_block(self):self.add('20261104T000000Z-1',report(changes=['browser_MemoryHigh_persistent']));self.assertFalse(self.check())
    def test_symlinked_run_block(self):
        x=self.add('20261104T000000Z-1',report());x.unlink();x.symlink_to(self.root/'bogus');self.assertFalse(self.check())
    def test_symlinked_runs_block(self):
        x=self.add('20261104T000000Z-1',report());root=self.root/'alias';root.symlink_to(self.runs,target_is_directory=True)
        self.assertFalse(m.v10_diagnosis_only_verified(root))
    def test_invalid_schema_block(self):self.add('20261104T000000Z-1',{'status':'diagnosis_only'});self.assertFalse(self.check())
    def test_corrupt_json_block(self):x=self.add('20261104T000000Z-1',report());x.write_text('not json');self.assertFalse(self.check())
    def test_more_than_256_block(self):
        for i in range(257):self.add(f'{i:04}',report())
        self.assertFalse(self.check())

class RefusalMigration(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.d=pathlib.Path(self.temp.name)
        self.service=self.d/'sc-vps-autodeploy.service';self.timer=self.d/'sc-vps-autodeploy.timer'
        self.home=self.d/'opt';self.home.mkdir();self.agent=self.home/'pull_agent.py';self.pub=self.home/'release-signing-public.pem'
        self.state=self.d/'state'/'state.json';self.state.parent.mkdir();self.backup=self.d/'backup';self.lock=self.d/'state'/'lock'
        self.legacy=b'legacy_exact';self.current=b'current_exact';self.key=b'pinned_key';self.receipt=refused()
        self.service.write_bytes(m.UNIT_SERVICE_260.encode());self.timer.write_bytes(m.UNIT_TIMER_300.encode())
        self.agent.write_bytes(self.legacy);self.pub.write_bytes(self.key);self.state.write_bytes(self.receipt)
        self.active=True;self.events=[]
        objs={'AGENT':self.agent,'SERVICE':self.service,'TIMER':self.timer,'PUB':self.pub,'STATE':self.state,'BACKUP':self.backup}
        self.patchers=[patch.object(m,k,v) for k,v in objs.items()]
        self.patchers.extend([patch.object(m,'AGENT_SHA256',m.digest(self.current)),patch.object(m,'LEGACY_AGENT_SHA256',m.digest(self.legacy)),patch.object(m,'PUB_SHA256',m.digest(self.key)),patch.object(m,'fetch_trusted_agent',lambda:self.current),patch.object(m,'v10_diagnosis_only_verified',return_value=True),patch.object(m,'rollback_watchdogs_clear',return_value=True),patch.object(m,'protected_ok',return_value=None),patch.object(m,'verify_effective_timeout',return_value=None)])
        self.patchers.append(patch.object(m,'systemd_state',side_effect=lambda unit:'active' if 'timer' in unit and self.active else 'inactive'))
        def fake_proc(*args,**kwargs):
            self.events.append(args)
            if args[:3]==('systemctl','stop','sc-vps-autodeploy.timer'):self.active=False
            if args[:3]==('systemctl','start','sc-vps-autodeploy.timer') or args[:3]==('systemctl','enable','--now'):
                self.active=True
            return ''
        self.patchers.append(patch.object(m,'proc',side_effect=fake_proc))
        for p in self.patchers:p.start();self.addCleanup(p.stop)
    def run_migration(self):
        return m.reconcile_verified_legacy(self.service.read_bytes(),self.agent.read_bytes(),self.pub.read_bytes(),self.timer.read_bytes(),self.state.read_bytes(),self.active,False)
    def test_migration_preserves_receipt_and_never_executes_v10(self):
        with patch.object(m,'signed_v10_installed',side_effect=AssertionError('must not inspect installed files from restored state')):
            self.assertEqual(self.run_migration(),0)
        self.assertEqual(self.state.read_bytes(),self.receipt)
        self.assertEqual(self.agent.read_bytes(),self.current)
        self.assertEqual(self.service.read_bytes(),m.UNIT_SERVICE.encode())
        self.assertTrue(self.active)
        self.assertFalse(any('sc-vps-rescue' in str(a) for tup in self.events for a in tup))
    def test_idempotent_migration(self):
        self.run_migration();self.events.clear();self.assertEqual(self.run_migration(),0)
        self.assertEqual(self.state.read_bytes(),self.receipt)
    def test_report_no_commit_blocks_before_mutation(self):
        with patch.object(m,'v10_diagnosis_only_verified',return_value=False):
            with self.assertRaisesRegex(m.Stop,'LEGACY_RECEIPT_UNVERIFIED'):self.run_migration()
        self.assertEqual(self.agent.read_bytes(),self.legacy)
        self.assertTrue(self.active)
    def test_watchdog_pending_blocks(self):
        with patch.object(m,'rollback_watchdogs_clear',return_value=False):
            with self.assertRaisesRegex(m.Stop,'LEGACY_RECEIPT_UNVERIFIED'):self.run_migration()
        self.assertEqual(self.service.read_bytes(),m.UNIT_SERVICE_260.encode())
    def test_failure_rolls_back_agent_unit_and_restores_timer(self):
        with patch.object(m,'verify_effective_timeout',side_effect=m.Stop('timeout invalid')):
            with self.assertRaises(m.Stop):self.run_migration()
        self.assertEqual(self.agent.read_bytes(),self.legacy)
        self.assertEqual(self.service.read_bytes(),m.UNIT_SERVICE_260.encode())
        self.assertTrue(self.active)
    def test_protected_service_change_fails(self):
        with patch.object(m,'protected_ok',side_effect=m.Stop('recorder not active')):
            with self.assertRaises(m.Stop):self.run_migration()
        self.assertEqual(self.agent.read_bytes(),self.legacy)
        self.assertTrue(self.active)

if __name__=='__main__':unittest.main()
