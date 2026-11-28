import contextlib, io, stat, unittest
from types import SimpleNamespace
from unittest.mock import Mock
import native_qa_preflight_service as s

class ServiceTest(unittest.TestCase):
    def fixture(self,result):
        state=Mock()
        state.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFDIR|0o700,st_uid=0)
        a={'STATE':state,'STAGE':'stage','PULL':'pull','RECEIPTS':'receipts','once':Mock(return_value=result)}
        return a
    def test_pass_canonical_delegation(self):
        a=self.fixture({'status':'PASS','receipt_sha256':'a'*64});invoke=Mock()
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(s.execute(a,invoke),0)
        a['once'].assert_called_once_with('stage','pull',a['STATE'],'receipts',invoke)
    def test_hold_no_replay(self):
        a=self.fixture({'status':'HOLD'});invoke=Mock()
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(s.execute(a,invoke),2)
        a['once'].assert_called_once()
    def test_already_attempted_no_replay(self):
        a=self.fixture({'status':'ALREADY_ATTEMPTED','previous':'PASS'});invoke=Mock()
        with contextlib.redirect_stdout(io.StringIO()): self.assertEqual(s.execute(a,invoke),0)
        a['once'].assert_called_once();invoke.assert_not_called()
    def test_untrusted_state_rejected(self):
        a=self.fixture({'status':'PASS'});a['STATE'].lstat.return_value.st_mode=stat.S_IFDIR|0o755
        with self.assertRaisesRegex(ValueError,'STATE_UNSAFE'): s.execute(a,Mock())
        a['once'].assert_not_called()
if __name__=='__main__': unittest.main()
