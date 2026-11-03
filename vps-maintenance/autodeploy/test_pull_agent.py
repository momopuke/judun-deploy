from __future__ import annotations
import base64
import importlib.util
import json
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch
P=Path(__file__).with_name('pull_agent.py')
s=importlib.util.spec_from_file_location('sc_agent', P)
a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
KEYDIR=Path(__file__).parent

def doc():
    return {'schema':'sc-vps-signed-release/v1','sequence':1,'release_id':'SC-VPS-v10-20261104-a1',
            'git_commit':'a'*40,'version':10,'operation':'apply',
            'files':{'SC_VPS_Base_ReadOnly.py':'b'*64,
                     'SC_VPS_Metrics_ReadOnly.py':'c'*64,
                     'SC_VPS_Rescue_v8.py':'d'*64,
                     'SC_VPS_Rescue_v9.py':'e'*64,
                     'SC_VPS_Rescue_v10.py':'f'*64,
                     'tests/test_v10.py':'1'*64}}

class Contract(unittest.TestCase):
    def test_valid(self):self.assertEqual(a.strict_json(json.dumps(doc()).encode())['version'],10)
    def test_unknown_field(self):
        d=doc();d['shell']='rm -rf /';self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_duplicate_field(self):self.assertRaises(a.Rejected,a.strict_json,b'{"schema":1,"schema":2}')
    def test_bad_commit(self):
        d=doc();d['git_commit']='main';self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_path_traversal(self):
        d=doc();d['files']['../../root/ssh']='f'*64;self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_operation_shell(self):
        d=doc();d['operation']='shell';self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_negative_sequence(self):
        d=doc();d['sequence']=-1;self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_boolean_sequence(self):
        d=doc();d['sequence']=True;self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_missing_file(self):
        d=doc();del d['files']['SC_VPS_Rescue_v10.py'];self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_invalid_digest(self):
        d=doc();d['files']['SC_VPS_Rescue_v10.py']='bogus';self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_file_size(self):self.assertRaises(a.Rejected,a.strict_json,b' '*9000)
    def test_unrecognized_filename(self):self.assertFalse(a.check_name('systemd/ssh.service',10))
    def test_v11_signed_file(self):self.assertTrue(a.check_name('SC_VPS_Rescue_v11.py',11))
    def test_no_future_source(self):self.assertFalse(a.check_name('SC_VPS_Rescue_v11.py',10))
    def test_no_foreign_key(self):self.assertFalse(a.check_name('.env',10))
    def test_release_version_match(self):
        d=doc();d['version']=11;self.assertRaises(a.Rejected,a.strict_json,json.dumps(d).encode())
    def test_git_data_immutable(self):
        d=doc();d['git_commit']='0'*40;self.assertEqual(a.strict_json(json.dumps(d).encode())['git_commit'],'0'*40)
    def test_write_state_reject_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);dst=base/'d';dst.write_text('keep');link=base/'l';link.symlink_to(dst)
            self.assertRaises(a.Rejected,a.save_json,link,{'x':1})
            self.assertEqual(dst.read_text(),'keep')
    def test_write_state_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json';a.save_json(p,{'x':1});self.assertEqual(json.loads(p.read_text()),{'x':1});self.assertEqual(p.stat().st_mode&0o777,0o600)
    def test_code_staged_then_rollback(self):
        d=doc();d['files']={'test.py':a.sha(b'new')}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'installed';p.mkdir();(p/'test.py').write_bytes(b'old')
            src=root/'src';src.mkdir();(src/'test.py').write_bytes(b'new')
            with patch.object(a,'target_dir',return_value=p),patch.object(a,'BACKUPS',root/'backups'):
                folder,backup,copied,existing=a.install_code(d,src,root)
                self.assertEqual((folder/'test.py').read_bytes(),b'new')
                self.assertTrue(backup.exists());self.assertEqual((backup/'test.py').read_bytes(),b'old')
                a.restore_code(folder,backup,copied,existing)
                self.assertEqual((folder/'test.py').read_bytes(),b'old')
    def test_code_new_file_rolls_back(self):
        d=doc();d['files']={'new.py':a.sha(b'new')}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'installed';p.mkdir();src=root/'src';src.mkdir();(src/'new.py').write_bytes(b'new')
            with patch.object(a,'target_dir',return_value=p),patch.object(a,'BACKUPS',root/'backups'):
                folder,backup,copied,existing=a.install_code(d,src,root)
                self.assertTrue((folder/'new.py').exists())
                a.restore_code(folder,backup,copied,existing)
                self.assertFalse((folder/'new.py').exists())
    def test_no_restart_or_disable(self):
        s=P.read_text();self.assertNotIn("'systemctl','restart'",s)
        self.assertNotIn("'docker','stop'",s)
    def test_signing_verifies_and_tamper_rejects(self):
        priv=KEYDIR/'private/sc-vps-release-signing-private.pem';pub=KEYDIR/'release-signing-public.pem'
        if not priv.exists():self.skipTest('test signing key unavailable')
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'manifest.json';f.write_bytes(json.dumps(doc()).encode())
            sig=Path(tmp)/'sig'
            p=subprocess.run(['openssl','pkeyutl','-sign','-inkey',str(priv),'-rawin','-in',str(f),'-out',str(sig)],capture_output=True)
            self.assertEqual(p.returncode,0)
            sig64=base64.b64encode(sig.read_bytes())
            self.assertEqual(a.verify(f.read_bytes(),sig64,pub)['sequence'],1)
            changed=json.loads(f.read_text());changed['sequence']=2
            self.assertRaises(a.Rejected,a.verify,json.dumps(changed).encode(),sig64,pub)

if __name__=='__main__':unittest.main()
