from typing import Any
import re,json,threading
_PUBLIC_EVIDENCE_RESULT_CACHE={}
_PUBLIC_EVIDENCE_SEARCH_TAG=None
_PUBLIC_EVIDENCE_SEARCH_ROWS=None
_JUDUN_EVIDENCE_CACHE_LOCK=threading.RLock()
APP_VERSION = '1.2.123'

RELEASE_REVISION = '1.2.123'

BUILD_SIGNATURE = 'JUDUN_1.2.123_REPORT_CLAIM_GUARD_20261022'

PUBLIC_EVIDENCE_MATCH_GROUPS = (
    ("油漆", "乳膠漆", "塗刷", "批土"),
    ("鋁窗", "鋁門窗", "氣密窗"),
    ("防水", "浴室防水", "屋頂防水"),
    ("清運", "垃圾清運", "廢棄物"),
    ("清潔", "細清", "粗清"),
    ("崁燈", "嵌燈", "筒燈"),
    ("塑鋼門", "浴室門"),
    ("牆磚", "壁磚", "磁磚"),
    ("地磚", "磁磚", "貼磚"),
    ("系統櫃", "衣櫃", "櫥櫃", "櫃體"),
    ("PVC", "塑膠管", "排水管"),
    ("天花板", "平釘", "矽酸鈣", "輕鋼架"),
    ("插座", "110V", "220V", "電源插座"),
    ("電箱", "配電盤", "開關箱"),
    ("網路", "弱電", "網路點"),
    ("門框", "門扇"),
    ("保護", "保護工程"),
    ("窗簾盒",),
    ("回風口", "出風口"),
    ("包樑", "包柱"),
    ("冷氣排水", "冷凝排水"),
    ("電視牆",),
    ("燈具", "照明"),
    ("熱水", "熱給水", "熱水管"),
    ("冷水", "冷給水", "冷水管"),
    ("拆除", "打除", "拆除工程"),
    ("泥作", "砌磚", "粉光", "水泥"),
    ("木作", "木工", "木作工程"),
    ("SPC", "超耐磨", "木地板", "地板"),
)

_PUBLIC_EVIDENCE_GENERIC_WORDS = {
    "工程", "施作", "施工", "安裝", "材料", "工資", "費用", "項目", "報價", "一式", "其他", "裝修", "室內", "基本", "新增", "更換",
}

def _evidence_compact_text(value: Any) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", str(value or "").casefold())

def _evidence_query_terms(value: Any) -> list[str]:
    raw = str(value or "").casefold()
    compact = _evidence_compact_text(raw)
    terms: list[str] = []
    for group in PUBLIC_EVIDENCE_MATCH_GROUPS:
        if any(_evidence_compact_text(term) in compact for term in group):
            terms.extend(group)
    for token in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]{2,}", raw):
        cleaned = token
        for suffix in ("工程", "施作", "施工", "安裝", "費用", "材料", "工資", "項目"):
            if cleaned.endswith(suffix) and len(cleaned) > len(suffix) + 1:
                cleaned = cleaned[:-len(suffix)]
        if len(cleaned) >= 2 and cleaned not in _PUBLIC_EVIDENCE_GENERIC_WORDS:
            terms.append(cleaned)
    out: list[str] = []
    seen = set()
    for term in terms:
        norm = _evidence_compact_text(term)
        if len(norm) >= 2 and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out[:18]

