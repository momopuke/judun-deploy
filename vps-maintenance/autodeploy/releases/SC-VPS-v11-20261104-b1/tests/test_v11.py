"""Offline safety tests for SC VPS v11; intentionally no live system writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import SC_VPS_Rescue_v11 as v11


def sample(**changes):
    x = {'seconds': 12., 'memory_full_pct': 33., 'io_full_pct': 0.,
         'high_events_per_s': 730., 'major_faults_per_s': 60., 'oom_kill': 0,
         'ram_available_mib': 495., 'swap_free_mib': 560.,
         'memory_current_mib': 554., 'memory_high_mib': 546.}
    x.update(changes)
    return x

class PolicyTests(unittest.TestCase):
    def test_version_11_and_only_64mb_increment(self):
        self.assertEqual(v11.VERSION, '11.0.0')
        self.assertEqual(v11.BASELINE_HIGH, 546 * v11.MiB)
        self.assertEqual(v11.TARGET_INCREMENT, 64 * v11.MiB)
        self.assertLessEqual(v11.BASELINE_HIGH + v11.TARGET_INCREMENT, v11.MAX_TARGET)

    def test_accept_real_four_round_baseline(self):
        w = sample(memory_full_pct=33.84, high_events_per_s=739.4,
                   major_faults_per_s=60, ram_available_mib=490)
        snapshot = {'current_bytes': 554*v11.MiB, 'high_bytes': v11.BASELINE_HIGH,
                    'max_bytes': 768*v11.MiB}
        self.assertIsNone(v11.baseline_reason(w, snapshot, v11.BASELINE_HIGH))

    def test_refuse_when_memory_not_stalled(self):
        self.assertEqual(v11.baseline_reason(sample(memory_full_pct=3),
            {'current_bytes': 554*v11.MiB, 'high_bytes': v11.BASELINE_HIGH, 'max_bytes': None},
            v11.BASELINE_HIGH), 'global_memory_pressure_not_confirmed')

    def test_refuse_no_throttling(self):
        self.assertIn('throttle', v11.baseline_reason(sample(high_events_per_s=0),
            {'current_bytes': 554*v11.MiB, 'high_bytes': v11.BASELINE_HIGH, 'max_bytes': None},
            v11.BASELINE_HIGH))

    def test_refuse_low_ram(self):
        self.assertEqual(v11.baseline_reason(sample(ram_available_mib=470),
            {'current_bytes': 554*v11.MiB, 'high_bytes': v11.BASELINE_HIGH, 'max_bytes': None},
            v11.BASELINE_HIGH), 'reserve_too_low_before_trial')

    def test_refuse_low_swap(self):
        self.assertEqual(v11.baseline_reason(sample(swap_free_mib=390),
            {'current_bytes': 554*v11.MiB, 'high_bytes': v11.BASELINE_HIGH, 'max_bytes': None},
            v11.BASELINE_HIGH), 'reserve_too_low_before_trial')

    def test_refuse_near_hard_cap(self):
        self.assertEqual(v11.baseline_reason(sample(),
            {'current_bytes': 554*v11.MiB, 'high_bytes': v11.BASELINE_HIGH,
             'max_bytes': (610+20)*v11.MiB}, v11.BASELINE_HIGH), 'memory_max_too_close')

    def test_high_post_memory_stall_is_unsafe(self):
        self.assertEqual(v11.unsafe_post(sample(memory_full_pct=56)), 'post_pressure_unsafe')

    def test_oom_is_unsafe(self):
        self.assertEqual(v11.unsafe_post(sample(oom_kill=1)), 'post_memory_reserve_or_oom')

    def test_missing_counters_are_unsafe(self):
        self.assertEqual(v11.unsafe_post(sample(major_faults_per_s=None)), 'post_sample_incomplete')

    def test_improve_requires_three_windows_each_metric(self):
        good = sample(memory_full_pct=15, high_events_per_s=12, major_faults_per_s=75)
        self.assertTrue(v11.improved(sample(), [good]*4))
        self.assertFalse(v11.improved(sample(), [good]*2 + [sample()]*2))

    def test_fault_storm_rejected(self):
        bad = sample(memory_full_pct=12, high_events_per_s=10, major_faults_per_s=400)
        self.assertFalse(v11.improved(sample(), [bad]*4))
        self.assertIsNotNone(v11.unsafe_post(bad))

    def test_watchdog_path_must_be_in_run_folder(self):
        self.assertFalse(v11.path_ok(Path('/tmp/state.json')))
        self.assertFalse(v11.path_ok(v11.ROOT/'runs/state.json'))
        self.assertTrue(v11.path_ok(v11.ROOT/'runs'/'abc'/'state.json'))

    def test_watchdog_refuses_foreign_version(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(v11, 'ROOT', Path(td)), mock.patch.object(v11.base, 'require_root'):
                p=Path(td)/'runs'/'one'/'state.json';p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'version':'12.0','status':'trial_pending'}))
                self.assertEqual(v11.watchdog(p),0)

    def test_watchdog_restores_trial_high(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(v11, 'ROOT', Path(td)), mock.patch.object(v11.base, 'require_root'), \
                 mock.patch.object(v11.v9, 'browser_group', return_value=Path('/sys/fs/cgroup/system.slice/test')), \
                 mock.patch.object(v11, 'expected_limit', return_value=True), \
                 mock.patch.object(v11, 'set_high') as change:
                p=Path(td)/'runs'/'one'/'state.json';p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'version':v11.VERSION,'status':'trial_applied',
                    'browser_cgroup':'/sys/fs/cgroup/system.slice/test',
                    'old_high':v11.BASELINE_HIGH,
                    'target_high':v11.BASELINE_HIGH+v11.TARGET_INCREMENT}))
                self.assertEqual(v11.watchdog(p), 0)
                change.assert_called_once_with(Path('/sys/fs/cgroup/system.slice/test'),
                    v11.BASELINE_HIGH+v11.TARGET_INCREMENT,v11.BASELINE_HIGH)
                self.assertEqual(json.loads(p.read_text())['status'],'watchdog_reverted')

    def test_watchdog_refuses_unknown_limit(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(v11, 'ROOT', Path(td)), mock.patch.object(v11.base, 'require_root'), \
                 mock.patch.object(v11.v9, 'browser_group', return_value=Path('/sys/fs/cgroup/system.slice/test')), \
                 mock.patch.object(v11, 'expected_limit', return_value=False), \
                 mock.patch.object(v11, 'set_high') as change:
                p=Path(td)/'runs'/'one'/'state.json';p.parent.mkdir(parents=True)
                p.write_text(json.dumps({'version':v11.VERSION,'status':'trial_running',
                    'browser_cgroup':'/sys/fs/cgroup/system.slice/test',
                    'old_high':v11.BASELINE_HIGH,
                    'target_high':v11.BASELINE_HIGH+v11.TARGET_INCREMENT}))
                with self.assertRaises(v11.SafetyError):v11.watchdog(p)
                change.assert_not_called()

class ApplySimulation(unittest.TestCase):
    def run_trial(self, post=None, baseline=None, refusal=True, stop_timer=True,
                  change_service=False):
        post = post if post is not None else [sample(memory_full_pct=12,high_events_per_s=0,major_faults_per_s=25)]*4
        baseline = baseline or sample()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            state={'high':v11.BASELINE_HIGH}
            changes=[]
            def limit(path,expected):return state['high']==expected
            def set_limit(path,old,new):
                self.assertEqual(state['high'],old)
                state['high']=new
                changes.append((old,new))
            seq=[baseline]+post
            with mock.patch.object(v11, 'ROOT', root), \
                 mock.patch.object(v11.base, 'require_root'), \
                 mock.patch.object(v11, 'v10_refusal_ok', return_value=refusal), \
                 mock.patch.object(v11.v10, 'saved_v9', return_value={'old_high':450*v11.MiB, 'target_high':v11.BASELINE_HIGH}), \
                 mock.patch.object(v11.v9, 'browser_group', return_value=Path('/sys/fs/cgroup/system.slice/test')), \
                 mock.patch.object(v11, 'get_service_identity', return_value={'pid':'123','active':'active'}), \
                 mock.patch.object(v11, 'get_container_identities', return_value={'stripchat-recorder':'id1','stripchat-gateway':'id2'}), \
                 mock.patch.object(v11, 'identities_ok', return_value=not change_service), \
                 mock.patch.object(v11, 'expected_limit', side_effect=limit), \
                 mock.patch.object(v11, 'set_high', side_effect=set_limit), \
                 mock.patch.object(v11, 'start_watchdog', return_value='sc-vps-v11-revert-123.timer') as arm, \
                 mock.patch.object(v11, 'stop_watchdog', return_value=stop_timer) as disarm, \
                 mock.patch.object(v11.base, 'run', return_value=(0,'active','')), \
                 mock.patch.object(v11.v9, 'inspect', return_value={'current_bytes': 554*v11.MiB,
                     'high_bytes':v11.BASELINE_HIGH,'max_bytes':768*v11.MiB}), \
                 mock.patch.object(v11, 'measure', side_effect=seq), \
                 mock.patch.object(v11.time, 'sleep'):
                rc=v11.apply()
            f=next(root.glob('runs/*/state.json'))
            result=json.loads(f.read_text())
            return rc,state['high'],changes,result,arm.call_count,disarm.call_count

    def test_good_trial_keeps_610mb_runtime(self):
        rc, high, changes, st, arm, disarm=self.run_trial()
        self.assertEqual(rc,0)
        self.assertEqual(high,610*v11.MiB)
        self.assertEqual(changes,[(546*v11.MiB,610*v11.MiB)])
        self.assertEqual(st['status'],'runtime_verified')
        self.assertEqual((arm,disarm),(1,1))

    def test_no_gain_rolls_back_to_546mb(self):
        rc,high,changes,st,arm,disarm=self.run_trial(post=[sample()]*4)
        self.assertEqual(rc,3)
        self.assertEqual(high,546*v11.MiB)
        self.assertEqual(st['status'],'diagnosis_only')
        self.assertEqual(len(changes),2)
        self.assertEqual((arm,disarm),(1,1))

    def test_safety_refused_no_mutation(self):
        rc,high,changes,st,arm,disarm=self.run_trial(refusal=False)
        self.assertEqual(rc,3)
        self.assertEqual(high,546*v11.MiB)
        self.assertEqual(changes,[])
        self.assertEqual(arm,0)

    def test_unhealthy_pressure_no_mutation(self):
        rc,high,changes,st,arm,disarm=self.run_trial(baseline=sample(ram_available_mib=320))
        self.assertEqual(rc,3)
        self.assertEqual(changes,[])
        self.assertEqual(arm,0)

    def test_sudden_oom_automatically_restores(self):
        rc,high,changes,st,arm,disarm=self.run_trial(post=[sample(oom_kill=1)]+[sample()]*3)
        self.assertEqual(rc,3)
        self.assertEqual(high,546*v11.MiB)
        self.assertEqual(st['status'],'diagnosis_only')
        self.assertEqual(len(changes),2)

    def test_watchdog_cancel_failure_keeps_problem_visible(self):
        rc,high,changes,st,arm,disarm=self.run_trial(stop_timer=False)
        self.assertEqual(rc,2)
        self.assertEqual(st['status'],'needs_review')
        self.assertEqual(high,546*v11.MiB)
        self.assertEqual(len(changes),2)

    def test_changed_service_refuses_before_trial(self):
        rc,high,changes,st,arm,disarm=self.run_trial(change_service=True)
        self.assertEqual(rc,3)
        self.assertEqual(changes,[])
        self.assertEqual(arm,0)

if __name__=='__main__':unittest.main()
