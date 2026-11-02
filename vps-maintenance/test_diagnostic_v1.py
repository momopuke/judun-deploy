import importlib.util
from pathlib import Path
from unittest import TestCase, main
import tempfile
import json
spec=importlib.util.spec_from_file_location('diagnostic',Path(__file__).with_name('diagnostic_v1.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class DiagnosticTests(TestCase):
    def test_cpu_delta(self):
        self.assertEqual(m.cpu_delta((100,20,5),(200,40,10)), {'busy_percent':75.0,'iowait_percent':5.0})
    def test_cpu_delta_no_progress(self): self.assertIsNone(m.cpu_delta((100,10,5),(100,10,5)))
    def test_cpu_delta_missing(self): self.assertIsNone(m.cpu_delta(None,None))
    def test_cgroup_delta(self):
        x=m.delta({'usage_usec':10,'nr_periods':10,'nr_throttled':1},{'usage_usec':30,'nr_periods':20,'nr_throttled':9})
        self.assertEqual(x['throttle_ratio'],.8)
        self.assertEqual(x['usage_usec'],20)
    def test_cgroup_missing(self): self.assertIsNone(m.delta(None,None))
    def test_cgroup_no_division_by_zero(self):
        self.assertNotIn('throttle_ratio',m.delta({'nr_periods':2,'nr_throttled':1},{'nr_periods':2,'nr_throttled':1}))
    def test_classify_high_pressure(self):
        r=m.classify(99,{'busy_percent':95},{'throttle_ratio':.8},'active',10)
        self.assertIn('HOST_CPU_CAPACITY_CONSTRAINED',r)
        self.assertIn('CHROMIUM_CGROUP_THROTTLED_DO_NOT_LOWER_CPU_LIMIT',r)
    def test_classify_high_psi_not_cpu_busy(self):
        r=m.classify(99,{'busy_percent':45},{'throttle_ratio':.9},'active',7)
        self.assertNotIn('HOST_CPU_CAPACITY_CONSTRAINED',r)
    def test_classify_io(self):
        self.assertIn('IO_WAIT_PRESSURE',m.classify(10,{'busy_percent':30},None,'active',70))
    def test_classify_browser_missing(self):
        self.assertIn('BROWSER_NOT_ACTIVE_CHECK_GUARD',m.classify(10,None,None,'inactive',0))
    def test_unverified_is_always_present(self):
        self.assertIn('LIVE_MODERATION_NOT_VERIFIED',m.classify(None,None,None,'active',None))
    def test_atomic_report(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.json'
            m.write_atomic(p,{'ok':1})
            self.assertEqual(json.loads(p.read_text()),{'ok':1})
            self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_atomic_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'report.json';real=Path(d)/'real.json';real.write_text('keep')
            p.symlink_to(real)
            with self.assertRaises(RuntimeError):m.write_atomic(p,{'bad':1})
            self.assertEqual(real.read_text(),'keep')
    def test_no_mutation_calls(self):
        src=Path(m.__file__).read_text()
        for marker in ('systemctl\',\'restart\'','systemctl\',\'stop\'','kill -9','sshpass','subprocess.Popen','eval('):
            self.assertNotIn(marker,src)
    def test_no_publication(self):
        src=Path(m.__file__).read_text()
        for marker in ('https://','Authorization','github_token','/root/videos/'):
            self.assertNotIn(marker,src)

if __name__=='__main__':main()