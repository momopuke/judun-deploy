import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SRC=Path(__file__).with_name('activate_seq2_v6.py')
spec=importlib.util.spec_from_file_location('sc_vps_seq2_v6',SRC)
a=importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

def receipt(seq=1,op='apply',status='safety_refused',rc=3,restored=True,**extra):
    d={
      'last_sequence':seq,'release_id':a.RELEASE,'operation':op,'status':status,
      'code_restored':restored,
      'result':{'exit_code':rc,'output_tail':'not trusted for memory acceptance'},
      'protected_before':{'stripchat-browser-desktop.service':'active',
                          'stripchat-recorder':'true','line-openchat-guard.service':'active'},
      'protected_after':{'stripchat-browser-desktop.service':'active',
                          'stripchat-recorder':'true','line-openchat-guard.service':'active'},
    }
    d.update(extra)
    return json.dumps(d).encode()

class ReceiptTests(unittest.TestCase):
    def test_refused_expected(self):self.assertEqual(a.parse_receipt(receipt()),'LEGACY_SEQ1_REFUSED_UNVERIFIED_MEMORY')
    def test_old_status_expected(self):self.assertEqual(a.parse_receipt(receipt(2,'status','applied',0,False)),'LEGACY_SEQ2_STATUS_APPLIED')
    def test_new_status_expected(self):
        x=json.loads(receipt(2,'status','applied',0));x.pop('code_restored');x['code_installed']=False
        self.assertEqual(a.parse_receipt(json.dumps(x).encode()),'CURRENT_SEQ2_STATUS_APPLIED')
    def test_null(self):self.assertEqual(a.parse_receipt(None),'UNKNOWN')
    def test_malformed_json(self):self.assertEqual(a.parse_receipt(b'{'),'UNKNOWN')
    def test_non_object(self):self.assertEqual(a.parse_receipt(b'[]'),'UNKNOWN')
    def test_large(self):self.assertEqual(a.parse_receipt(b' '*12001),'UNKNOWN')
    def test_different_release(self):self.assertEqual(a.parse_receipt(receipt(release_id='different')),'UNKNOWN')
    def test_different_seq(self):self.assertEqual(a.parse_receipt(receipt(seq=3)),'UNKNOWN')
    def test_int_bool_exit(self):self.assertEqual(a.parse_receipt(receipt(rc=True)),'UNKNOWN')
    def test_refusal_not_restored(self):self.assertEqual(a.parse_receipt(receipt(restored=False)),'UNKNOWN')
    def test_unsafe_apply_result(self):self.assertEqual(a.parse_receipt(receipt(status='applied')),'UNKNOWN')
    def test_protected_mismatch(self):
        d=json.loads(receipt());d['protected_after']['stripchat-recorder']='false'
        self.assertEqual(a.parse_receipt(json.dumps(d).encode()),'UNKNOWN')
    def test_no_protected(self):self.assertEqual(a.parse_receipt(receipt(protected_before=None)),'UNKNOWN')
    def test_missing_protected_browser(self):
        d=json.loads(receipt());d['protected_before']['stripchat-browser-desktop.service']='inactive';d['protected_after']['stripchat-browser-desktop.service']='inactive'
        self.assertEqual(a.parse_receipt(json.dumps(d).encode()),'UNKNOWN')
    def test_line_unknown_allowed(self):
        d=json.loads(receipt());d['protected_before']['line-openchat-guard.service']='unknown';d['protected_after']['line-openchat-guard.service']='unknown'
        self.assertEqual(a.parse_receipt(json.dumps(d).encode()),'LEGACY_SEQ1_REFUSED_UNVERIFIED_MEMORY')
    def test_status_bad_exit(self):self.assertEqual(a.parse_receipt(receipt(2,'status','applied',3,False)),'UNKNOWN')
    def test_mismatched_new_installed_flag(self):
        d=json.loads(receipt(2,'status','applied',0));d.pop('code_restored');d['code_installed']=True
        self.assertEqual(a.parse_receipt(json.dumps(d).encode()),'UNKNOWN')
    def test_status_code_restored_mixed(self):
        d=json.loads(receipt(2,'status','applied',0,False));d['code_installed']=False
        self.assertEqual(a.parse_receipt(json.dumps(d).encode()),'UNKNOWN')
    def test_memory_not_certified_by_receipt(self):
        self.assertIn('UNVERIFIED_MEMORY',a.parse_receipt(receipt()))

