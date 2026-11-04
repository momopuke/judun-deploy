from __future__ import annotations
import importlib.util,unittest,json,tempfile,os,sys,base64
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('v16test',ROOT/'SC_VPS_Rescue_v16.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
class TestV16(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup);self.root=Path(self.t.name)
 def test_version(self):self.assertEqual(a.VERSION,'16.0.0')
 def test_preserves_recording(self):
  source=(ROOT/'SC_VPS_Rescue_v16.py').read_text()
  for s in ('/root/videos','docker restart','docker stop','docker rm','killall','rm -rf'):self.assertNotIn(s,source)
 def test_no_username_reporting(self):
  src=(ROOT/'SC_VPS_Rescue_v16.py').read_text()
  self.assertNotIn('/proc/cmdline',src);self.assertNotIn('journalctl',src)
 def test_timer_600(self):self.assertIn('OnUnitInactiveSec=600s',a.TIMER_TEXT)
 def test_service_cpu_quota(self):self.assertIn('CPUQuota=15%',a.SERVICE_TEXT)
 def test_service_oom_cap(self):self.assertIn('MemoryMax=110M',a.SERVICE_TEXT)
 def test_no_network_listener(self):self.assertNotIn('ListenStream',a.SERVICE_TEXT)
 def test_category_chromium(self):self.assertEqual(a.category('chromium'),'chromium')
 def test_category_chrome_helper(self):self.assertEqual(a.category('chromium-gpu'),'chromium')
 def test_category_python(self):self.assertEqual(a.category('python3'),'python')
 def test_category_node(self):self.assertEqual(a.category('node'),'node')
 def test_category_ffmpeg(self):self.assertEqual(a.category('ffmpeg'),'ffmpeg')
 def test_category_rclone(self):self.assertEqual(a.category('rclone'),'rclone')
 def test_category_docker(self):self.assertEqual(a.category('dockerd'),'docker')
 def test_category_unknown_redacted(self):self.assertEqual(a.category('user_314.private'),'other')
 def test_category_no_account_leak(self):self.assertEqual(a.category('---irene'),'other')
 def test_contrib_core(self):
  d=a.contrib({'1':{'start':5,'cat':'chromium','ticks':100}},{'1':{'start':5,'cat':'chromium','ticks':150}},1,100)
  self.assertEqual(d,[['chromium',50.0]])
 def test_contrib_pid_reuse(self):
  self.assertEqual(a.contrib({'1':{'start':2,'cat':'python','ticks':300}},{'1':{'start':3,'cat':'python','ticks':440}},1,100),[])
 def test_contrib_negative_ticks(self):
  self.assertEqual(a.contrib({'1':{'start':2,'cat':'python','ticks':440}},{'1':{'start':2,'cat':'python','ticks':300}},1,100),[])
 def test_contrib_zero_interval(self):self.assertEqual(a.contrib({}, {}, 0,100),[])
 def test_contrib_top_6(self):
  old={str(i):{'start':1,'cat':str(i),'ticks':0} for i in range(10)}
  new={str(i):{'start':1,'cat':str(i),'ticks':i+1} for i in range(10)}
  self.assertEqual(len(a.contrib(old,new,1,100)),6)
 def test_contrib_deny_implausible_overspeed(self):
  self.assertEqual(a.contrib({'1':{'start':2,'cat':'python','ticks':0}},{'1':{'start':2,'cat':'python','ticks':1000}},1,100),[])
 def test_proc_stat_valid(self):
  p=self.root/'12'/'stat';p.parent.mkdir();p.write_text('12 (chromium) S '+ ' '.join(['0']*10+['150','30']+['0']*6+['400']+['0']*10))
  x=a.proc_stat(p);self.assertEqual(x,{'cat':'chromium','ticks':180,'start':400})
 def test_proc_stat_invalid(self):
  p=self.root/'1'/'stat';p.parent.mkdir();p.write_text('secret');self.assertIsNone(a.proc_stat(p))
 def test_proc_snapshot_filters_names(self):
  p=self.root/'abc';p.mkdir();(p/'stat').write_text('junk');self.assertEqual(a.proc_snapshot(self.root),{})
 def test_cpu_stat_cpu_line(self):
  p=self.root/'stat';p.write_text('cpu 10 20 30 40 50 60 70\n');self.assertEqual(a.cpu_stat(p),{'total':280,'idle':90})
 def test_cpu_stat_malformed(self):
  p=self.root/'stat';p.write_text('x 10 20\n');self.assertIsNone(a.cpu_stat(p))
 def test_browser_cpu_count(self):
  p=self.root/'cpu.stat';p.write_text('usage_usec 321000\n');self.assertEqual(a.browser_cpu(p),321000)
 def test_browser_cpu_missing(self):self.assertIsNone(a.browser_cpu(self.root/'absent'))
 def test_unit_state_unknown_refused(self):self.assertIsNone(a.unit_state('ssh.service'))
 def test_unit_state_forward_nrestarts(self):
  with mock.patch.object(a.v15,'cmd',return_value='ActiveState=activating\nNRestarts=685420\nExecMainStatus=251'):
   self.assertEqual(a.unit_state('livevpn-stripchat-forward.service'),{'active':True,'r':685420,'x':251})
 def test_unit_state_bad_number_none(self):
  with mock.patch.object(a.v15,'cmd',return_value='ActiveState=failed\nNRestarts=oops\nExecMainStatus=0'):
   self.assertEqual(a.unit_state('livevpn-stripchat-forward.service'),{'active':False,'r':None,'x':0})
 def test_unit_state_failure_none(self):
  with mock.patch.object(a.v15,'cmd',side_effect=a.v15.Refused('fail')):self.assertIsNone(a.unit_state('strip-recovery-watchdog.service'))
 def test_diagnose_merges_protected(self):
  d={'v':15,'ts':1700000,'seq':9,'pr':[True,True],'cpu':99,'mf':15.93,'cl':{'n':0,'b':0}}
  with mock.patch.object(a,'proc_snapshot',side_effect=[{},{}]),mock.patch.object(a,'cpu_stat',side_effect=[{'total':100,'idle':40},{'total':200,'idle':50}]),mock.patch.object(a,'browser_cpu',side_effect=[1000,2000]),mock.patch.object(a.v15,'report_data',return_value=d),mock.patch.object(a,'unit_state',return_value={'r':0,'x':0,'active':False}):
   r=a.diagnose()
  self.assertEqual(r['v'],16);self.assertEqual(r['seq'],9);self.assertEqual(r['pr'],[True,True]);self.assertEqual(r['use'],90)
  self.assertIn('pc',r);self.assertIn('bp',r)
 def test_diagnose_encrypt_accepts(self):
  d={'v':16,'ts':1793805555,'ag':'applied','pr':[True,True],'seq':9,'cpu':99.21,'mf':15.93,'ld':25.23,'cl':{'at':'2026-11-04','n':0,'b':0,'err':0},'pc':[['chromium',40],['python',20],['other',5]],'bp':47.2,'use':100,'fwd':{'active':False,'r':685420,'x':251}}
  self.assertEqual(len(base64.b64decode(a.v15.encrypt(d))),512)
 def test_install_requires_root(self):
  with mock.patch.object(a.os,'geteuid',return_value=1000):
   with self.assertRaises(a.v15.Refused):a.install()
 def test_report_requires_root(self):
  with mock.patch.object(a.os,'geteuid',return_value=1000):
   with self.assertRaises(a.v15.Refused):a.report()
 def test_rollback_requires_root(self):
  with mock.patch.object(a.os,'geteuid',return_value=1000):
   with self.assertRaises(a.v15.Refused):a.rollback()
if __name__=='__main__':unittest.main()
