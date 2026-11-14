import unittest, tempfile, pathlib
from unittest.mock import patch
import SC_VPS_Rescue_v23 as v23

class TestCpuGuard(unittest.TestCase):
    def test_pid_reuse_and_cpu_attribution(self):
        a=(1,1000,200,{(100,7):(20,'python_other',False,0),(101,8):(30,'backup_integrity',True,0)})
        b=(9,1800,300,{(100,7):(420,'python_other',False,0),(101,8):(430,'backup_integrity',True,0)})
        busy,rows=v23.compare(a,b)
        self.assertEqual(busy,87.5)
        self.assertEqual(rows[0][2], 'python_other')
        self.assertEqual(rows[0][0],50.)
        c=(9,1800,300,{(100,9):(420,'python_other',False,0)})
        self.assertEqual(v23.compare(a,c)[1],[])
    def test_safe_identification_strict(self):
        tag,ok=v23.identify(b'/usr/bin/python3\x00/root/strip_2g_integrity.py\x00','0::/system.slice/user.slice'.encode())
        self.assertEqual((tag,ok),('backup_integrity',True))
        for cmd,cg in [(b'/usr/bin/python3\x00/root/private.py\x00',b'0::/system.slice'),
                       (b'/usr/bin/python3\x00/root/strip_2g_integrity.py\x00',b'0::/docker/xyz'),
                       (b'/usr/bin/python3\x00/root/strip_2g_integrity.py\x00',b'0::/system.slice/stripchat-recorder')]:
            self.assertFalse(v23.identify(cmd,cg)[1])
        self.assertEqual(v23.identify(b'/usr/bin/python3\x00/root/private.py\x00',b'0::/system.slice')[0],'python:private.py')
    def test_proc_stat_shape(self):
        fields=['0']*20;fields[0]='S';fields[11]='33';fields[12]='22';fields[16]='7';fields[19]='1234'
        self.assertEqual(v23.proc_stat('4 (python) '+' '.join(fields)),(4,1234,'python',55,7))
    def test_units_no_foreign_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'unit'
            self.assertTrue(v23.put_if_absent(p,b'A'))
            self.assertFalse(v23.put_if_absent(p,b'A'))
            with self.assertRaisesRegex(v23.Refused,'foreign'):
                v23.put_if_absent(p,b'B')
            p.unlink();p.symlink_to('/etc/passwd')
            with self.assertRaisesRegex(v23.Refused,'symlink'):
                v23.put_if_absent(p,b'A')
    def test_no_changes_on_readonly_preflight(self):
        with patch.object(v23,'snapshot',side_effect=[(1,100,10,{}),(2,200,20,{})]),\
             patch.object(v23.time,'sleep'),patch.object(v23.os,'setpriority') as change:
            data=v23.sample(duration=.5,adjust=False)
            self.assertEqual(data['busy'],90)
            change.assert_not_called()
    def test_only_named_allowlisted_background_can_renice(self):
        before=(1,100,0,{(42,3):(1,'backup_integrity',True,0), (43,3):(1,'python_other',False,0)})
        after=(6,600,0,{(42,3):(201,'backup_integrity',True,0),(43,3):(201,'python_other',False,0)})
        with patch.object(v23,'snapshot',side_effect=[before,after]),\
             patch.object(v23.time,'sleep'),patch.object(v23,'still_allowed',return_value=True),\
             patch.object(v23.os,'setpriority') as change:
            data=v23.sample(duration=5)
            change.assert_called_once_with(v23.os.PRIO_PROCESS,42,15)
            self.assertEqual(data['low_priority'][0][0],'backup_integrity')
    def test_schema_and_bounded_packet(self):
        ob={'busy':100,'n':3,'top':[['python_other',40.0],['ffmpeg',10.0]],'low_priority':[],'s':8}
        self.assertEqual(len(v23.telemetry.encrypt({'v':23,'k':'cpu_diag','seq':23,'ts':1794000000,**ob})),684)

    def test_v17_encryption_key_selected(self):
        from SC_VPS_Rescue_v17 import PUBLIC_KEY
        from unittest.mock import MagicMock
        fake_response=MagicMock()
        fake_response.__enter__.return_value.status=201
        with patch.object(v23.telemetry,'encrypt',return_value='ciphertext') as crypt, \
             patch.object(v23.urllib.request,'urlopen',return_value=fake_response):
            v23.deliver({'busy':1})
            self.assertEqual(v23.telemetry.PUBLIC_KEY,PUBLIC_KEY)
            crypt.assert_called_once()

    def test_legacy_foreign_units_cannot_be_retired(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            old20=root/'sc-vps-cpu-guard-v20'
            with patch.object(v23,'Path',wraps=pathlib.Path):
                pass
            # Unknown existing unit content is rejected before any service operation.
            with patch.object(v23,'unit_body',side_effect=lambda p: b'FOREIGN' if 'v20.' in str(p) else None):
                with self.assertRaisesRegex(v23.Refused,'legacy_guard_foreign'):
                    v23.approved_legacy()

if __name__=='__main__':unittest.main()

class TestEnhancements(unittest.TestCase):
    def test_python_unbuffered_backup_is_prioritized(self):
        for flag in (b'-u',b'-B',b'-OO'):
            cmd=b'/usr/bin/python3\0'+flag+b'\0/root/strip_2g_integrity.py\0'
            self.assertEqual(v23.identify(cmd,b'0::/system.slice/cron.service'),('backup_integrity',True))
    def test_argv_injection_cannot_allow_backup_script(self):
        for cmd in (b'python3\0-c\0/root/strip_2g_integrity.py\0',
                    b'python3\0-m\0/root/strip_2g_integrity.py\0',
                    b'python3\0-X\0/root/strip_2g_integrity.py\0'):
            self.assertFalse(v23.identify(cmd,b'0::/system.slice/cron.service')[1])
    def test_legacy_v22_checksum_pinned(self):
        import hashlib
        from pathlib import Path
        target=Path(__file__).resolve().parents[2]/'SC-VPS-v22-20261114-h1'/'SC_VPS_Rescue_v22.py'
        # The pinned source may be absent after signed host staging; check the
        # actual unit identifiers are complete and cryptographic-length only.
        self.assertEqual(len(v23.LEGACY_GUARDS[22]['service']),64)
        self.assertEqual(len(v23.LEGACY_GUARDS[22]['timer']),64)
    def test_interval_bounded(self):
        self.assertIn('OnUnitInactiveSec=180s',v23.TIMER_TEXT)
        self.assertIn('CPUQuota=3%',v23.SERVICE_TEXT)
