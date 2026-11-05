import copy,json,os,tempfile,time,unittest,zlib
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch
import SC_VPS_Rescue_v18 as m

def sample(**values):
    d=dict(cpu=99.4,mf=30.6,io=0,av=699,sf=1393,hi=866.4,oom=0,mc=568,bp=20.7,use=36.3,cf=80,mh=546,q=20)
    d.update(values);return d

class Repair(unittest.TestCase):
    def simulate(self,mem_bad=False,cpu_bad=False,identity_bad=False,initial_max=None):
        policy=[m.OLD_HIGH,m.OLD_CPU];history=[];saved=[];hard=[initial_max or m.NEW_MAX]
        mem=sample(mf=3,hi=0,av=600,mc=630,mh=674)
        if mem_bad:mem.update(hi=800,mf=30)
        cpu=sample(mf=1,hi=0,av=590,mc=640,mh=674,q=50,bp=50,use=66,cf=50 if not cpu_bad else 80)
        def setp(oh,oc,nh,nc):
            self.assertEqual(policy,[oh,oc]);policy[:]=[nh,nc];history.append((nh,nc))
        with ExitStack() as st:
            st.enter_context(patch.object(m,'identity',side_effect=lambda:['changed'] if identity_bad and history else ['stable']))
            st.enter_context(patch.object(m,'measure',side_effect=[sample(),mem,mem,mem,cpu,cpu,cpu]))
            st.enter_context(patch.object(m,'save',side_effect=lambda s:saved.append(copy.deepcopy(s))))
            st.enter_context(patch.object(m,'number',side_effect=lambda p:hard[0] if p.name=='memory.max' else policy[0]))
            st.enter_context(patch.object(m,'set_max',side_effect=lambda old,new:hard.__setitem__(0,new)))
            st.enter_context(patch.object(m,'quota',side_effect=lambda:policy[1]))
            st.enter_context(patch.object(m,'matching',side_effect=lambda h,c:policy==[h,c]))
            st.enter_context(patch.object(m,'set_policy',side_effect=setp))
            st.enter_context(patch.object(m,'arm',side_effect=lambda s:s.update(watchdog='sc-vps-v18-rollback-42.timer')))
            st.enter_context(patch.object(m,'disarm'))
            s={};m.repair(s)
        return s,policy,history,saved

    def test_verified_two_independent_improvements(self):
        s,p,h,_=self.simulate();self.assertEqual(s['status'],'verified');self.assertTrue(s['accepted'])
        self.assertEqual(p,[m.NEW_HIGH,50]);self.assertEqual(h,[(m.NEW_HIGH,20),(m.NEW_HIGH,50)])

    def test_original_tight_hard_cap_is_raised_with_reserve(self):
        s,p,_,_=self.simulate(initial_max=600*m.MiB)
        self.assertEqual(s['status'],'verified');self.assertEqual(s['original_max'],600*m.MiB)
        self.assertTrue(s['max_raised']);self.assertEqual(p,[m.NEW_HIGH,50])

    def test_coupled_trial_can_resolve_initial_memory_stall(self):
        s,p,h,_=self.simulate(mem_bad=True);self.assertEqual(s['status'],'verified')
        self.assertEqual(p,[m.NEW_HIGH,50]);self.assertIn((m.NEW_HIGH,50),h)

    def test_unhelpful_cpu_returns_both_original(self):
        s,p,_,_=self.simulate(cpu_bad=True);self.assertEqual(s['status'],'rolled_back');self.assertEqual(p,[m.OLD_HIGH,20])

    def test_changed_protected_identity_aborts_and_restores(self):
        s,p,_,_=self.simulate(identity_bad=True);self.assertEqual(s['status'],'rolled_back');self.assertEqual(p,[m.OLD_HIGH,20])

    def test_low_reserve_never_arms(self):
        with patch.object(m,'identity',return_value=[]),patch.object(m,'measure',return_value=sample(av=450)),patch.object(m,'matching',return_value=True),patch.object(m,'number',return_value=768*m.MiB),patch.object(m,'save'),patch.object(m,'arm') as arm:
            s={};m.repair(s);self.assertEqual(s['status'],'refused');arm.assert_not_called()

    def test_unknown_policy_never_arms(self):
        with patch.object(m,'identity',return_value=[]),patch.object(m,'measure',return_value=sample()),patch.object(m,'matching',return_value=False),patch.object(m,'save'),patch.object(m,'arm') as arm:
            s={};m.repair(s);self.assertEqual(s['reason'],'unknown_existing_policy');arm.assert_not_called()

    def test_safe_rejects_oom_missing_and_pressure(self):
        self.assertTrue(m.safe(sample(),0))
        for d in (sample(oom=1),sample(av=369),sample(sf=299),sample(io=6),sample(cf=None)):
            self.assertFalse(m.safe(d,0))

    def test_forged_watchdog_names_rejected(self):
        self.assertTrue(m.watchdog_name('sc-vps-v18-rollback-42.timer'))
        for name in ('docker.service','sc-vps-v18-rollback-42.service','sc-vps-v18-rollback-../../.timer',None):
            self.assertFalse(m.watchdog_name(name))

    def test_watchdog_restores_interrupted_trial(self):
        s={'v':18,'status':'trial'}
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'state',return_value=s),patch.object(m,'restore') as restore:
            m.watchdog();restore.assert_called_once_with(s)

    def test_watchdog_keeps_accepted_policy(self):
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'state',return_value={'v':18,'status':'verified'}),patch.object(m,'restore') as restore:
            m.watchdog();restore.assert_not_called()

    def test_foreign_policy_not_overwritten_by_rollback(self):
        with patch.object(m,'number',return_value=999*m.MiB),patch.object(m,'quota',return_value=75),patch.object(m,'set_policy') as setter:
            with self.assertRaises(m.v15.Refused):m.restore({'v':18})
            setter.assert_not_called()

    def test_concurrent_change_blocks_mutation(self):
        with patch.object(m,'matching',return_value=False),patch.object(m.v15,'cmd') as cmd:
            with self.assertRaises(m.v15.Refused):m.set_policy(m.OLD_HIGH,20,m.NEW_HIGH,20)
            cmd.assert_not_called()

    def test_hard_cap_not_lowered_below_resident_use(self):
        s={'v':18,'max_raised':True,'original_max':650*m.MiB}
        with patch.object(m,'number',side_effect=lambda p: m.OLD_HIGH if p.name=='memory.high' else 700*m.MiB if p.name=='memory.current' else m.NEW_MAX),patch.object(m,'quota',return_value=20),patch.object(m,'save'),patch.object(m,'set_max') as setmax:
            m.restore(s);self.assertEqual(s['status'],'rolled_back_max_pending');setmax.assert_not_called()

    def test_hard_cap_restored_after_resident_use_drains(self):
        s={'v':18,'max_raised':True,'original_max':650*m.MiB}
        with patch.object(m,'number',side_effect=lambda p: m.OLD_HIGH if p.name=='memory.high' else 600*m.MiB if p.name=='memory.current' else m.NEW_MAX),patch.object(m,'quota',return_value=20),patch.object(m,'save'),patch.object(m,'set_max') as setmax:
            m.restore(s);self.assertEqual(s['status'],'rolled_back');setmax.assert_called_once_with(m.NEW_MAX,650*m.MiB)

    def test_nonroot_cannot_install_run_or_watchdog(self):
        with patch.object(m.os,'geteuid',return_value=1000):
            for fn in (m.install,m.run,m.rollback,m.watchdog):
                with self.assertRaises(m.v15.Refused):fn()

    def test_foreign_units_prevent_install(self):
        with patch.object(m.os,'geteuid',return_value=0),patch.object(m,'SOURCE',Path(__file__)),patch.object(m.v15,'read_unit',return_value=b'foreign'),patch.object(m.v15,'cmd') as cmd:
            with self.assertRaises(m.v15.Refused):m.install()
            cmd.assert_not_called()