def _public_evidence_search_index(data: dict | None = None) -> tuple[str, list[dict]]:
    """Build normalized searchable text once per evidence DB revision.

    v1.2.49 normalized every one of ~thousands of rows again for every quote
    item and every AI chunk.  This cache keeps the same ranking rules while
    making retrieval cost nearly independent from the number of repeated
    analysis calls in one report.
    """
    with _JUDUN_EVIDENCE_CACHE_LOCK:
        global _PUBLIC_EVIDENCE_SEARCH_TAG, _PUBLIC_EVIDENCE_SEARCH_ROWS, _PUBLIC_EVIDENCE_RESULT_CACHE
        tag = public_evidence_revision_tag()
        if _PUBLIC_EVIDENCE_SEARCH_TAG == tag and isinstance(_PUBLIC_EVIDENCE_SEARCH_ROWS, list):
            return tag, _PUBLIC_EVIDENCE_SEARCH_ROWS
        data = data or public_quote_data()
        cases = {str(c.get("id") or ""): c for c in data.get("cases", []) if isinstance(c, dict)}
        rows: list[dict] = []
        for row in data.get("records", []):
            if not isinstance(row, dict):
                continue
            cid = str(row.get("case_id") or "")
            case = cases.get(cid)
            if not case:
                continue
            row_item = str(row.get("item") or "")
            spec = str(row.get("specification") or "")
            title = str(case.get("title") or row.get("logical_case_title") or "")
            context = _evidence_compact_text(" ".join((row_item, spec, title)))
            if not context:
                continue
            has_price = any(row.get(k) is not None for k in ("unit_price_twd", "amount_twd", "amount_low_twd", "amount_high_twd", "amount_upper_twd", "amount_upper_exclusive_twd")) or bool(str(row.get("raw_price_text") or "").strip())
            if not has_price:
                continue
            rows.append({
                "row": row, "case": case, "cid": cid, "context": context,
                "row_item": _evidence_compact_text(row_item),
                "unit": _evidence_compact_text(row.get("unit")),
                "region": _evidence_compact_text(case.get("region")).replace("臺", "台"),
                "status": str(row.get("review_status") or ""),
            })
        _PUBLIC_EVIDENCE_SEARCH_TAG = tag
        _PUBLIC_EVIDENCE_SEARCH_ROWS = rows
        _PUBLIC_EVIDENCE_RESULT_CACHE = {}
        return tag, rows

def rank_public_evidence_records(
    item_name: str,
    *,
    unit: str = "",
    region: str = "",
    limit: int = 5,
    data: dict | None = None,
) -> list[dict]:
    """本機規則式檢索：同工項優先，地區／單位／證據完整度加權；不呼叫模型。"""
    query = _evidence_compact_text(item_name)
    if not query or limit <= 0:
        return []
    terms = _evidence_query_terms(item_name)
    tag, indexed_rows = _public_evidence_search_index(data)
    unit_norm = _evidence_compact_text(unit)
    region_norm = _evidence_compact_text(region).replace("臺", "台")
    cache_key = (tag, query, tuple(terms), unit_norm, region_norm, int(limit))
    cached = _PUBLIC_EVIDENCE_RESULT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    scored: list[dict] = []
    for entry in indexed_rows:
        row, case, context = entry["row"], entry["case"], entry["context"]
        if "110v" in query and "220v" in context and "110v" not in context:
            continue
        if "220v" in query and "110v" in context and "220v" not in context:
            continue
        score = 0.0
        reasons: list[str] = []
        row_item_norm = entry["row_item"]
        if query in context or (row_item_norm and row_item_norm in query):
            score += 15
            reasons.append("工項名稱高度相近")
        term_hits = [term for term in terms if term in context]
        if term_hits:
            score += min(14, 4 + len(term_hits) * 2.5)
            reasons.append("同類工項關鍵字吻合")
        if not term_hits and score < 10:
            continue
        row_unit = entry["unit"]
        if unit_norm and row_unit:
            if unit_norm == row_unit:
                score += 4
                reasons.append("計價單位相同")
            else:
                score -= 1.5
        case_region = entry["region"]
        if region_norm and case_region:
            region_key = region_norm.replace("市", "").replace("縣", "")
            if region_key and region_key in case_region:
                score += 4
                reasons.append("施工地區相近")
        status = entry["status"]
        if status == "original_image_read":
            score += 3.5
            reasons.append("原圖數量／單價已核對")
        elif status == "original_image_amount_read":
            score += 2.5
            reasons.append("原圖金額已核對")
        elif status in {"public_text_read", "source_text_read"}:
            score += 1.2
        elif status == "auto_public_text":
            score -= 0.5
        score += 1.5
        if row.get("record_kind") in {"分項", "單價"}:
            score += 1.2
        if "政府／公共文件" in str(row.get("evidence_stage") or ""):
            score -= 2.0
        if score <= 5:
            continue
        scored.append({"score": round(score, 2), "match_reason": "、".join(dict.fromkeys(reasons)) or "同類工項公開參考", "record": row, "case": case})

    scored.sort(key=lambda hit: (hit["score"], str(hit["case"].get("published") or "")), reverse=True)
    unique: list[dict] = []
    seen_cases = set()
    for hit in scored:
        cid = str(hit["record"].get("case_id") or "")
        if cid in seen_cases:
            continue
        seen_cases.add(cid)
        unique.append(hit)
        if len(unique) >= limit:
            break
    if len(_PUBLIC_EVIDENCE_RESULT_CACHE) > 512:
        _PUBLIC_EVIDENCE_RESULT_CACHE.clear()
    _PUBLIC_EVIDENCE_RESULT_CACHE[cache_key] = unique
    return unique

