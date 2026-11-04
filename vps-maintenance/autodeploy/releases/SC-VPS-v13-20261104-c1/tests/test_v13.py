import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('v13',ROOT/'SC_VPS_Rescue_v13.py')
v13=importlib.util.module_from_spec(spec);spec.loader.exec_module(v13)

class TestTelemetry(unittest.TestCase):
    def test_topic_allowlist(self):
        self.assertRegex(v13.UPLINK,r'^https://ntfy\.sh/scvps-rpt-[0-9a-f]{40}$')

    def test_public_key_only(self):
        self.assertIn('BEGIN PUBLIC KEY',v13.PUBLIC_KEY)
        self.assertNotIn('PRIVATE',v13.PUBLIC_KEY)

    def test_units_bounded_and_no_protected_restart(self):
        s=v13.SERVICE_TEXT+v13.TIMER_TEXT
        for forbidden in ['docker restart','docker stop','systemctl restart','systemctl stop stripchat','rm -rf','bash -c']:
            self.assertNotIn(forbidden,s)
        self.assertIn('OnUnitInactiveSec=600s',s)
        self.assertIn('NoNewPrivileges=yes',s)

    def test_encrypt_returns_encrypted_512_bytes(self):
        d={'v':13,'ts':100,'mf':35.1,'mh':546,'why':'insufficient_host_reserve'}
        ciphertext=v13.encrypt(d)
        self.assertEqual(len(ciphertext),684)
        self.assertNotIn(b'insufficient_host_reserve',ciphertext)

    def test_report_size_reject(self):
        with self.assertRaises(v13.Stop):v13.encrypt({'many':os.urandom(1000).hex()})

    def test_cgroup_normal(self):
        with mock.patch.object(v13,'command',return_value='/system.slice/stripchat-browser-desktop.service'),\
             mock.patch.object(Path,'is_dir',return_value=True),\
             mock.patch.object(Path,'is_symlink',return_value=False):
            self.assertEqual(v13.cgroup(),Path('/sys/fs/cgroup/system.slice/stripchat-browser-desktop.service'))

    def test_cgroup_unsafe_refused(self):
        with mock.patch.object(v13,'command',return_value='/system.slice/../../etc'):
            with self.assertRaises(v13.Stop):v13.cgroup()

    def test_sanitize(self):
        self.assertEqual(v13.sanitize('runtime_verified'),'runtime_verified')
        self.assertEqual(v13.sanitize('foo /root/secret'),'other')
        self.assertEqual(v13.sanitize(None),'')

    def test_plaintext_fields_no_secret(self):
        fake={'mh':546.,'mc':551.,'high':500,'pf':200,'ok':0}
        with mock.patch.object(v13,'cgroup',return_value=Path('/tmp/none')),\
             mock.patch.object(v13,'cgroup_counters',side_effect=[fake,{**fake,'high':620,'pf':224}]),\
             mock.patch.object(v13,'protected',return_value=('234',["sha|true","sha2|true"])),\
             mock.patch.object(v13,'meminfo',return_value={'MemAvailable':500,'SwapFree':550}),\
             mock.patch.object(v13,'latest_v12',return_value={'status':'diagnosis_only','reason':'insufficient_host_reserve'}),\
             mock.patch.object(v13,'json_status',return_value={'last_sequence':7,'status':'applied','operation':'apply'}),\
             mock.patch.object(v13,'psi',side_effect=[99.7,33.2]),\
             mock.patch.object(v13,'time') as tm,\
             mock.patch.object(v13.subprocess,'run') as run:
             tm.monotonic.side_effect=[1,5];tm.time.return_value=1234567
             run.return_value.stdout='active'
             d=v13.build_report(delay=0)
        self.assertTrue(d['pr']);self.assertTrue(d['tm'])
        self.assertEqual(d['hi'],30.0);self.assertEqual(d['pf'],6.0)
        self.assertEqual(d['mh'],546)
        self.assertNotIn('container_id',d);self.assertNotIn('browser_pid',d)
        self.assertNotIn('hostname',d);self.assertNotIn('credentials',d)

    def test_missing_browser_still_reports(self):
        with mock.patch.object(v13,'cgroup',side_effect=v13.Stop('missing')),\
             mock.patch.object(v13,'protected',return_value=(None,[None,None])),\
             mock.patch.object(v13,'meminfo',return_value={'MemAvailable':400,'SwapFree':300}),\
             mock.patch.object(v13,'latest_v12',return_value={}),\
             mock.patch.object(v13,'json_status',return_value={}),\
             mock.patch.object(v13,'psi',return_value=99.9),\
             mock.patch.object(v13,'time') as tm,\
             mock.patch.object(v13.subprocess,'run') as run:
            tm.monotonic.side_effect=[1,5];tm.time.return_value=100
            run.return_value.stdout='inactive'
            d=v13.build_report(delay=0)
        self.assertIsNone(d['mh']);self.assertFalse(d['pr']);self.assertFalse(d['r']);self.assertFalse(d['g'])

    def test_safe_read_reject_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'a';p.symlink_to('/etc/passwd')
            with self.assertRaises(v13.Stop):v13.safe_read(p)

    def test_state_json_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'state.json';v13.write_atomic(p,{'a':1});self.assertEqual(json.loads(p.read_text())['a'],1)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_install_refuses_foreign_unit(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'service';p.write_text('unknown')
            with mock.patch.object(v13,'SERVICE',p),mock.patch.object(v13,'TIMER',Path(td)/'timer'),\
                 mock.patch.object(v13,'SOURCE',Path(__file__).resolve()),\
                 mock.patch.object(v13.os,'geteuid',return_value=0),\
                 mock.patch.object(v13,'command') as command:
                with self.assertRaises(v13.Stop):v13.install()
                command.assert_not_called()

    def test_publish_reads_and_uploads_encrypted_only(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(v13,'ROOT',Path(td)),\
                 mock.patch.object(v13.os,'geteuid',return_value=0),\
                 mock.patch.object(v13,'build_report',return_value={'v':13,'av':420,'ts':123}),\
                 mock.patch.object(v13,'send') as send:
                self.assertEqual(v13.publish(),0)
                sent=send.call_args.args[0]
                self.assertEqual(len(sent),684)
                self.assertTrue((Path(td)/'last_report.json').exists())

    def test_no_inbound_port(self):
        s=(ROOT/'SC_VPS_Rescue_v13.py').read_text()
        for forbidden in ('.listen(','.bind(','HTTPServer(','sshpass','PRIVATE KEY','authorized_keys','/root/videos'):
            self.assertNotIn(forbidden,s)

    def test_intent_safe_report_only(self):
        self.assertIn('encrypt(data)',(ROOT/'SC_VPS_Rescue_v13.py').read_text())
        self.assertIn('send(ciphertext)',(ROOT/'SC_VPS_Rescue_v13.py').read_text())

if __name__=='__main__':unittest.main()
