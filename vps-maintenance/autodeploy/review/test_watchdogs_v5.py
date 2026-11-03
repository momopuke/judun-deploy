import importlib.util, pathlib, subprocess, tempfile, unittest
from unittest.mock import patch

src=pathlib.Path(__file__).with_name('reconcile_v5.py')
spec=importlib.util.spec_from_file_location('rv5_watchdogs',src)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def proc(code=0,out=''):
    return subprocess.CompletedProcess(args=[],returncode=code,stdout=out,stderr='')

class WatchdogGuards(unittest.TestCase):
    def mock_subprocess(self,first,second):
        return patch.object(m.subprocess,'run',side_effect=[first,second])
    def test_systemd_unavailable_blocks(self):
        with patch.object(m.subprocess,'run',return_value=proc(code=1)):
            self.assertFalse(m.rollback_watchdogs_clear())
    def test_systemd_unit_files_unavailable_blocks(self):
        with patch.object(m.subprocess,'run',side_effect=[proc(),proc(code=2)]):
            self.assertFalse(m.rollback_watchdogs_clear())
    def test_pending_active_rollback_timer_blocks(self):
        with self.mock_subprocess(proc(out='sc-vps-v10-rollback-123.timer active'),proc()):
            with patch.object(m,'systemd_state',return_value='active'):
                self.assertFalse(m.rollback_watchdogs_clear())
    def test_inactive_timer_allowed(self):
        with self.mock_subprocess(proc(out='sc-vps-v10-rollback-123.timer inactive'),proc()):
            with patch.object(m,'systemd_state',return_value='inactive'):
                with patch.object(m.pathlib.Path,'iterdir',return_value=iter([])):
                    self.assertTrue(m.rollback_watchdogs_clear())
    def test_transient_unit_list_pending_blocks(self):
        with self.mock_subprocess(proc(),proc(out='sc-vps-v10-rollback-999.timer enabled')):
            with patch.object(m,'systemd_state',return_value='activating'):
                self.assertFalse(m.rollback_watchdogs_clear())
    def test_live_watchdog_proc_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);p=root/'123';p.mkdir();(p/'cmdline').write_bytes(b'/usr/bin/python3\0/path/SC_VPS_Rescue_v10.py\0--watchdog\0x')
            with self.mock_subprocess(proc(),proc()):
                with patch.object(m.pathlib.Path,'iterdir',return_value=iter([p])):
                    self.assertFalse(m.rollback_watchdogs_clear())
    def test_unknown_process_does_not_block(self):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td);p=root/'123';p.mkdir();(p/'cmdline').write_bytes(b'python3\0--check')
            with self.mock_subprocess(proc(),proc()):
                with patch.object(m.pathlib.Path,'iterdir',return_value=iter([p])):
                    self.assertTrue(m.rollback_watchdogs_clear())

if __name__=='__main__':unittest.main()