def build_public_evidence_context(
    items: list[dict],
    project_profile: dict | None = None,
    *,
    per_item: int | None = None,
    max_total: int = 32,
    max_chars: int = 15000,
) -> dict:
    """把正式公開證據庫縮成少量高相關摘要；本機檢索後以 round-robin 分配，避免前幾列吃光證據額度。"""
    profile = clean_project_profile(project_profile or {}) if "PROJECT_PROFILE_OPTIONS" in globals() else (project_profile or {})
    region = str(profile.get("region") or "")
    clean_items = [item for item in (items or []) if isinstance(item, dict)]
    per_item = int(per_item or _dynamic_public_evidence_per_item(len(clean_items)))
    data = public_quote_data()

    candidates: list[dict] = []
    for index, item in enumerate(clean_items, start=1):
        name = str(item.get("項目", item.get("item", "")) or "").strip()
        unit = str(item.get("單位", item.get("unit", "")) or "").strip()
        if not name:
            continue
        hits = rank_public_evidence_records(name, unit=unit, region=region, limit=per_item, data=data)
        if hits:
            candidates.append({"index": index, "name": name, "hits": hits, "selected": []})

    # 每輪每個工項最多拿一筆。大型報價即使總額度有限，也不會只餵前幾列。
    total_hits = 0
    for rank in range(per_item):
        for bucket in candidates:
            if total_hits >= max_total:
                break
            hits = bucket["hits"]
            if rank < len(hits):
                bucket["selected"].append(hits[rank])
                total_hits += 1
        if total_hits >= max_total:
            break

    lines: list[str] = []
    emitted_hits = 0
    for bucket in candidates:
        item_lines = []
        for hit in bucket["selected"]:
            row, case = hit["record"], hit["case"]
            missing = row.get("missing_fields") or case.get("missing") or []
            if not isinstance(missing, list):
                missing = []
            review_title, _ = _public_review_label(row)
            item_lines.append({
                "source_item": str(row.get("item") or "")[:70],
                "price": _public_amount_label(row),
                "region": str(case.get("region") or "")[:36],
                "published": str(case.get("published") or "")[:10],
                "unit": str(row.get("unit") or "")[:16],
                "spec": str(row.get("specification") or "")[:90],
                "status": review_title,
                "why": hit["match_reason"],
            })
        if not item_lines:
            continue
        line = json.dumps({"quote_index": bucket["index"], "quote_item": bucket["name"][:120], "references": item_lines}, ensure_ascii=False, separators=(",", ":"))
        if sum(len(x) + 1 for x in lines) + len(line) > max_chars:
            # 若整組過長，保留該工項最相關的第一筆再嘗試，優先維持覆蓋面。
            slim = json.dumps({"quote_index": bucket["index"], "quote_item": bucket["name"][:120], "references": item_lines[:1]}, ensure_ascii=False, separators=(",", ":"))
            if sum(len(x) + 1 for x in lines) + len(slim) > max_chars:
                continue
            line, item_lines = slim, item_lines[:1]
        lines.append(line)
        emitted_hits += len(item_lines)

    if lines:
        text = "\n".join(lines)
    else:
        text = "本次正式公開證據庫沒有找到足夠相關的工項資料；不得因此推定報價合理或不合理。"
    return {
        "text": text,
        "match_count": emitted_hits,
        "per_item": per_item,
        "item_count": len(clean_items),
        "revision": public_evidence_revision_tag(),
    }

