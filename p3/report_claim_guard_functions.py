def _judun_risk_score(value):
    """Validate the declared 0–10 scale; never guess a percentage conversion."""
    import re
    from decimal import Decimal, InvalidOperation
    if isinstance(value, bool) or value is None:
        return '待核對'
    text = str(value).strip()
    if len(text) > 60:
        return '待核對'
    match = re.fullmatch(r'(\d{1,2}(?:\.\d{1,4})?)\s*(?:/\s*10)?', text)
    if not match:
        return '待核對'
    try:
        score = Decimal(match.group(1))
    except InvalidOperation:
        return '待核對'
    if not score.is_finite() or not 0 <= score <= 10:
        return '待核對'
    return format(score.normalize(), 'f') + '/10'


def _judun_guard_report_claims(data):
    """Guard copied render data only; leave stored analysis and amounts intact."""
    import copy
    import re
    result = copy.deepcopy(data) if isinstance(data, dict) else {}
    result['risk_score'] = _judun_risk_score(result.get('risk_score'))
    rows = result.get('items_analysis')
    # Exact backend evidence labels, never free-form model claims of approval.
    model_only = (isinstance(rows, list) and bool(rows)
                  and all(isinstance(row, dict) and row.get('source_level') == 'C'
                          for row in rows))
    if not model_only:
        return result
    claims = [
        (r'(?:工項單價|本案價格|報價價格)與(?:公開)?市場行情相符',
         '本案價格目前僅有模型情境估算，仍須同規格詢價核對'),
        (r'(?:符合|落在)(?:一般|公開)?市場(?:行情|合理)?區間',
         '僅可與模型情境估算對照，仍須同規格詢價核對'),
        (r'本案工項與價格皆屬合理範圍',
         '本案價格比較屬模型情境估算，尚未核驗為同規格市場價格'),
    ]
    def walk(value):
        if isinstance(value, dict):
            return {key: walk(item) for key, item in value.items()}
        if isinstance(value, list):
            return [walk(item) for item in value]
        if not isinstance(value, str):
            return value
        phrases = claims + [
            ('並無重大惡意缺漏', '施工安全與契約責任仍待專業核對'),
            ('即可安心簽約', '仍應核對完整契約與施工條件，再決定是否簽約'),
            ('即可進行簽約動工', '仍應核對完整契約與施工條件，再決定是否簽約動工'),
        ]
        for pattern, replacement in phrases:
            def replace(match):
                context = value[max(0, match.start()-24):match.start()]
                if re.search(r'(?:不代表|不保證|不能認定|無法認定|未能確認|不得宣稱)[^。；\n]{0,8}$', context):
                    return match.group(0)
                return replacement
            value = re.sub(pattern, replace, value)
        return value
    # Apply only to generated commentary, never source URLs, quoted customer
    # specifications, numerical fields, prices, evidence records or entitlements.
    for key in ['advisor_summary', 'final_decision', 'categories', 'top5_actions',
                'action_guides', 'advanced_guides']:
        if key in result:
            result[key] = walk(result[key])
    for row in result['items_analysis']:
        for key in ['comment', 'action_tip', 'estimate_assumptions']:
            if key in row:
                row[key] = walk(row[key])
    return result
