import contextlib, io, pathlib, subprocess, sys, unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError, URLError
import stage_native_qa_launcher_preflight_v2 as m

class Stop(Exception): pass

class RetryTest(unittest.TestCase):
    def test_transient_then_pass(self):
        for exc in (TimeoutError(), ConnectionRefusedError(), ConnectionResetError(), subprocess.TimeoutExpired('x',1), URLError(TimeoutError()), HTTPError('https://example.invalid',503,'',{},None), Stop('STOP_STAGE_PID_CHANGED'), Stop('STOP_HTTP_503_GET_health')):
            with self.subTest(exc=exc):
                fn=Mock(side_effect=[exc,'ok']); pause=Mock()
                self.assertEqual(m.preflight_retry(fn,pause),'ok'); self.assertEqual(fn.call_count,2); pause.assert_called_once_with(8)
    def test_no_retry_security(self):
        for exc in (ValueError('SIGNATURE_INVALID'),ValueError('POINTER_CHANGED'),Stop('STOP_WRONG_PAYMENT_MODE'),Stop('STOP_STAGE_IDENTITY_DRIFT'),Stop('STOP_STAGE_DEEP_OR_READY'),Stop('STOP_STAGE_SESSION_INVALID'),PermissionError(),HTTPError('https://example.invalid',403,'',{},None),URLError(PermissionError())):
            with self.subTest(exc=exc):
                fn=Mock(side_effect=exc); pause=Mock()
                with self.assertRaises(type(exc)): m.preflight_retry(fn,pause)
                fn.assert_called_once(); pause.assert_not_called()
    def test_retry_bounded(self):
        f=Mock(side_effect=TimeoutError()); pause=Mock()
        with self.assertRaises(TimeoutError): m.preflight_retry(f,pause)
        self.assertEqual(f.call_count,2);pause.assert_called_once()
    def main_case(self,prep,run_rc=2,pointer='a'*40,argv=('--run',)):
        ident={'version':'1.2.197','artifact_id':'JUDUN-1.2.197-X','build_instance_id':'1.2.197-X','source_tree_sha256':'b'*64,'count':98}
        p=Mock(side_effect=prep or [(ident,pathlib.Path('native.py'),True,False,'')])
        run=Mock(return_value=Mock(returncode=run_rc))
        with patch.object(sys,'argv',['launcher',*argv]),patch.object(m.os,'geteuid',return_value=0),patch.object(m.os,'umask'),patch.object(m,'fetch',return_value=b'{"candidate_commit":"'+pointer.encode()+b'"}'),patch.object(m,'prepare',p),patch.object(m,'preflight_retry',side_effect=lambda f:m.__dict__['_orig_retry'](f,lambda _:None)),patch.object(m.subprocess,'run',run),contextlib.redirect_stdout(io.StringIO()):
            rc=m.main()
        return rc,p,run
    def test_native_failure_no_replay(self):
        rc,p,r=self.main_case(None,2);self.assertEqual(rc,2);p.assert_called_once();r.assert_called_once()
    def test_existing_receipt_no_run(self):
        ident={'version':'1.2.197','artifact_id':'JUDUN-1.2.197-X','build_instance_id':'1.2.197-X','source_tree_sha256':'b'*64,'count':98}
        rc,p,r=self.main_case([(ident,pathlib.Path('native.py'),True,True,'c'*64)])
        self.assertEqual(rc,0);r.assert_not_called()
    def test_probe_no_business(self):
        rc,p,r=self.main_case(None,argv=());self.assertEqual(rc,0);r.assert_not_called()
    def test_preflight_retry_then_one_native(self):
        ident={'version':'1.2.197','artifact_id':'JUDUN-1.2.197-X','build_instance_id':'1.2.197-X','source_tree_sha256':'b'*64,'count':98}
        rc,p,r=self.main_case([Stop('STOP_STAGE_PID_CHANGED'),(ident,pathlib.Path('native.py'),True,False,'')],0)
        self.assertEqual(rc,0);self.assertEqual(p.call_count,2);r.assert_called_once()
m._orig_retry=m.preflight_retry
if __name__=='__main__': unittest.main()
