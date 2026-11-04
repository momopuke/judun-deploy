import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('v14',HERE/'SC_VPS_Rescue_v14.py')
a=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(a)
class Safety(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.bases=[]
        for n in range(8,13):
            p=self.root/f'v{n}'/'runs';p.mkdir(parents=True);self.bases.append(p)
        self.now=time.time()
    def mk(self,n=8,status='diagnosis_only',days=9,changes=None,extras=False,utc=True):
        p=self.bases[n-8]/('20261001-'+str(sum(1 for _ in self.bases[n-8].iterdir())))
        p.mkdir()
        s={'status':status,'changes':changes}
        if utc:s['utc']=__import__('datetime').datetime.fromtimestamp(self.now-days*86400,__import__('datetime').timezone.utc).isoformat()
        f=p/'state.json';f.write_text(json.dumps(s))
        os.utime(f,(self.now-days*86400,self.now-days*86400))
        if extras:(p/'secrets').write_text('keep')
        return p
    def runit(self,delete=True):
        with patch.object(a,'KEEP',0):return a.prune(now=self.now,roots=self.bases,unlink=delete)
    def test_expired_diagnosis_removed(self):
        p=self.mk();r=self.runit();self.assertFalse(p.exists());self.assertEqual(r['removed'],1)
    def test_recent_diagnosis_kept(self):
        p=self.mk(days=6);self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_verified_trial_kept(self):
        p=self.mk(n=12,status='runtime_verified');self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_watchdog_pending_kept(self):
        p=self.mk(n=12,status='trial_running');self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_changes_kept(self):
        p=self.mk(changes=['memory_high_changed']);self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_extra_file_kept(self):
        p=self.mk(extras=True);self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_missing_utc_kept(self):
        p=self.mk(utc=False);self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_young_mtime_kept(self):
        p=self.mk();os.utime(p/'state.json',None);self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_dry_run_kept(self):
        p=self.mk();self.assertEqual(self.runit(delete=False)['removed'],1);self.assertTrue(p.exists())
    def test_symlinked_file_kept(self):
        p=self.mk();f=p/'state.json';f.unlink();f.symlink_to(self.root/'elsewhere');self.assertEqual(self.runit()['removed'],0)
    def test_symlinked_dir_kept(self):
        p=self.mk();(self.bases[0]/'fake').symlink_to(p,target_is_directory=True);self.assertEqual(self.runit()['removed'],1);self.assertTrue((self.bases[0]/'fake').is_symlink())
    def test_keep_20_latest(self):
        for i in range(25):self.mk(days=10+i)
        self.assertEqual(a.prune(now=self.now,roots=self.bases)['removed'],5)
    def test_v12_monitoring_accepted_removed(self):
        p=self.mk(n=12,status='monitoring_accepted');self.assertEqual(self.runit()['removed'],1)
    def test_v12_regression_rolled_back_kept(self):
        p=self.mk(n=12,status='regression_rolled_back');self.assertEqual(self.runit()['removed'],0);self.assertTrue(p.exists())
    def test_no_video_dir_in_roots(self):
        self.assertTrue(all('videos' not in str(x) and 'docker' not in str(x) for x in a.RUNS))
    def test_service_scoped(self):
        self.assertIn('sc-vps-diagnostics-retention',str(a.SERVICE));self.assertIn('CPUQuota=15%',a.SERVICE_TEXT)
    def test_bounded(self):
        self.assertEqual(a.MAX_REMOVALS,200);self.assertEqual(a.KEEP,20)
if __name__=='__main__':unittest.main()
