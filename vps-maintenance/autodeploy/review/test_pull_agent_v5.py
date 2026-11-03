"""Safety-only offline tests for the signed SC VPS pull agent. Never run systemctl."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
AGENT=HERE/'pull_agent_v5.py'
SPEC=importlib.util.spec_from_file_location('sc_vps_candidate',AGENT)
a=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(a)
M=(ROOT/'channel.json').read_bytes()
S=(ROOT/'channel.sig.b64').read_bytes()
SOURCE=ROOT/'releases/SC-VPS-v10-20261104-a1'
SERV={'stripchat-browser-desktop.service':'active','line-openchat-guard.service':'active','stripchat-recorder':'true'}

def fetch(url,limit):
    if url.endswith('channel.json'):return M
    if url.endswith('channel.sig.b64'):return S
    name=url.split('/SC-VPS-v10-20261104-a1/',1)[1]
    return (SOURCE/name).read_bytes()

class SignedDeploy(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.home=Path(self.t.name)
        self.target=self.home/'target';self.target.mkdir()
        (self.target/'SC_VPS_Base_ReadOnly.py').write_text('original')
        self.state=self.home/'state';self.state.mkdir()
        self.backups=self.home/'backups'
        self.origverify=a.verify
        for p in [patch.object(a.os,'geteuid',return_value=0),
                  patch.object(a,'STATE',self.state),patch.object(a,'BACKUPS',self.backups),
                  patch.object(a,'target_dir',return_value=self.target),
                  patch.object(a,'get',side_effect=fetch),
                  patch.object(a,'read_protected',return_value=SERV),
                  patch.object(a,'preflight_tests')]:
            p.start();self.addCleanup(p.stop)
        patcher=patch.object(a,'verify',side_effect=lambda m,s:self.origverify(m,s,ROOT/'release-signing-public.pem'))
        patcher.start();self.addCleanup(patcher.stop)
    def state_data(self):return json.loads((self.state/'state.json').read_text())
    def enrolled(self):
        (self.state/'state.json').write_text(json.dumps({'last_sequence':1,'status':'applied','operation':'status'}))
        # Simulate a *separately signed future* release without modifying public channel.
        original=self.origverify
        def signed_followup(m,s):
            doc=original(m,s,ROOT/'release-signing-public.pem')
            return {**doc,'sequence':2,'operation':'apply'}
        self.addCleanup(patch.object(a,'verify').stop) if False else None
        p=patch.object(a,'verify',side_effect=signed_followup);p.start();self.addCleanup(p.stop)
    def test_published_manifest_is_signed_status(self):
        x=self.origverify(M,S,ROOT/'release-signing-public.pem')
        self.assertEqual(x['operation'],'status');self.assertEqual(x['sequence'],1)
    def test_tampered_signature_rejected(self):
        self.assertRaises(a.Rejected,self.origverify,M,S[:-1]+b'X',ROOT/'release-signing-public.pem')
    def test_initial_apply_denied(self):
        p=patch.object(a,'verify',return_value={**json.loads(M),'operation':'apply'})
        with p,patch.object(a,'operation') as operation:
            self.assertEqual(a.once(),5)
            operation.assert_not_called()
        self.assertFalse((self.target/'SC_VPS_Rescue_v10.py').exists())
    def test_initial_status_does_not_install_source(self):
        with patch.object(a,'operation',return_value={'exit_code':0,'output_tail':'ok','error_tail':''}) as operation:
            self.assertEqual(a.once(),0);operation.assert_called_once()
        self.assertEqual(self.state_data()['operation'],'status')
        self.assertEqual(self.state_data()['status'],'applied')
        self.assertEqual((self.target/'SC_VPS_Base_ReadOnly.py').read_text(),'original')
        self.assertFalse((self.target/'SC_VPS_Rescue_v10.py').exists())
        self.assertFalse(self.backups.exists())
    def test_status_service_drift_blocks(self):
        changed={**SERV,'line-openchat-guard.service':'inactive'}
        with patch.object(a,'read_protected',side_effect=[SERV,changed]),patch.object(a,'operation',return_value={'exit_code':0,'output_tail':'','error_tail':''}):
            self.assertEqual(a.once(),5)
        self.assertEqual(self.state_data()['status'],'needs_review')
    def test_applied_once_only_after_status(self):
        self.enrolled()
        with patch.object(a,'operation',return_value={'exit_code':0,'output_tail':'applied','error_tail':''}) as op:
            self.assertEqual(a.once(),0)
            self.assertEqual(a.once(),0)
            op.assert_called_once()
        self.assertEqual(self.state_data()['status'],'applied')
        self.assertEqual(self.state_data()['last_sequence'],2)
    def test_timeout_preserves_watchdog_source(self):
        self.enrolled()
        with patch.object(a,'operation',side_effect=a.Rejected('APPLY_TIMEOUT_WATCHDOG_MAY_BE_ACTIVE')) as op:
            self.assertEqual(a.once(),5)
            self.assertEqual(a.once(),5)
            op.assert_called_once()
        self.assertEqual(self.state_data()['status'],'in_progress')
        self.assertTrue((self.target/'SC_VPS_Rescue_v10.py').exists())
    def test_safety_refusal_restores_original(self):
        self.enrolled()
        with patch.object(a,'operation',return_value={'exit_code':3,'output_tail':'SC VPS Rescue v10 | diagnosis_only','error_tail':''}):
            self.assertEqual(a.once(),0)
        self.assertEqual(self.state_data()['status'],'safety_refused')
        self.assertEqual((self.target/'SC_VPS_Base_ReadOnly.py').read_text(),'original')
        self.assertFalse((self.target/'SC_VPS_Rescue_v10.py').exists())
    def test_tampered_payload_denied(self):
        def corrupt(url,limit):
            if url.endswith('SC_VPS_Rescue_v10.py'):return b'wrong'
            return fetch(url,limit)
        self.enrolled()
        with patch.object(a,'get',side_effect=corrupt),patch.object(a,'operation') as op:
            self.assertEqual(a.once(),5);op.assert_not_called()
    def test_protected_service_changed_invokes_rollback(self):
        self.enrolled()
        different={**SERV,'stripchat-recorder':'false'}
        with patch.object(a,'read_protected',side_effect=[SERV,different]),patch.object(a,'operation',return_value={'exit_code':0,'output_tail':'','error_tail':''}) as op:
            self.assertEqual(a.once(),5)
            self.assertEqual(op.call_count,2)
        self.assertEqual(self.state_data()['status'],'protected_service_changed')
        self.assertFalse((self.target/'SC_VPS_Rescue_v10.py').exists())
if __name__=='__main__':unittest.main()