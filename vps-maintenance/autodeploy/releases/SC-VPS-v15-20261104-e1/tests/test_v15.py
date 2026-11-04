"""Offline assurance: no live operations, no host changes."""
from __future__ import annotations
import importlib.util,json,os,tempfile,unittest,zlib,base64
from pathlib import Path
from unittest import mock

source=Path(__file__).resolve().parents[1]/'SC_VPS_Rescue_v15.py'
spec=importlib.util.spec_from_file_location('sc_vps_v15_test',source)
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class V15Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name)

    def test_source_version(self): self.assertEqual(a.VERSION,'15.0.0')
    def test_no_external_writes(self):
        src=source.read_text()
        for pattern in ('docker restart','docker stop','killall','rm -rf','/root/videos'):
            self.assertNotIn(pattern,src)
    def test_systemd_low_priority(self):
        self.assertIn('CPUQuota=15%',a.SERVICE_TEXT)
        self.assertIn('MemoryMax=96M',a.SERVICE_TEXT)
        self.assertIn('Nice=19',a.SERVICE_TEXT)
    def test_timer_600_seconds(self):self.assertIn('OnUnitInactiveSec=600s',a.TIMER_TEXT)
    def test_timer_owned(self):self.assertIn('SC-VPS-TELEMETRY-MANAGED-v15',a.TIMER_TEXT)
    def test_no_ssh_or_inbound(self):
        self.assertNotIn('ListenStream',a.SERVICE_TEXT)
        self.assertNotIn('ListenStream',a.TIMER_TEXT)
        self.assertTrue(a.UPLINK.startswith('https://ntfy.sh/'))
    def test_safe_short_rejects_unsafe(self):self.assertIsNone(a.safe_short('root pass word'))
    def test_safe_short_long(self):self.assertIsNone(a.safe_short('A'*41))
    def test_safe_short_normal(self):self.assertEqual(a.safe_short('applied'),'applied')
    def test_safe_write_json(self):
        out=self.p/'s.json';a.safe_write(out,{'x':1});self.assertEqual(a.read_json(out),{'x':1} if os.geteuid()==0 else {}) # root-only provenance
        self.assertEqual(json.loads(out.read_text()),{'x':1})
        self.assertEqual(out.stat().st_mode&0o777,0o600)
    def test_safe_write_symlink_refusal(self):
        out=self.p/'ref';out.symlink_to(self.p/'external')
        with self.assertRaises(a.Refused):a.safe_write(out,{'x':1})
    def test_read_json_no_symlink(self):
        o=self.p/'real.json';o.write_text('{"status":"applied"}')
        s=self.p/'sym';s.symlink_to(o)
        self.assertEqual(a.read_json(s),{})
    def test_read_json_caps_size(self):
        o=self.p/'large';o.write_bytes(b'a'*17000)
        self.assertEqual(a.read_json(o),{})
    def test_read_json_invalid(self):
        o=self.p/'bad';o.write_text('hello');self.assertEqual(a.read_json(o),{})
    def test_cleanup_missing(self):
        with mock.patch.object(a,'read_json',return_value={}):self.assertIsNone(a.clean_result())
    def test_cleanup_valid(self):
        d={'status':'cleanup_pass','at':'2026-11-04T15:00:00+00:00','removed':21,'freed_bytes':14567,'errors':0}
        with mock.patch.object(a,'read_json',return_value=d):
            self.assertEqual(a.clean_result(),{'n':21,'b':14567,'err':0,'at':'2026-11-04T15:00:00'})
    def test_cleanup_does_not_accept_negative(self):
        d={'status':'cleanup_pass','at':'2026-11-04','removed':-3,'freed_bytes':11,'errors':0}
        with mock.patch.object(a,'read_json',return_value=d):self.assertIsNone(a.clean_result())
    def test_cleanup_does_not_accept_wrong_status(self):
        d={'status':'failed','at':'2026-11-04','removed':2,'freed_bytes':11,'errors':0}
        with mock.patch.object(a,'read_json',return_value=d):self.assertIsNone(a.clean_result())
    def test_report_data_contains_all(self):
        browser0={'g':'x','h':4,'o':0,'mh':546,'mc':460}
        browser1={'g':'x','h':9,'o':0,'mh':546,'mc':470}
        with mock.patch.object(a,'browser',side_effect=[browser0,browser1]),\
             mock.patch.object(a.time,'sleep'),\
             mock.patch.object(a,'meminfo',return_value={'MemAvailable':455,'SwapFree':612}),\
             mock.patch.object(a,'read_json',return_value={'last_sequence':8,'status':'applied'}),\
             mock.patch.object(a,'clean_result',return_value={'n':3,'b':320,'err':0,'at':'2026-11-04'}),\
             mock.patch.object(a,'psi',side_effect=[99.4,40.1,5.7]),\
             mock.patch.object(a,'cmd',return_value='active'),\
             mock.patch.object(a,'protected',return_value=[True,True]):
            d=a.report_data(delay=0)
        for key in ('cl','pr','seq','cpu','mf','io','mh','hi','om','av','sf','fd','timer14'):
            self.assertIn(key,d)
        self.assertEqual(d['seq'],8);self.assertEqual(d['cl']['n'],3)
        self.assertEqual(d['pr'],[True,True])
        self.assertEqual(d['v'],15)
        self.assertTrue(isinstance(d['hi'],float))
    def test_report_data_invalid_sample(self):
        b={'g':'x','h':100,'o':0,'mh':546,'mc':460};c={**b,'h':98}
        with mock.patch.object(a,'browser',side_effect=[b,c]),mock.patch.object(a.time,'sleep'),\
             mock.patch.object(a,'meminfo',return_value={}),mock.patch.object(a,'read_json',return_value={}),\
             mock.patch.object(a,'clean_result',return_value=None),mock.patch.object(a,'psi',return_value=None),\
             mock.patch.object(a,'cmd',return_value='active'),mock.patch.object(a,'protected',return_value=[True,False]):
            d=a.report_data(delay=0)
        self.assertIsNone(d['hi']);self.assertIsNone(d['om'])
        self.assertEqual(d['pr'],[True,False]);self.assertIsNone(d['cl'])
    def test_encryption_is_512_bytes(self):
        enc=a.encrypt({'v':15,'ts':1760000000,'cl':{'n':4,'b':12000},'cpu':99})
        self.assertEqual(len(enc),684);self.assertEqual(len(base64.b64decode(enc)),512)
        self.assertNotIn(b'"cpu"',enc)
    def test_encryption_oversize(self):
        import secrets
        data={'value':base64.b64encode(secrets.token_bytes(500)).decode()}
        with self.assertRaises(a.Refused):a.encrypt(data)
    def test_no_unit_override(self):
        p=self.p/'unit';p.write_bytes(b'foreign service')
        self.assertNotEqual(a.read_unit(p),a.SERVICE_TEXT.encode())
    def test_unit_symlink_refusal(self):
        p=self.p/'link';p.symlink_to(self.p/'missing')
        with self.assertRaises(a.Refused):a.read_unit(p)
    def test_command_nonzero_refuses(self):
        fake=mock.Mock(returncode=3,stdout='',stderr='failed')
        with mock.patch.object(a.subprocess,'run',return_value=fake):
            with self.assertRaises(a.Refused):a.cmd('systemctl','show')
    def test_cmd_only_safe_error(self):
        with mock.patch.object(a.subprocess,'run',side_effect=OSError('secret')):
            with self.assertRaisesRegex(a.Refused,'command_error'):a.cmd('systemctl','show')
    def test_install_root_gate(self):
        with mock.patch.object(a.os,'geteuid',return_value=1000):
            with self.assertRaisesRegex(a.Refused,'root_required'):a.install()
    def test_report_root_gate(self):
        with mock.patch.object(a.os,'geteuid',return_value=1000):
            with self.assertRaisesRegex(a.Refused,'root_required'):a.report()
    def test_rollback_root_gate(self):
        with mock.patch.object(a.os,'geteuid',return_value=1000):
            with self.assertRaisesRegex(a.Refused,'root_required'):a.rollback()
    def test_report_source_no_keys_or_credentials(self):
        data={'v':15,'ts':1760000000,'ag':'applied','cl':{'n':2,'b':2100,'err':0}}
        compressed=zlib.compress(json.dumps(data).encode())
        self.assertNotIn(b'password',compressed)
        self.assertNotIn(b'USERNAME',compressed)

if __name__=='__main__':unittest.main()