class Cleanup(unittest.TestCase):
    def exercise(self,remote=True,opened=False,young=False,changed=False):
        with tempfile.TemporaryDirectory() as td,ExitStack() as st:
            root=Path(td);ready=root/'ready';folder=ready/'model';folder.mkdir(parents=True)
            merge=folder/'clip_MERGE.mkv';merge.write_bytes(b'123456')
            original=folder/'clip.mkv';original.write_bytes(b'original')
            os.utime(merge,(time.time()-20000,time.time()-(1 if young else 20000)))
            st.enter_context(patch.object(m,'READY',ready));st.enter_context(patch.object(m,'upload_route_known',return_value=True))
            st.enter_context(patch.object(m,'open_files',return_value={str(merge)} if opened else set()))
            st.enter_context(patch.object(m,'verified_remote',return_value=remote));st.enter_context(patch.object(m.v15,'safe_write'))
            st.enter_context(patch.object(m,'inventory',return_value=[0,0,0,0,False]))
            if changed:st.enter_context(patch.object(m,'fingerprint',side_effect=[(1,2,6,4,5),(1,2,6,9,10)]))
            result=m.cleanup();return result,merge.exists(),original.exists()

    def test_deletes_only_exact_remote_verified_merge(self):
        d,exists,original=self.exercise();self.assertEqual((d['n'],d['b'],exists,original),(1,6,False,True))

    def test_remote_mismatch_preserves_merge(self):
        d,exists,_=self.exercise(remote=False);self.assertEqual(d['n'],0);self.assertTrue(exists)

    def test_open_merge_preserved(self):
        d,exists,_=self.exercise(opened=True);self.assertEqual(d['n'],0);self.assertTrue(exists)

    def test_young_merge_preserved(self):
        d,exists,_=self.exercise(young=True);self.assertEqual(d['n'],0);self.assertTrue(exists)

    def test_changed_merge_preserved(self):
        d,exists,_=self.exercise(changed=True);self.assertEqual(d['n'],0);self.assertTrue(exists)

    def test_remote_exact_path_size_and_type(self):
        with patch.object(m,'READY',Path('/ready')),patch.object(m.v15,'cmd',return_value=json.dumps({'Name':'clip_MERGE.mkv','Size':6,'IsDir':False})) as cmd:
            self.assertTrue(m.verified_remote(Path('/ready/model/clip_MERGE.mkv'),6))
            self.assertIn(m.REMOTE+'/model/clip_MERGE.mkv',cmd.call_args.args)
            self.assertFalse(m.verified_remote(Path('/ready/model/clip_MERGE.mkv'),7))

    def test_ambiguous_remote_layout_rejected(self):
        with patch.object(m,'READY',Path('/ready')),patch.object(m.v15,'cmd') as cmd:
            self.assertFalse(m.verified_remote(Path('/ready/clip_MERGE.mkv'),6));cmd.assert_not_called()

    def test_symlinks_and_hardlinks_not_regular(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'a').write_text('x');(p/'link').symlink_to(p/'a')
            self.assertFalse(m.regular(p/'link'));os.link(p/'a',p/'b');self.assertFalse(m.regular(p/'a'))

    def test_unverified_existing_route_cannot_delete(self):
        with patch.object(m,'upload_route_known',return_value=False),patch.object(m,'inventory',return_value=[]),patch.object(m.v15,'safe_write'),patch.object(m,'open_files') as opened:
            d=m.cleanup();self.assertEqual(d['reason'],'uploader_route_not_verified');opened.assert_not_called()

