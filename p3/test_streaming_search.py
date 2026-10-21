from contextlib import closing
from pathlib import Path
import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import threading
import tracemalloc
import types
import unittest
from unittest.mock import patch as mock_patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import streaming_search_patch as patch

FIXTURE=(Path(__file__).parent/'fixtures/streaming_search_v123.py').read_bytes()
READER=(Path(__file__).parent/'fixtures/evidence_reader_v118.py').read_text()

def qa_pass(version,decision,rules):return version=='current' and decision=='PASS' and rules=={'ok':True}
POLICY=types.SimpleNamespace(current_qa_pass=qa_pass,PRICE_POLICY_VERSION='current')

def create_db(root,cases,records):
    dbpath=root/'public_evidence.db'
    with sqlite3.connect(dbpath) as db:
        db.executescript('CREATE TABLE cases(id TEXT PRIMARY KEY,payload TEXT);CREATE TABLE quote_records(id TEXT PRIMARY KEY,case_id TEXT,payload TEXT);')
        db.executemany('INSERT INTO cases VALUES(?,?)',[(r['id'],json.dumps(r,ensure_ascii=False)) for r in cases])
        db.executemany('INSERT INTO quote_records VALUES(?,?,?)',[(r['id'],r['case_id'],json.dumps(r,ensure_ascii=False)) for r in records])
    ns={'Path':Path,'sqlite3':sqlite3,'json':json,'closing':closing,'current_qa_pass':qa_pass,'PRICE_POLICY_VERSION':'current'}
    exec(READER,ns)
    return dbpath,ns['read_store'](dbpath)

def namespace(root,data,changed):
    ns={'Path':Path,'DATA_DIR':root}
    source=patch.transform(FIXTURE,expected_sha256=patch.sha(FIXTURE)) if changed else FIXTURE
    exec(compile(source,'<search-regression-fixture>','exec'),ns)
    ns['public_evidence_revision_tag']=lambda:'fixture-1'
    ns['public_quote_data']=lambda:data
    return ns

def fixture_data():
    cases=[{'id':'manual','title':'室內油漆與插座','region':'台中市','published':'2026-01-01','url':'https://example.com/a','provenance':{'keep':True}},
           {'id':'auto','title':'木地板油漆','source_line':'AUTO','source_status':'active','validation_policy_version':'current','auto_qa_decision':'PASS','auto_qa_rules':{'ok':True},'published':'2026-02-01'},
           {'id':'held','title':'油漆','price_qa_decision':'HOLD'},
           {'id':'rejected','title':'油漆','price_qa_decision':'REJECTED'},
           {'id':'stale','title':'油漆','source_line':'AUTO','source_status':'active','validation_policy_version':'old','auto_qa_decision':'PASS','auto_qa_rules':{'ok':True}},
           {'id':'inactive','title':'油漆','source_line':'AUTO','source_status':'probationary','validation_policy_version':'current','auto_qa_decision':'PASS','auto_qa_rules':{'ok':True}}]
    rows=[]
    for index,(cid,item,extra) in enumerate([
        ('manual','室內油漆',{'unit':'坪','amount_twd':30000,'specification':'批土一道、乳膠漆二道','review_status':'original_image_read'}),
        ('manual','插座110V',{'unit':'處','unit_price_twd':1800,'raw_price_text':'1,800元/處'}),
        ('manual','插座220V',{'unit':'處','unit_price_twd':2800}),
        ('auto','油漆',{'unit':'坪','unit_price_twd':1200,'review_status':'auto_public_text','price_qa_decision':'PASS','price_qa_policy_version':'current'}),
        ('auto','木地板',{'unit':'坪','amount_low_twd':4000,'amount_high_twd':6000,'price_qa_decision':'PASS','price_qa_policy_version':'current'}),
        ('auto','油漆',{'unit_price_twd':1,'price_qa_decision':'PASS','price_qa_policy_version':'old'}),
        ('auto','油漆',{'unit_price_twd':1,'price_qa_decision':'HOLD','price_qa_policy_version':'current'}),
        ('manual','油漆',{'unit_price_twd':1,'price_qa_decision':'REJECTED'}),
        ('held','油漆',{'unit_price_twd':1}),('rejected','油漆',{'unit_price_twd':1}),
        ('stale','油漆',{'unit_price_twd':1,'price_qa_decision':'PASS','price_qa_policy_version':'current'}),
        ('inactive','油漆',{'unit_price_twd':1,'price_qa_decision':'PASS','price_qa_policy_version':'current'}),
        ('manual','無價格項目',{})]):
        rows.append({'id':f'r{index}','case_id':cid,'item':item,**extra,'opaque_audit':{'retained':'exact'}})
    return cases,rows

