"""Fail-closed advisory gate for PUBLIC Taiwanese renovation-price evidence.

This is a standalone integration candidate, not a claim that the production
ingestion service currently uses it. Strict decisions should be applied
before formal evidence admission; do not auto-delete historic data.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import escape
from ipaddress import ip_address
from urllib.parse import urlsplit
import re

RENOVATION_TERMS = (
    "裝修", "裝潢", "室內設計", "室內裝修", "住宅改造", "翻新", "泥作",
    "油漆工程", "牆面油漆", "粉刷", "木地板", "磁磚", "鋪磚", "系統櫃",
    "木作", "木工裝潢", "拆除工程", "室內拆除", "水電工程", "管線配置",
    "衛浴裝修", "浴室翻新", "衛浴設備安裝", "廚具", "廚房裝修", "防水工程",
    "輕隔間", "天花板", "窗框更換", "門窗安裝", "隔音工程", "鋁窗",
    "裝修報價", "工程估價", "工程單價", "電路配置"
)
UNRELATED_TERMS = (
    "藥品採購", "醫療器材", "醫學院", "護理人員", "疫苗接種",
    "學校招生", "彩票", "下注", "賭博", "投資報酬率", "虛擬貨幣",
    "手機門號方案", "色情影片", "成人直播"
)
TAIWAN_TERMS = (
    "臺灣", "台灣", "臺北", "台北", "新北", "基隆", "桃園", "新竹", "苗栗",
    "臺中", "台中", "彰化", "南投", "雲林", "嘉義", "臺南", "台南",
    "高雄", "屏東", "宜蘭", "花蓮", "臺東", "台東", "澎湖", "金門", "連江"
)
UNITS = (
    "坪", "平方公尺", "m2", "m²", "㎡", "才", "組", "式", "公尺",
    "米", "片", "件", "顆", "間", "台", "樘", "平方尺"
)
TYPES = {
    "PRIMARY_CASE", "PLATFORM_QUOTE_STATS", "ESTIMATOR_BENCHMARK",
    "OFFICIAL_BENCHMARK", "EDITORIAL_REFERENCE"
}
BLOCKED_DOMAIN_LABELS = frozenset({"twfuns"})
AD_SIGNALS = ("點我頭像", "看我主頁", "加LINE詢價", "私訊報價", "洽詢報價", "來電洽詢")


@dataclass(frozen=True)
class GateDecision:
    status: str                     # REJECT, HOLD, REFERENCE_ONLY, COMPARABLE
    reasons: tuple[str, ...]
    eligible_for_formal_import: bool
    usable_for_exact_price_comparison: bool
    transaction_confirmed: bool = False

    def as_dict(self):
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "eligible_for_formal_import": self.eligible_for_formal_import,
            "usable_for_exact_price_comparison": self.usable_for_exact_price_comparison,
            "transaction_confirmed": self.transaction_confirmed,
        }


def public_source_url(value: object, blocked_labels=BLOCKED_DOMAIN_LABELS) -> bool:
    """No JavaScript links, internal addresses, credentials, or fragment-only URLs."""
    if not isinstance(value, str):
        return False
    value = value.strip()
    if len(value) > 2048 or not value:
        return False
    try:
        p = urlsplit(value)
        if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
            return False
        host = p.hostname.rstrip(".").lower()
        if host in ("localhost",) or not ("." in host):
            return False
        if any(label in blocked_labels for label in host.split(".")):
            return False
        try:
            ip = ip_address(host.strip("[]"))
        except ValueError:
            return True
        return ip.is_global
    except (ValueError, TypeError):
        return False


def parse_twd_amount(value: object) -> Decimal | None:
    """Parse explicit numeric price, supporting 萬 suffix but never guessing."""
    if isinstance(value, bool) or value is None:
        return None
    s = str(value).replace(",", "").replace("，", "").replace(" ", "").strip()
    match = re.fullmatch(r"(?:NT\$|NTD|TWD|新臺幣|新台幣|元)?\s*(\d+(?:\.\d+)?)\s*(萬|萬元|元)?", s, re.I)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1))
        if match.group(2) in ("萬", "萬元"):
            amount *= 10000
        if amount <= 0 or amount > 10000000000:
            return None
        return amount
    except (InvalidOperation, OverflowError):
        return None


def evaluate(record: dict) -> GateDecision:
    """Never claim a real paid transaction from text alone.

    REJECT = off-topic/explicitly prohibited/non-public URL.
    HOLD = potentially relevant but missing required verifiable fields.
    REFERENCE_ONLY = public Taiwanese price but not like-for-like evidence.
    COMPARABLE = structural comparability only, NOT independent proof of payment.
    """
    def d(status, *reasons):
        return GateDecision(
            status, tuple(reasons),
            eligible_for_formal_import=status in ("COMPARABLE", "REFERENCE_ONLY"),
            usable_for_exact_price_comparison=status == "COMPARABLE",
            transaction_confirmed=False,
        )

    if not isinstance(record, dict):
        return d("REJECT", "INVALID_RECORD")
    url = record.get("url", "")
    if not public_source_url(url):
        return d("REJECT", "BLOCKED_OR_NONPUBLIC_URL")

    title = str(record.get("title") or "")
    body = str(record.get("body") or "")
    category = str(record.get("category") or "")
    item_name = str(record.get("item_name") or "")
    subject = " ".join((title, body[:3500], category, item_name))
    has_topic = any(term in subject for term in RENOVATION_TERMS)
    unrelated = any(term in subject for term in UNRELATED_TERMS)
    if not has_topic:
        return d("REJECT", "NOT_RENOVATION_TOPIC")
    if unrelated:
        return d("HOLD", "MIXED_UNRELATED_CONTEXT_REVIEW")
    if any(term in subject for term in AD_SIGNALS) and not record.get("amount"):
        return d("HOLD", "PROMOTIONAL_CONTENT_NO_VERIFIABLE_PRICE")

    locality = str(record.get("locality") or record.get("region") or "")
    if not any(term in locality for term in TAIWAN_TERMS):
        return d("HOLD", "TAIWAN_LOCALITY_UNVERIFIED")

    currency = str(record.get("currency") or "").upper()
    if currency not in ("TWD", "NTD", "NT$", "新臺幣", "新台幣"):
        return d("HOLD", "CURRENCY_UNVERIFIED_OR_FOREIGN")

    amount = parse_twd_amount(record.get("amount"))
    if amount is None:
        return d("HOLD", "NO_VALID_EXPLICIT_PRICE")

    evidence_type = str(record.get("evidence_type") or "").upper()
    if evidence_type not in TYPES:
        return d("HOLD", "EVIDENCE_TYPE_NOT_CLASSIFIED")

    # Requiring a recorded stage blocks "asked price" being mislabeled as paid.
    phase = str(record.get("price_phase") or "")
    if not phase:
        return d("HOLD", "PRICE_PHASE_NOT_DOCUMENTED")

    if evidence_type != "PRIMARY_CASE":
        return d("REFERENCE_ONLY", "BENCHMARK_NOT_AN_INDIVIDUAL_CASE")

    raw_unit = str(record.get("unit") or "").strip()
    spec = str(record.get("spec") or "").strip()
    if not item_name or raw_unit not in UNITS or len(spec) < 2:
        return d("REFERENCE_ONLY", "ITEM_UNIT_OR_SPEC_NOT_COMPARABLE")
    return d("COMPARABLE", "EXACT_FIELDS_PRESENT_NOT_PAYMENT_PROOF")


def html_source_link(url: str, label: str = "查看原始公開來源") -> str:
    """Render raw public citation in a new tab, never as an internal redirect."""
    if not public_source_url(url):
        raise ValueError("Source URL rejected")
    return '<a href="' + escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer">' + escape(label) + '</a>'