class Receipt(unittest.TestCase):
    def test_packet_size_fits_encryption_with_realistic_inventory(self):
        s={'status':'verified','reason':'measured_memory_and_cpu_full_stall_reduction','pre':sample(),'post':sample(mf=1,hi=0,mh=674,q=50,cf=50)}
        cl={'n':3,'b':8000000000,'err':0,'reason':'remote_verified_merge_copies_removed','inventory':[[100,11000,20,5000,False]]*3,'upload':[int(time.time()),100,200,0]}
        with tempfile.TemporaryDirectory() as td,patch.object(m,'ROOT',Path(td)),patch.object(m.v15,'read_json',return_value={'last_sequence':13,'status':'applied'}),patch.object(m.v15,'protected',return_value=[True,True]),patch.object(m.v16,'unit_state',return_value={'active':True,'r':1590,'x':251}),patch.object(m,'forward_errors',return_value=[0,1,2]),patch.object(m,'post',return_value=200) as send:
            m.receipt(s,cl);self.assertEqual(send.call_count,1)

    def test_retire_only_exact_owned_diagnostics(self):
        with patch.object(m.v15,'read_unit',return_value=b'foreign'),patch.object(m.v15,'cmd') as cmd,patch.object(m.v15,'safe_write'):
            self.assertEqual(m.retire_legacy(),[]);cmd.assert_not_called()
        expected={}
        for module in (m.v13,m.v15,m.v16,m.v17):
            expected[module.SERVICE]=module.SERVICE_TEXT.encode();expected[module.TIMER]=module.TIMER_TEXT.encode()
        with patch.object(m.v15,'read_unit',side_effect=expected.get),patch.object(m.v15,'cmd') as cmd,patch.object(m.v15,'safe_write'):
            self.assertEqual(m.retire_legacy(),[13,15,16,17]);self.assertEqual(cmd.call_count,4)
            self.assertTrue(all('timer' in c.args[3] for c in cmd.call_args_list))

    def test_publish_limit_is_recorded_and_backup_receives(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'ROOT',Path(td)),patch.object(m,'post',side_effect=[429,200]) as post:
            m.deliver({'v':18,'k':'maintenance','ts':1,'seq':13})
            d=json.loads((Path(td)/'last_receipt.json').read_text());self.assertEqual(d['net'],429)
            self.assertTrue(post.call_args.args[0].startswith('https://ntfy.envs.net/'))

    def test_failed_backup_never_claims_delivery(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'ROOT',Path(td)),patch.object(m,'post',side_effect=[429,503,429]):
            with self.assertRaises(m.v15.Refused):m.deliver({'v':18,'k':'maintenance','ts':1,'seq':13})

    def test_original_relay_can_recover_after_previous_limit(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'ROOT',Path(td)),patch.object(m,'post',side_effect=[503,200]) as post:
            (Path(td)/'relay_probe.json').write_text(json.dumps({'code':429,'at':1}))
            m.deliver({'v':18,'k':'maintenance','ts':1,'seq':15})
            self.assertEqual(post.call_count,2)

    def test_bounded_packet_keeps_core_metrics(self):
        with tempfile.TemporaryDirectory() as td,patch.object(m,'ROOT',Path(td)),patch.object(m,'post',return_value=200):
            d={'v':18,'k':'maintenance','ts':1,'seq':13,'iv':list(range(1000)),'fe':list(range(1000))}
            m.deliver(d);self.assertEqual(d['v'],18);self.assertNotIn('iv',d)

if __name__=='__main__':unittest.main()