class StreamingSearchTests(unittest.TestCase):
    def test_live_db_and_explicit_data_match_original_ranking_exactly(self):
        with tempfile.TemporaryDirectory() as td,mock_patch.dict(sys.modules,{'evidence_store':POLICY}):
            root=Path(td);cases,rows=fixture_data();db,data=create_db(root,cases,rows);before=hashlib.sha256(db.read_bytes()).hexdigest()
            for query in ['油漆','乳 膠 漆','批土','110V 插座','220V插座','超耐磨木地板','工程','無命中']:
                for limit in [1,3,18]:
                    with self.subTest(query=query,limit=limit):
                        old=namespace(root,data,False);new=namespace(root,data,True)
                        expected=old['rank_public_evidence_records'](query,unit='坪',region='台中市',limit=limit)
                        self.assertEqual(new['rank_public_evidence_records'](query,unit='坪',region='台中市',limit=limit),expected)
                        explicit=namespace(root,data,True)
                        self.assertEqual(explicit['rank_public_evidence_records'](query,unit='坪',region='台中市',limit=limit,data=data),expected)
            self.assertEqual(hashlib.sha256(db.read_bytes()).hexdigest(),before)

    def test_completed_read_transaction_releases_writer_lock(self):
        with tempfile.TemporaryDirectory() as td,mock_patch.dict(sys.modules,{'evidence_store':POLICY}):
            root=Path(td);db,data=create_db(root,*fixture_data());ns=namespace(root,data,True)
            ns['rank_public_evidence_records']('油漆')
            with sqlite3.connect(db,timeout=.1) as writer:
                writer.execute("INSERT INTO cases VALUES('writer','{}')");writer.commit()

    def test_default_analysis_does_not_call_bulk_store_or_cache_corpus(self):
        with tempfile.TemporaryDirectory() as td,mock_patch.dict(sys.modules,{'evidence_store':POLICY}):
            root=Path(td);db,data=create_db(root,*fixture_data());ns=namespace(root,data,True)
            def fail():raise AssertionError('bulk store must not load for analysis')
            ns['public_quote_data']=fail
            self.assertTrue(ns['rank_public_evidence_records']('油漆'))
            self.assertIsNone(ns['_PUBLIC_EVIDENCE_SEARCH_ROWS'])

    def test_duplicate_case_winning_row_keeps_original_stable_tie_order(self):
        cases=[{'id':'a','title':'','published':'2026-01-01'},{'id':'b','title':'','published':'2026-01-01'}]
        rows=[{'id':'a-low','case_id':'a','item':'牆面批土','amount_twd':1},
              {'id':'b-best','case_id':'b','item':'油漆','amount_twd':1},
              {'id':'a-best','case_id':'a','item':'油漆','amount_twd':1}]
        with tempfile.TemporaryDirectory() as td,mock_patch.dict(sys.modules,{'evidence_store':POLICY}):
            root=Path(td);db,data=create_db(root,cases,rows)
            old=namespace(root,data,False);new=namespace(root,data,True)
            expected=old['rank_public_evidence_records']('油漆',limit=2)
            self.assertEqual(new['rank_public_evidence_records']('油漆',limit=2),expected)
            self.assertEqual([h['record']['id'] for h in expected],['b-best','a-best'])

    def test_memory_bound_for_many_matching_rows_from_one_case(self):
        cases=[{'id':'one','title':'油漆'}]
        rows=[{'id':str(i),'case_id':'one','item':'油漆工程','amount_twd':1000,'audit_blob':'x'*8000} for i in range(1200)]
        with tempfile.TemporaryDirectory() as td,mock_patch.dict(sys.modules,{'evidence_store':POLICY}):
            root=Path(td);db,data=create_db(root,cases,rows);ns=namespace(root,data,True)
            tracemalloc.start()
            try:
                out=ns['rank_public_evidence_records']('油漆工程',limit=3);_,peak=tracemalloc.get_traced_memory()
            finally:tracemalloc.stop()
            self.assertEqual(len(out),1);self.assertEqual(out[0]['record']['audit_blob'],'x'*8000)
            self.assertLess(peak,2_000_000,'streaming search retained the full matching corpus')

    def test_cache_hit_does_not_open_database_again(self):
        with tempfile.TemporaryDirectory() as td,mock_patch.dict(sys.modules,{'evidence_store':POLICY}):
            root=Path(td);db,data=create_db(root,*fixture_data());ns=namespace(root,data,True)
            first=ns['rank_public_evidence_records']('油漆')
            def never_iterate(*args):
                raise AssertionError('unexpected database reread')
                yield
            ns['_judun_iter_search_evidence']=never_iterate
            self.assertIs(ns['rank_public_evidence_records']('油漆'),first)

    def test_parallel_identical_queries_share_one_scan(self):
        from concurrent.futures import ThreadPoolExecutor
        with tempfile.TemporaryDirectory() as td,mock_patch.dict(sys.modules,{'evidence_store':POLICY}):
            root=Path(td);db,data=create_db(root,*fixture_data());ns=namespace(root,data,True)
            original=ns['_judun_iter_search_evidence'];entered=threading.Event();release=threading.Event();calls=[]
            def observed(path):
                calls.append(path);entered.set()
                if not release.wait(2):raise RuntimeError('test synchronization timeout')
                yield from original(path)
            ns['_judun_iter_search_evidence']=observed
            with ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(ns['rank_public_evidence_records'],'油漆');self.assertTrue(entered.wait(1))
                b=pool.submit(ns['rank_public_evidence_records'],'油漆');release.set()
                self.assertIs(a.result(timeout=3),b.result(timeout=3))
            self.assertEqual(len(calls),1)

    def test_unrecognized_source_and_unsigned_apply_fail_closed(self):
        with self.assertRaisesRegex(ValueError,'CURRENT_APP_SHA_MISMATCH'):patch.transform(FIXTURE)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'release.json').write_text('{}');(root/'app.py').write_bytes(b'protected')
            with self.assertRaisesRegex(ValueError,'SIGNED_INNER_IDENTITY_MISMATCH'):patch.apply_signed_patch(root,root)
            self.assertEqual((root/'app.py').read_bytes(),b'protected')

if __name__=='__main__':unittest.main()
