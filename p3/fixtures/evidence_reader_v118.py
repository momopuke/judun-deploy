def read_store(db_path, include_held=False):
    uri=Path(db_path).resolve().as_uri()+'?mode=ro'
    with closing(sqlite3.connect(uri,uri=True,timeout=15)) as db:
        db.execute('BEGIN')
        cases=[json.loads(r[0]) for r in db.execute('SELECT payload FROM cases ORDER BY id')]
        held_cids={c['id'] for c in cases if c.get('price_qa_decision')=='HOLD'}
        auto_cids={c['id'] for c in cases if c.get('source_line')=='AUTO'}
        stale_cids={c['id'] for c in cases if c['id'] in auto_cids and (c.get('source_status')!='active' or not current_qa_pass(c.get('validation_policy_version'),c.get('auto_qa_decision'),c.get('auto_qa_rules')))}
        rejected_cids={c['id'] for c in cases if c.get('price_qa_decision')=='REJECTED'}
        blocked_record_cids=held_cids|rejected_cids
        blocked_case_cids=blocked_record_cids|stale_cids
        records=[];held_count=0;stale_rows=set()
        for (payload,) in db.execute('SELECT payload FROM quote_records ORDER BY rowid'):
            row=json.loads(payload)
            if row.get('price_qa_decision')=='HOLD' or row['case_id'] in held_cids:
                held_count+=1
            if row['case_id'] in auto_cids and (row['case_id'] in stale_cids or row.get('price_qa_decision')!='PASS' or row.get('price_qa_policy_version')!=PRICE_POLICY_VERSION):
                stale_rows.add(row['id'])
            if include_held or (row.get('price_qa_decision') not in ('HOLD','REJECTED') and row['case_id'] not in blocked_record_cids and row['id'] not in stale_rows):
                records.append(row)
    if not include_held:
        records=[r for r in records if r['id'] not in stale_rows]
        occupied={r['case_id'] for r in records}
        cases=[c for c in cases if c['id'] not in blocked_case_cids and (c['id'] not in auto_cids or c['id'] in occupied)]
    return dict(schema_version='judun.public-evidence.v1',cases=cases,records=records,qa_hold_cases=len(held_cids),qa_hold_records=held_count,qa_stale_cases=len(stale_cids),qa_stale_records=len(stale_rows))
