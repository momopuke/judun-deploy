import base64,json,os,tempfile,unittest,zlib
from pathlib import Path
from unittest.mock import patch
import SC_VPS_Rescue_v17 as m

class Contracts(unittest.TestCase):
    def test_rate_rejects_reset_missing_and_zero_time(self):
        self.assertIsNone(m.rate({'x':10},{'x':9},'x',1))
        self.assertIsNone(m.rate({}, {'x':9},'x',1))
        self.assertIsNone(m.rate({'x':1},{'x':9},'x',0))
        self.assertEqual(m.rate({'x':1},{'x':9},'x',2),4)

    def test_pressure_missing_and_both_kinds(self):
        with patch.object(m,'read',return_value=None):self.assertEqual(m.pressure(Path('x')),[None,None])
        with patch.object(m,'read',return_value='some avg10=4.30 avg60=1\nfull avg10=2.10\n'):
            self.assertEqual(m.pressure(Path('x')),[4.3,2.1])

    def test_symlink_refused_for_reads(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'real').write_text('private');(p/'link').symlink_to(p/'real')
            self.assertIsNone(m.read(p/'link'))

    def test_fields_skip_invalid_data(self):
        with patch.object(m,'read',return_value='nr_throttled 23\nusage_usec invalid\nwrong 4 5\n'):
            self.assertEqual(m.fields(Path('x')),{'nr_throttled':23})

    def test_detail_is_read_only_and_quota_not_assumed(self):
        with tempfile.TemporaryDirectory() as t,patch.object(m,'CG',Path(t)):
            p=Path(t);(p/'cpu.max').write_text('20000 100000\n')
            (p/'memory.max').write_text('805306368')
            d=m.detail({'nr_throttled':0},{'nr_throttled':5},1)
            self.assertEqual(d['q'],[20000,100000]);self.assertEqual(d['th'],5)
            self.assertEqual((p/'cpu.max').read_text(),'20000 100000\n')

    def test_payload_bound_realistic_large_base(self):
        d={'v':17,'k':'base','ts':1793841995,'seq':11,'ag':'applied','cpu':99.99,'mf':99.99,'io':99.99,
           'av':2048,'sf':4096,'mh':546,'mc':600,'hi':99999.9,'om':0,'ld':99.99,'fd':50000,
           'pr':[True,True],'timer14':True,'cl':{'n':200,'b':999999999,'err':0,'at':'2026-11-05T10:20:33'},
           'pc':[['chromium',20.5],['python',15.5],['ffmpeg',13.4],['node',10.1],['other',3.2],['systemd',2.1]],
           'bp':20.0,'use':99.9,'fwd':{'active':True,'r':999999,'x':251},'wd':{'active':True,'r':5,'x':0}}
        self.assertLessEqual(len(zlib.compress(json.dumps(d,sort_keys=True,separators=(',',':')).encode(),9)),430)

    def test_public_encryption_is_exact_rsa_packet(self):
        old=m.v15.PUBLIC_KEY
        try:
            m.v15.PUBLIC_KEY=m.PUBLIC_KEY
            self.assertEqual(len(base64.b64decode(m.v15.encrypt({'v':17,'k':'test','ts':1}))),512)
        finally:m.v15.PUBLIC_KEY=old

    def test_packets_keep_same_timestamp_and_new_version(self):
        with patch.object(m.v16,'diagnose',return_value={'v':16,'ts':1,'seq':11}),patch.object(m,'detail',return_value={}):
            a,b=m.packets();self.assertEqual((a['v'],b['v'],a['ts'],b['ts']),(17,17,1,1))

    def test_nonroot_cannot_install_or_report(self):
        with patch.object(m.os,'geteuid',return_value=1000),patch.object(m.v15,'cmd') as cmd:
            for f in (m.install,m.report,m.rollback):
                with self.assertRaises(m.v15.Refused):f()
            cmd.assert_not_called()

    def test_no_source_cannot_install(self):
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'SOURCE',Path('/nonexistent')),patch.object(m.v15,'cmd') as cmd:
            with self.assertRaises(m.v15.Refused):m.install()
            cmd.assert_not_called()

    def test_foreign_unit_blocks_install(self):
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'SOURCE',Path(__file__)),patch.object(m.v15,'read_unit',return_value=b'foreign'),patch.object(m.v15,'cmd') as cmd:
            with self.assertRaises(m.v15.Refused):m.install()
            cmd.assert_not_called()

    def test_foreign_unit_blocks_rollback(self):
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m.v15,'read_unit',return_value=b'foreign'),patch.object(m.v15,'cmd') as cmd:
            with self.assertRaises(m.v15.Refused):m.rollback()
            cmd.assert_not_called()

    def test_timer_bounded_ten_minutes(self):
        self.assertIn('OnUnitInactiveSec=600s',m.TIMER_TEXT)
        self.assertIn('CPUQuota=15%',m.SERVICE_TEXT)
        self.assertIn('MemoryMax=110M',m.SERVICE_TEXT)

    def test_two_packets_are_sent_and_failure_propagates(self):
        with patch.object(m.v15,'encrypt',side_effect=lambda d:bytes([d['v']])),patch.object(m.v15,'send') as send:
            m.send_packets([{'v':17},{'v':18}]);self.assertEqual(send.call_count,2)
        with patch.object(m.v15,'encrypt',side_effect=m.v15.Refused('size')):
            with self.assertRaises(m.v15.Refused):m.send_packets([{}])

if __name__=='__main__':unittest.main()
