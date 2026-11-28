import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError
import staging_qa_wait as w

C='a'*40; T={'expected_display_version':'v1.2.196','target_artifact_id':'JUDUN-1.2.196-X','target_build_instance_id':'1.2.196-X','expected_source_tree_sha256':'b'*64,'expected_managed_file_count':98}; P='c'*64
N={'native_qa_status':'PASS','native_qa_receipt_sha256':'d'*64,'native_qa_file_count':98}
F={'feature_qa_status':w.READY,'feature_plan_sha256':P,'feature_receipt_sha256':'e'*64}
PN={'native_qa_status':'PENDING','native_qa_receipt_sha256':'','native_qa_file_count':0}; PF={'feature_qa_status':'PENDING','feature_plan_sha256':'','feature_receipt_sha256':''}
I={'version':'v1.2.196','artifact_id':T['target_artifact_id'],'build_instance_id':T['target_build_instance_id'],'source_tree_sha256':T['expected_source_tree_sha256'],'managed_files':98,'payment_mode':'test_unlock'}
B={**I,'status':'ok','manifest_status':'ok',**N,**F}
def receipt(n=PN,f=PF,**kw):
    return {'schema':'judun.staging-request-readback.v1','result':'PASS','candidate_commit':C,'first':I,'second':I,'first_at_epoch':100,'second_at_epoch':165,'observed_seconds':65,'native_qa':n,'native_qa_first':n,'native_qa_second':n,'feature_qa':f,'feature_qa_builds':[B,B] if f==F else [],**kw}
class WaitTests(unittest.TestCase):
    def setup_call(self,reads,results=(),initial=None,plan=P,pointers=None,limit=10):
        self.t=0; self.read=Mock(side_effect=reads);self.attest=Mock(side_effect=results);self.pointer=Mock(side_effect=pointers) if pointers else Mock(return_value=C)
        def sleep(s): self.t+=s
        return w.wait(C,T,plan,initial or receipt(),pointer=self.pointer,read_build=self.read,attest=self.attest,clock=lambda:self.t,sleep=sleep,max_seconds=limit,interval=2)
    def test_pending_then_ready(self):
        r,reason=self.setup_call([{**B,**PN,**PF},B],[receipt(N,F)])
        self.assertEqual(reason,'FRESH_TWO_PASS_RECEIPT_READY');self.assertEqual(self.read.call_count,2);self.attest.assert_called_once()
    def test_already_ready_no_network(self):
        _,reason=self.setup_call([],initial=receipt(N,F));self.assertEqual(reason,'INITIAL_RECEIPT_ALREADY_READY');self.read.assert_not_called();self.attest.assert_not_called()
    def test_timeout_no_attest(self):
        with self.assertRaisesRegex(TimeoutError,'TIMEOUT_HOLD'): self.setup_call([{**B,**PN,**PF}]*10,limit=5)
        self.attest.assert_not_called()
    def test_superseded_no_read(self):
        with self.assertRaisesRegex(ValueError,'SUPERSEDED'): self.setup_call([],pointers=[C,'f'*40])
        self.read.assert_not_called()
    def test_superseded_after_attest(self):
        with self.assertRaisesRegex(ValueError,'SUPERSEDED'): self.setup_call([B],[receipt(N,F)],pointers=[C,C,'f'*40])
    def test_wrong_identity(self):
        with self.assertRaisesRegex(ValueError,'IDENTITY_DRIFT'): self.setup_call([{**B,'source_tree_sha256':'f'*64}])
        self.attest.assert_not_called()
    def test_payment_wrong(self):
        with self.assertRaisesRegex(ValueError,'IDENTITY_DRIFT'): self.setup_call([{**B,'payment_mode':'ecpay_live'}])
    def test_wrong_feature_plan_no_approval(self):
        with self.assertRaises(TimeoutError):self.setup_call([{**B,'feature_plan_sha256':'f'*64}]*10,limit=5)
        self.attest.assert_not_called()
    def test_no_feature_required(self):
        _,reason=self.setup_call([{**B,**PF}],[receipt(N)],plan=None);self.assertEqual(reason,'FRESH_TWO_PASS_RECEIPT_READY')
    def test_native_needed(self):
        with self.assertRaises(TimeoutError):self.setup_call([{**B,**PN}]*10,limit=5)
    def test_receipt_race_repoll(self):
        self.setup_call([B,B],[receipt(N),receipt(N,F)]);self.assertEqual(self.attest.call_count,2)
    def test_short_receipt(self):
        with self.assertRaisesRegex(ValueError,'READBACK_IDENTITY'): self.setup_call([],initial=receipt(N,F,observed_seconds=59))
    def test_unstable_native(self):
        with self.assertRaisesRegex(ValueError,'NATIVE_UNSTABLE'): self.setup_call([],initial=receipt(N,F,native_qa_second=PN))
    def test_unstable_feature(self):
        with self.assertRaisesRegex(ValueError,'FEATURE_UNSTABLE'): self.setup_call([],initial=receipt(N,F,feature_qa_builds=[B,{**B,'feature_receipt_sha256':'f'*64}]))
    def test_wrong_ready_literal(self):
        with self.assertRaises(TimeoutError): self.setup_call([{**B,'feature_qa_status':'PASS'}]*10,limit=5)
    def test_transport_retry(self):
        self.setup_call([URLError("temporary"),B],[receipt(N,F)]);self.attest.assert_called_once()
    def test_transport_retry_bounded(self):
        with self.assertRaises(URLError):self.setup_call([URLError("temporary")]*3)
        self.attest.assert_not_called()
    def test_auth_denial_not_retried(self):
        with self.assertRaises(HTTPError):self.setup_call([HTTPError("https://example.invalid",403,"denied",{},None)])
        self.assertEqual(self.read.call_count,1)
    def test_error_fails_closed(self):
        with self.assertRaises(OSError):self.setup_call([OSError('read failure')])
        self.attest.assert_not_called()
if __name__=='__main__':unittest.main()
