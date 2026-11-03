import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path=Path(__file__).with_name("vps_rescue_v5.py")
spec=importlib.util.spec_from_file_location("sc_vps_rescue_v5",path)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class TestV5(unittest.TestCase):
    def test_01_seconds(self): self.assertEqual(m.to_seconds("180s"),180)
    def test_02_minutes(self): self.assertEqual(m.to_seconds("3min"),180)
    def test_03_combined(self): self.assertEqual(m.to_seconds("1min 30s"),90)
    def test_04_ms(self): self.assertEqual(m.to_seconds("200ms"),.2)
    def test_05_us(self): self.assertEqual(m.to_seconds("1000000us"),1)
    def test_06_hours(self): self.assertEqual(m.to_seconds("0.5h"),1800)
    def test_07_unknown(self): self.assertIsNone(m.to_seconds("not-known"))
    def test_08_invalid(self): self.assertIsNone(m.to_seconds("1min other"))
    def test_09_infinite(self): self.assertEqual(m.to_seconds("infinity"),float("inf"))
    def test_10_empty(self): self.assertIsNone(m.to_seconds(""))
    def test_11_pinned_diag(self):
        self.assertEqual(len(m.DIAG_SHA),40)
        self.assertIn("35ad4f51ca6eb100b009441ff0c27638c014bc08",m.DIAG_URL)
    def _assess(self, **overrides):
        s=dict(LoadState="loaded",ActiveState="activating",SubState="auto-restart",
               RestartUSec="60s",NRestarts="600000",ExecMainStatus="251")
        s.update(overrides)
        with patch.object(m,"prop",side_effect=lambda unit,key:s[key]):
            return m.assess_forwarder()
    def test_12_fail_storm_eligible(self): self.assertEqual(self._assess()["status"],"ELIGIBLE")
    def test_13_already_backoff(self): self.assertEqual(self._assess(RestartUSec="3min")["status"],"ALREADY_BACKOFF")
    def test_14_running_skip(self): self.assertEqual(self._assess(ActiveState="active",SubState="running")["status"],"SKIP_NOT_CONFIRMED_STORM")
    def test_15_inactive_skip(self): self.assertEqual(self._assess(ActiveState="inactive")["status"],"SKIP_NOT_CONFIRMED_STORM")
    def test_16_first_retry_skip(self): self.assertEqual(self._assess(NRestarts="2")["status"],"SKIP_NOT_CONFIRMED_STORM")
    def test_17_exit_zero_skip(self): self.assertEqual(self._assess(ExecMainStatus="0")["status"],"SKIP_NOT_CONFIRMED_STORM")
    def test_18_unknown_counter(self): self.assertEqual(self._assess(NRestarts="nope")["status"],"SKIP_UNKNOWN_COUNTERS")
    def test_19_unknown_delay(self): self.assertEqual(self._assess(RestartUSec="nope")["status"],"SKIP_UNKNOWN_RESTART_DELAY")
    def test_20_missing_service(self): self.assertEqual(self._assess(LoadState="not-found")["status"],"SKIP_NO_FORWARDER")
    def test_21_skip_no_writes(self):
        with patch.object(m,"atomic",side_effect=AssertionError("mutation")):
            self.assertEqual(m.fix_forwarder({"status":"SKIP_NOT_CONFIRMED_STORM"})["status"],"SKIP_NOT_CONFIRMED_STORM")
    def test_22_refuse_unowned_dropin(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"unowned.conf";p.write_text("[Service]\nRestartSec=10s")
            with patch.object(m,"CONF",p):
                self.assertEqual(m.fix_forwarder({"status":"ELIGIBLE"})["status"],"BLOCKED_EXISTING_CONFIG")
    def test_23_refuse_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"link.conf";p.symlink_to(Path(t)/"unowned")
            with patch.object(m,"CONF",p):
                self.assertEqual(m.fix_forwarder({"status":"ELIGIBLE"})["status"],"BLOCKED_SYMLINK_CONFIG")
    def test_24_atomic_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"link";p.symlink_to(Path(t)/"target")
            with self.assertRaises(m.Blocked):m.atomic(p,b"test")
    def test_25_private_report(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"report.json";m.atomic(p,b'{"ok":true}')
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_26_agent_not_enrolled(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"state.json";p.write_text('{"last_seq":1,"status":"applied"}')
            with patch.object(m,"STATE",p):
                with self.assertRaises(m.Blocked):m.preflight()
    def test_27_agent_valid(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"state.json";p.write_text('{"last_seq":3,"status":"applied"}')
            with patch.object(m,"STATE",p),patch.object(m,"prop",return_value="loaded"):
                self.assertEqual(m.preflight()["last_seq"],3)
    def test_28_no_service_restart(self):
        txt=path.read_text()
        for bad in ("systemctl restart","systemctl stop","docker restart","pkill","killall","rm -rf"):
            self.assertNotIn(bad,txt)

if __name__=="__main__":
    unittest.main()
