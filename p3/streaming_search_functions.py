def _judun_iter_search_evidence(db_path):
    """Stream eligible search rows in one read snapshot; never cache the corpus."""
    import json
    from contextlib import closing
    from pathlib import Path
    import sqlite3
    from evidence_store import current_qa_pass, PRICE_POLICY_VERSION
    uri = Path(db_path).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=15)) as db:
        db.execute('BEGIN')
        cases = {}
        auto_cids = set()
        for (payload,) in db.execute('SELECT payload FROM cases ORDER BY id'):
            case = json.loads(payload)
            cid = case['id']
            is_auto = case.get('source_line') == 'AUTO'
            if is_auto:
                auto_cids.add(cid)
            if case.get('price_qa_decision') in {'HOLD', 'REJECTED'}:
                continue
            if is_auto and (case.get('source_status') != 'active'
                            or not current_qa_pass(case.get('validation_policy_version'),
                                                   case.get('auto_qa_decision'),
                                                   case.get('auto_qa_rules'))):
                continue
            cases[str(cid)] = case
        for (payload,) in db.execute('SELECT payload FROM quote_records ORDER BY rowid'):
            row = json.loads(payload)
            cid = str(row['case_id'])
            case = cases.get(cid)
            if not case or row.get('price_qa_decision') in {'HOLD', 'REJECTED'}:
                continue
            if cid in auto_cids and (row.get('price_qa_decision') != 'PASS'
                                      or row.get('price_qa_policy_version') != PRICE_POLICY_VERSION):
                continue
            row_item = str(row.get('item') or '')
            spec = str(row.get('specification') or '')
            title = str(case.get('title') or row.get('logical_case_title') or '')
            context = _evidence_compact_text(' '.join((row_item, spec, title)))
            if not context:
                continue
            has_price = any(row.get(key) is not None for key in (
                'unit_price_twd', 'amount_twd', 'amount_low_twd', 'amount_high_twd',
                'amount_upper_twd', 'amount_upper_exclusive_twd')) or bool(str(row.get('raw_price_text') or '').strip())
            if not has_price:
                continue
            yield {'row':row, 'case':case, 'cid':cid, 'context':context,
                   'row_item':_evidence_compact_text(row_item),
                   'unit':_evidence_compact_text(row.get('unit')),
                   'region':_evidence_compact_text(case.get('region')).replace('臺','台'),
                   'status':str(row.get('review_status') or '')}