class FakeM:
    def __init__(self,d,seq2=False,current=False,timeout900=False):
        self.d=Path(d);self.BASE=self.d/'code';self.BASE.mkdir()
        self.AGENT=self.BASE/'pull_agent.py';self.PUB=self.BASE/'release-signing-public.pem'
        self.SERVICE=self.d/'sc-vps-autodeploy.service';self.TIMER=self.d/'sc-vps-autodeploy.timer'
        self.STATE=self.d/'state'/'state.json';self.STATE.parent.mkdir()
        self.ENROLL_LOCK=self.d/'enroll.lock';self.BACKUP=self.d/'backups';self.BACKUP.mkdir()
        self.legacy=b'known legacy pinned agent';self.new=b'known current signed agent'
        self.key=b'verified public key';self.PUB_SHA256=a.sha(self.key)
        self.AGENT_SHA256=a.sha(self.new)
        self.UNIT_TIMER_180='[Timer]\nOnBootSec=180s\n'
        self.UNIT_TIMER_300='[Timer]\nOnBootSec=300s\n'
        self.legacy_service=b'[Service]\nTimeoutStartSec=260s\n'
        self.new_service=b'[Service]\nTimeoutStartSec=900s\n'
        self.AGENT.write_bytes(self.new if current else self.legacy)
        self.PUB.write_bytes(self.key)
        self.SERVICE.write_bytes(self.new_service if timeout900 else self.legacy_service)
        self.TIMER.write_bytes(self.UNIT_TIMER_300.encode())
        self.STATE.write_bytes(receipt(2,'status','applied',0,False) if seq2 else receipt())
        self.timer_active=True;self.watchdog_clear=True;self.status_runs=0;self.backups=[]
        self.fail_status=False;self.fail_fetch=False;self.sources_match=True
    def safe_read(self,p,limit=32768):return Path(p).read_bytes() if Path(p).exists() else None
    def agent_variant(self,b):return 'KNOWN_LEGACY' if b==self.legacy else 'CURRENT' if b==self.new else 'UNKNOWN'
    def service_variant(self,b):return 'SAFE_260_TIMEOUT_ONLY' if b==self.legacy_service else 'CURRENT' if b==self.new_service else 'UNKNOWN'
    def ensure_known_unit(self,p,b,variants):
        if b not in variants:raise a.Rejected('UNRECOGNIZED_TIMER')
    def systemd_state(self,u):return ('active' if self.timer_active else 'inactive') if 'timer' in u else 'inactive'
    def rollback_watchdogs_clear(self):return self.watchdog_clear
    def signed_v10_installed(self):return self.sources_match
    def fetch_trusted_agent(self):
        if self.fail_fetch:raise a.Rejected('SIGNED_SOURCE_UNAVAILABLE')
        return self.new
    def make_backup(self,path,content):
        self.backups.append((Path(path).name,content))
        q=self.BACKUP/(Path(path).name+'-'+str(len(self.backups))+'.bak');q.write_bytes(content)
        return q
    def atomic_update_existing(self,path,old,new):
        assert Path(path).read_bytes()==old
        Path(path).write_bytes(new)
    def verify_effective_timeout(self):
        if self.SERVICE.read_bytes()!=self.new_service:raise a.Rejected('NOT_900_SECONDS')
    def proc(self,*cmd,timeout=25):
        if cmd[:2]==('systemctl','stop') and cmd[-1]=='sc-vps-autodeploy.timer':self.timer_active=False;return ''
        if cmd[:2]==('systemctl','start') and cmd[-1]=='sc-vps-autodeploy.timer':self.timer_active=True;return ''
        if cmd[:3]==('systemctl','enable','--now') and cmd[-1]=='sc-vps-autodeploy.timer':self.timer_active=True;return ''
        if cmd[:2]==('systemctl','daemon-reload'):return ''
        if cmd[:2]==('systemctl','start') and cmd[-1]=='sc-vps-autodeploy.service':
            self.status_runs+=1
            d=json.loads(receipt(2,'status','needs_review' if self.fail_status else 'applied',5 if self.fail_status else 0))
            d.pop('code_restored');d['code_installed']=False
            self.STATE.write_text(json.dumps(d))
            return ''
        if cmd[:2]==('systemctl','show') and 'ActiveState' in cmd:return 'active'
        if cmd[0]=='docker':return 'true'
        raise AssertionError('unexpected command '+str(cmd))

class SimulatedMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.f=FakeM(self.temp.name)
    def invoke(self):
        safe={'browser':'active','line':'active','recorder':'true'}
        with patch.object(a,'load_verified_v5',return_value=self.f),\
             patch.object(a,'load_channel',return_value={'sequence':2,'operation':'status'}),\
             patch.object(a,'observe_protected',return_value=safe),\
             patch.object(a.os,'geteuid',return_value=0),\
             patch.object(a.sys,'argv',['activate_seq2_v6.py']):
            with contextlib.redirect_stdout(io.StringIO()):
                return a.main()
    def test_refusal_upgrades_only_updater_then_status(self):
        self.assertEqual(self.invoke(),0)
        self.assertEqual(self.f.AGENT.read_bytes(),self.f.new)
        self.assertEqual(self.f.SERVICE.read_bytes(),self.f.new_service)
        self.assertEqual(self.f.status_runs,1)
        self.assertTrue(self.f.timer_active)
        self.assertEqual(a.parse_receipt(self.f.STATE.read_bytes()),'CURRENT_SEQ2_STATUS_APPLIED')
        self.assertEqual([n for n,_ in self.f.backups],['pull_agent.py','sc-vps-autodeploy.service','state.json'])
    def test_repeated_safe_no_second_status(self):
        self.invoke();self.assertEqual(self.invoke(),0)
        self.assertEqual(self.f.status_runs,1)
    def test_seq2_already_received_not_reexecuted(self):
        self.f.STATE.write_bytes(receipt(2,'status','applied',0,False))
        self.invoke()
        self.assertEqual(self.f.status_runs,0)
        self.assertEqual(a.parse_receipt(self.f.STATE.read_bytes()),'LEGACY_SEQ2_STATUS_APPLIED')
        self.assertEqual(self.f.AGENT.read_bytes(),self.f.new)
    def test_seq2_missing_pinned_source_blocks(self):
        self.f.STATE.write_bytes(receipt(2,'status','applied',0,False));self.f.sources_match=False
        with self.assertRaisesRegex(a.Rejected,'LEGACY_SEQ2_SOURCE_HASH_MISMATCH'):self.invoke()
        self.assertEqual(self.f.AGENT.read_bytes(),self.f.legacy)
    def test_live_watchdog_blocks(self):
        self.f.watchdog_clear=False
        with self.assertRaisesRegex(a.Rejected,'ROLLBACK_WATCHDOGS_NOT_CLEAR'):self.invoke()
        self.assertTrue(self.f.timer_active)
    def test_bad_state_blocks(self):
        self.f.STATE.write_bytes(b'{}')
        with self.assertRaisesRegex(a.Rejected,'UNVERIFIED_PREVIOUS_RELEASE_STATE'):self.invoke()
        self.assertEqual(self.f.AGENT.read_bytes(),self.f.legacy)
    def test_unsigned_agent_blocks(self):
        self.f.AGENT.write_bytes(b'unknown')
        with self.assertRaisesRegex(a.Rejected,'UNRECOGNIZED_AGENT'):self.invoke()
    def test_fetch_failure_rolls_back_timer(self):
        self.f.fail_fetch=True
        with self.assertRaisesRegex(a.Rejected,'SIGNED_SOURCE_UNAVAILABLE'):self.invoke()
        self.assertEqual(self.f.SERVICE.read_bytes(),self.f.legacy_service)
        self.assertTrue(self.f.timer_active)
        self.assertEqual(self.f.STATE.read_bytes(),receipt())
    def test_status_failure_keeps_new_code_but_stops_timer(self):
        self.f.fail_status=True
        with self.assertRaisesRegex(a.Rejected,'SEQ2_SIGNED_STATUS_DID_NOT_PASS'):self.invoke()
        self.assertEqual(self.f.AGENT.read_bytes(),self.f.new)
        self.assertEqual(self.f.SERVICE.read_bytes(),self.f.new_service)
        self.assertFalse(self.f.timer_active)
    def test_current_code_old_state_can_finish(self):
        self.f.AGENT.write_bytes(self.f.new);self.f.SERVICE.write_bytes(self.f.new_service)
        self.invoke();self.assertEqual(self.f.status_runs,1)
    def test_current_and_modern_seq2_skips(self):
        self.f.AGENT.write_bytes(self.f.new);self.f.SERVICE.write_bytes(self.f.new_service)
        d=json.loads(receipt(2,'status','applied',0,False));d.pop('code_restored');d['code_installed']=False
        self.f.STATE.write_text(json.dumps(d))
        self.invoke();self.assertEqual(self.f.status_runs,0)
    def test_unknown_service_blocks(self):
        self.f.SERVICE.write_bytes(b'unknown service')
        with self.assertRaisesRegex(a.Rejected,'UNRECOGNIZED_SERVICE_UNIT'):self.invoke()
    def test_unknown_trust_root_blocks(self):
        self.f.PUB.write_bytes(b'bad key')
        with self.assertRaisesRegex(a.Rejected,'TRUST_ROOT_MISMATCH'):self.invoke()
    def test_unknown_timer_blocks(self):
        self.f.TIMER.write_bytes(b'unknown timer')
        with self.assertRaisesRegex(a.Rejected,'UNRECOGNIZED_TIMER'):self.invoke()

if __name__=='__main__':unittest.main()
