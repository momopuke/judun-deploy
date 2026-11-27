import base64,copy,json,subprocess,tempfile,unittest
from pathlib import Path
import feature_gate_policy as p
import feature_evidence as f
class Gate(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();d=Path(cls.tmp.name);cls.k=d/'k';cls.pub=d/'pub';subprocess.run(['openssl','genpkey','-algorithm','ED25519','-out',str(cls.k)],check=True,capture_output=True);subprocess.run(['openssl','pkey','-in',str(cls.k),'-pubout','-out',str(cls.pub)],check=True,capture_output=True);cls.pin=f.sha(cls.pub.read_bytes())
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def sign(self,x):
  raw=json.dumps(x,sort_keys=True).encode();msg=Path(self.tmp.name)/'msg';msg.write_bytes(raw);sig=subprocess.check_output(['openssl','pkeyutl','-sign','-inkey',str(self.k),'-rawin','-in',str(msg)]);return raw,base64.b64encode(sig)+b'\n'
 def setUp(self):
  self.target={'expected_display_version':'v1.2.195','target_artifact_id':'JUDUN-1.2.195-FIXTURE','target_build_instance_id':'1.2.195-FIXTURE','expected_source_tree_sha256':p.V195_TREE,'expected_managed_file_count':98,'candidate_acceptance_sha256':'d'*64};i=p.target_identity(self.target);self.plan={'schema':'judun.feature-qa-plan.v1','identity':i,'checks':sorted(f.CHECKS),'target_model':'gemini-fixture','max_preview_seconds':900};raw,sig=self.sign(self.plan);self.proof={'identity':i,'feature_receipt_sha256':'a'*64,'plan_sha256':f.sha(raw),'native_receipt_sha256':'c'*64,'feature_qa_status':'EVIDENCE_READY_NOT_RELEASE_APPROVAL'};b={**i,'status':'ok','manifest_status':'ok','payment_mode':'test_unlock','native_qa_status':'PASS','native_qa_receipt_sha256':'c'*64,'native_qa_file_count':98};b.update(f.summarize_live(self.proof,b));self.att={'native_qa':{k:b[k] for k in ('native_qa_status','native_qa_receipt_sha256','native_qa_file_count')},'feature_qa_builds':[b,copy.deepcopy(b)]};self.review={'schema':'judun.feature-release-review.v1','identity':i,'native_receipt_sha256':'c'*64,'feature_receipt_sha256':'a'*64,'plan_sha256':f.sha(raw),'candidate_acceptance_sha256':'d'*64,'review_checks':{k:'e'*64 for k in f.REVIEW_CHECKS},'status':'PASS'};self.paths=p.paths(self.target);self.files=dict(zip(self.paths,[raw,sig,*self.sign(self.review)]))
 def verify(self):return p.verify(self.target,lambda path,limit:self.files[path],self.pub.read_bytes(),self.att,pin=self.pin)
 def test_positive_fixture(self):self.assertEqual(self.verify(),'a'*64)
 def test_required_missing_plan(self):self.assertTrue(p.required(self.target,lambda x:False));del self.files[self.paths[0]];self.assertRaises(KeyError,self.verify)
 def test_required_missing_review(self):del self.files[self.paths[2]];self.assertRaises(KeyError,self.verify)
 def test_missing_oidc(self):del self.att['feature_qa_builds'];self.assertRaises(ValueError,self.verify)
 def test_native_drift(self):self.att['feature_qa_builds'][1]['native_qa_receipt_sha256']='f'*64;self.assertRaises(ValueError,self.verify)
 def test_feature_drift(self):self.att['feature_qa_builds'][1]['feature_receipt_sha256']='f'*64;self.assertRaises(ValueError,self.verify)
 def test_unsigned_plan(self):self.files[self.paths[0]]+=b' ';self.assertRaises(ValueError,self.verify)
 def test_partial_plan(self):self.plan['checks']=['vendor_markup'];self.files.update(zip(self.paths[:2],self.sign(self.plan)));self.assertRaises(ValueError,self.verify)
 def test_wrong_approval(self):self.review['candidate_acceptance_sha256']='f'*64;self.files.update(zip(self.paths[2:],self.sign(self.review)));self.assertRaises(ValueError,self.verify)
 def test_other_version_scope(self):t={**self.target,'expected_display_version':'v1.2.196','target_artifact_id':'JUDUN-1.2.196-FIXTURE','target_build_instance_id':'1.2.196-FIXTURE','expected_source_tree_sha256':'f'*64};self.assertFalse(p.required(t,lambda x:False));self.assertTrue(p.required(t,lambda x:x==p.paths(t)[0]))
if __name__=='__main__':unittest.main(verbosity=2)
