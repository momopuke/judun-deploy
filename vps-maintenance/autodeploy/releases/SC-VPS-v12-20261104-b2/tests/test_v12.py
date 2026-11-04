import os
import sys
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import SC_VPS_Rescue_v12 as m

class V12GuardTests(unittest.TestCase):
    def w(self, **kw):
        r={'seconds':12,'memory_full_pct':34.0,'io_full_pct':0,
           'high_events_per_s':800.,'major_faults_per_s':60.,
           'oom_kill':0,'available_mib':470,'swap_free_mib':500}
        r.update(kw);return r
    def test_successful_baseline(self):self.assertIsNone(m.eligible(self.w()))
    def test_readout_gaps_refuse(self):
        for k in self.w():
            self.assertEqual(m.eligible(self.w(**{k:None})),'counters_missing')
    def test_short_sample_refuses(self):self.assertEqual(m.eligible(self.w(seconds=7)),'counters_missing')
    def test_low_ram_refuses(self):self.assertEqual(m.eligible(self.w(available_mib=429)),'insufficient_host_reserve')
    def test_low_swap_refuses(self):self.assertEqual(m.eligible(self.w(swap_free_mib=349)),'insufficient_host_reserve')
    def test_io_refuses(self):self.assertEqual(m.eligible(self.w(io_full_pct=5.1)),'io_full_unsafe')
    def test_oom_refuses(self):self.assertEqual(m.eligible(self.w(oom_kill=1)),'oom_event')
    def test_faults_refuses(self):self.assertEqual(m.eligible(self.w(major_faults_per_s=251)),'heavy_disk_faults')
    def test_pressure_not_causal_refuses(self):self.assertEqual(m.eligible(self.w(memory_full_pct=16)),'no_causal_memory_stall')
    def test_high_events_not_causal_refuses(self):self.assertEqual(m.eligible(self.w(high_events_per_s=79)),'no_causal_memory_stall')
    def test_post_oom_refuses(self):self.assertEqual(m.danger(self.w(oom_kill=1)),'oom_event_after_change')
    def test_post_ram_refuses(self):self.assertEqual(m.danger(self.w(available_mib=369)),'reserve_too_low_after_change')
    def test_post_swap_refuses(self):self.assertEqual(m.danger(self.w(swap_free_mib=279)),'reserve_too_low_after_change')
    def test_post_io_refuses(self):self.assertEqual(m.danger(self.w(io_full_pct=8.01)),'pressure_unsafe_after_change')
    def test_post_pressure_refuses(self):self.assertEqual(m.danger(self.w(memory_full_pct=55.01)),'pressure_unsafe_after_change')
    def test_post_faults_refuses(self):self.assertEqual(m.danger(self.w(major_faults_per_s=281)),'major_faults_unsafe_after_change')
    def test_improved_four_rounds(self):self.assertTrue(m.improved(self.w(),[self.w(memory_full_pct=25,high_events_per_s=300)]*4))
    def test_improvement_3_of_4(self):self.assertTrue(m.improved(self.w(),[self.w(memory_full_pct=25,high_events_per_s=300)]*3+[self.w()]))
    def test_improvement_2_of_4_refuses(self):self.assertFalse(m.improved(self.w(),[self.w(memory_full_pct=25,high_events_per_s=300)]*2+[self.w()]*2))
    def test_improvement_only_events_refuses(self):self.assertFalse(m.improved(self.w(),[self.w(high_events_per_s=300)]*4))
    def test_improvement_only_pressure_refuses(self):self.assertFalse(m.improved(self.w(),[self.w(memory_full_pct=25)]*4))
    def test_improvement_unsafe_refuses(self):self.assertFalse(m.improved(self.w(),[self.w(memory_full_pct=25,high_events_per_s=300,oom_kill=1)]*4))
    def test_units_do_not_reference_protected_restarts(self):
        s=m.SERVICE_TEXT+m.TIMER_TEXT
        self.assertNotIn('restart ',s)
        self.assertNotIn('docker ',s)
        self.assertNotIn('stripchat-recorder',s)
        self.assertNotIn('systemctl set-property',s)
    def test_idempotent_unit_files_match(self):
        self.assertIn('ExecStart=/usr/bin/python3 /root/sc-vps-rescue-v12/SC_VPS_Rescue_v12.py --run',m.SERVICE_TEXT)
        self.assertIn('OnUnitInactiveSec=600s',m.TIMER_TEXT)
    def test_path_rejects_outside(self):
        self.assertFalse(m.pending_path_ok(Path('/tmp/state.json')))
        self.assertFalse(m.pending_path_ok(m.ROOT/'incorrect'/'state.json'))
        self.assertTrue(m.pending_path_ok(m.ROOT/'runs'/'test'/'state.json'))
    def test_limit_mismatch_no_mutation(self):
        with mock.patch.object(m,'limit_ok',return_value=False), mock.patch.object(m,'cmd') as cmd:
            with self.assertRaises(m.Stop):m.set_high(Path('/tmp/fake'),m.OLD,m.NEW)
            cmd.assert_not_called()
    def test_limit_change_verified(self):
        with mock.patch.object(m,'limit_ok',side_effect=[True,True]),mock.patch.object(m,'cmd') as cmd:
            m.set_high(Path('/tmp/fake'),m.OLD,m.NEW)
            self.assertIn('--runtime',cmd.call_args.args)
    def test_limit_change_fail_verified(self):
        with mock.patch.object(m,'limit_ok',side_effect=[True,False]),mock.patch.object(m,'cmd'):
            with self.assertRaises(m.Stop):m.set_high(Path('/tmp/fake'),m.OLD,m.NEW)
    def test_watchdog_path_rejects_unknown(self):
        with mock.patch.object(m.base,'require_root'):
            with self.assertRaises(m.Stop):m.watchdog(Path('/tmp/nonexistent.json'))
    def test_foreign_unit_conflict_refuses(self):
        with mock.patch.object(m.base,'require_root'),mock.patch.object(m,'pre_install_ok'),mock.patch.object(m,'SOURCE',Path(__file__)),mock.patch.object(m,'safe_read',return_value=b'foreign'):
            with self.assertRaises(m.Stop):m.install()
    def test_autonomous_monitor_does_not_change_on_low_reserve(self):
        # Guarded baseline eligibility must not leak to a runtime write.
        self.assertEqual(m.eligible(self.w(available_mib=200)),'insufficient_host_reserve')
    def test_accepted_policy_requires_same_cgroup(self):
        with mock.patch.object(m,'identities',return_value=(Path('/sys/fs/cgroup/system.slice/x'), '123',{'stripchat-recorder':'a','stripchat-gateway':'b'})),mock.patch.object(m,'limit_ok',return_value=True):
            self.assertTrue(m.stable(Path('/sys/fs/cgroup/system.slice/x'),'123',{'stripchat-recorder':'a','stripchat-gateway':'b'},m.OLD))
            self.assertFalse(m.stable(Path('/sys/fs/cgroup/system.slice/y'),'123',{'stripchat-recorder':'a','stripchat-gateway':'b'},m.OLD))
    def test_stale_pid_refuses(self):
        with mock.patch.object(m,'identities',return_value=(Path('/sys/fs/cgroup/system.slice/x'),'124',{'stripchat-recorder':'a','stripchat-gateway':'b'})):
            self.assertFalse(m.stable(Path('/sys/fs/cgroup/system.slice/x'),'123',{'stripchat-recorder':'a','stripchat-gateway':'b'},m.OLD))
    def test_foreign_watchdog_timer_rejected(self):
        self.assertFalse(m.cancel_watchdog('system.slice.timer'))
        self.assertFalse(m.cancel_watchdog('sc-vps-v12-rollback-../../.timer'))
    def test_cooldown_on_rollback(self):
        with mock.patch.object(m,'last_change',return_value={'status':'trial_rolled_back','utc':m.stamp()}):self.assertTrue(m.safe_cooldown())
    def test_cooldown_on_verified(self):
        with mock.patch.object(m,'last_change',return_value={'status':'runtime_verified','utc':m.stamp()}):self.assertFalse(m.safe_cooldown())
    def test_old_verified_state_is_not_lost_after_many_monitor_cycles(self):
        # Regression: the old [:30] would lose a verified trial after only five hours.
        with TemporaryDirectory() as tmp, mock.patch.object(m,'ROOT',Path(tmp)):
            runs=Path(tmp)/'runs';runs.mkdir()
            for i in range(50):
                folder=runs/(f'20261104T{i:06d}Z-1000');folder.mkdir()
                (folder/'state.json').write_text(json.dumps({'status':'monitoring_accepted'}))
            saved=runs/'20261103T235959Z-1000';saved.mkdir()
            (saved/'state.json').write_text(json.dumps({'status':'runtime_verified','browser_cgroup':'/sys/fs/cgroup/system.slice/x'}))
            self.assertEqual(m.last_change()['status'],'runtime_verified')
    def test_fresh_unit_install_without_touching_protected_service(self):
        with TemporaryDirectory() as tmp:
            d=Path(tmp)
            fake_source=d/'SC_VPS_Rescue_v12.py';fake_source.write_text('safe test')
            service=d/'test.service';timer=d/'test.timer';root=d/'state'
            def fake_cmd(*parts,**kwargs):
                if parts[0]=='systemctl' and parts[1]=='is-active':return 'active'
                return ''
            with mock.patch.object(m.base,'require_root'),mock.patch.object(m,'pre_install_ok'),mock.patch.object(m,'SOURCE',fake_source),mock.patch.object(m,'SERVICE',service),mock.patch.object(m,'TIMER',timer),mock.patch.object(m,'ROOT',root),mock.patch.object(m,'cmd',side_effect=fake_cmd) as c:
                self.assertEqual(m.install(),0)
                self.assertEqual(service.read_text(),m.SERVICE_TEXT)
                self.assertEqual(timer.read_text(),m.TIMER_TEXT)
                self.assertEqual(json.loads((root/'install.json').read_text())['status'],'autonomous_timer_installed')
                self.assertFalse(any('restart' in str(x) or 'docker' in str(x) for x in c.call_args_list))

if __name__=='__main__':unittest.main()
