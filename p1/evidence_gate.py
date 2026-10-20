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
    status: str                     # REJECT, HOLD, REFERENCE_ONLY, READY_FOR_MATCHING, COMPARABLE
    reasons: tuple[str, ...]
    eligible_for_formal_import: bool  # Always false before existing human/QA admission
    usable_for_exact_price_comparison: bool
    transaction_confirmed: bool = False

    def as_dict(self):
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "eligible_for_formal_import": self.eligible_for_formal_import,
            "eligible_for_formal_qa": self.status in ("REFERENCE_ONLY", "READY_FOR_MATCHING", "COMPARABLE"),
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
        # Reject malformed ports and local naming aliases without DNS queries.
        try:
            port = p.port
        except ValueError:
            return False
        if port is not None and not 1 <= port <= 65535:
            return False
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            return False
        if any(label in blocked_labels for label in host.split(".")):
            return False
        try:
            ip = ip_address(host.strip("[]"))
        except ValueError:
            # Alternate numeric IPv4 notation (127.1, 0177.0.0.1, 0x7f.1)
            # can resolve to loopback despite ipaddress rejecting the syntax.
            if re.fullmatch(r"(?:0x[0-9a-f]+|[0-9]+)(?:\.(?:0x[0-9a-f]+|[0-9]+)){1,3}", host):
                return False
            # Well-known wildcard DNS hosts may encode a private IP in their
            # labels. Literal rejection helps, but collector DNS checks are
            # STILL mandatory for all actual fetches.
            for suffix in (".nip.io", ".sslip.io"):
                if host.endswith(suffix):
                    literal = host[:-len(suffix)].replace("-", ".")
                    try:
                        decoded_ip = ip_address(literal)
                    except ValueError:
                        return False  # unknown wildcard encoding, fail closed
                    return decoded_ip.is_global
            return True
        return ip.is_global
    except (ValueError, TypeError):
        return False


def parse_twd_amount(value: object) -> Decimal | None:
    """Parse explicit numeric price, supporting 萬 suffix but never guessing."""
    if isinstance(value, bool) or value is None:
        return None
    raw = str(value)
    if len(raw) > 64:
        return None
    s = raw.replace(",", "").replace("，", "").replace(" ", "").strip()
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



# A normalized numeric amount from a parser is NOT itself source evidence.
# Only accept a price that appears near a currency marker or price descriptor
# in the captured public title/quote excerpt. Bare years, floor areas and
# arbitrary digits never count as price evidence.
_PRICE_NUMBER = r"(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:\.\d+)?"
_SOURCE_PRICE_PATTERN = re.compile(
    rf"(?:"
    rf"(?:NT\s*\$|NTD|TWD|新[臺台]幣|[$＄])\s*(?P<currency_amount>{_PRICE_NUMBER})\s*(?P<currency_unit>萬元?|元)?"
    rf"|(?P<unit_amount>{_PRICE_NUMBER})\s*(?P<unit_suffix>萬元?|元)"
    rf"|(?:報價|估價|價格|單價|總價|金額|費用|每坪|一坪|每平方公尺|單坪價)"
    rf"\s*(?:[:：]|約|為|是|從)?\s*(?P<label_amount>{_PRICE_NUMBER})\s*(?P<label_suffix>萬元?|元)?"
    rf")",
    re.I,
)


def source_price_precision(title: str, excerpt: str, amount: Decimal) -> str:
    """Return EXACT / APPROXIMATE / ABSENT for the price quoted in source.

    Matching a price embedded in a range, approximation or "from" figure
    cannot substantiate a single exact unit price.
    """
    if not isinstance(title, str) or not isinstance(excerpt, str):
        return "ABSENT"
    approximate_seen = False
    exact_seen = False
    for text in (title[:500], excerpt[:3500]):
        for found in _SOURCE_PRICE_PATTERN.finditer(text):
            for key, suffix in (("currency_amount", "currency_unit"),
                                ("unit_amount", "unit_suffix"),
                                ("label_amount", "label_suffix")):
                numeric = found.group(key)
                if numeric is None:
                    continue
                parsed = parse_twd_amount(numeric + (found.group(suffix) or ""))
                if parsed is None or parsed != amount:
                    continue
                head = text[max(0, found.start() - 6):found.start()]
                tail = text[found.end():found.end() + 15]
                # Adjacent unambiguous date/floor-area tokens are not prices.
                if re.match(r"^\s*(?:年(?:度|份)?|坪|㎡|平方(?:公尺|米)?|日|月|號)", tail):
                    continue
                # Pricing ranges, starting prices, and approximations may be
                # useful for market context but must not support an exact gap.
                is_approximate = (
                    bool(re.search(r"(?:約|大約|概估|起價|起跳|最低|從|至少|大概|約莫)\s*$", head))
                    or "約" in found.group(0)
                    or bool(re.match(r"^\s*(?:[-~～〜－–—]|至|到|起|以上|以下|上下|左右|不等)", tail))
                    or bool(re.search(r"(?:[-~～〜－–—]|至|到)\s*$", head))
                )
                if is_approximate:
                    approximate_seen = True
                else:
                    exact_seen = True
    # A second occurrence saying "starting at"/"approximately" contradicts
    # interpreting the very same parsed amount as one settled point price.
    # Conservatively retain it as reference, regardless of text order.
    if approximate_seen:
        return "APPROXIMATE"
    return "EXACT" if exact_seen else "ABSENT"


def source_explicitly_supports_amount(title: str, excerpt: str, amount: Decimal) -> bool:
    """Whether the source contains that number in a price context at all."""
    return source_price_precision(title, excerpt, amount) != "ABSENT"

def evaluate(record: dict) -> GateDecision:
    """Never claim a real paid transaction from text alone.

    REJECT = off-topic/explicitly prohibited/non-public URL.
    HOLD = potentially relevant but missing required verifiable fields.
    REFERENCE_ONLY = public Taiwanese price but not like-for-like evidence.
    READY_FOR_MATCHING = candidate fields present, NOT a pairwise match.
    COMPARABLE can be returned ONLY by compare_with_target after strict matching.
    """
    def d(status, *reasons):
        return GateDecision(
            status, tuple(reasons),
            eligible_for_formal_import=False,  # Strictly never bypass formal QA
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
    # Parser-supplied category/item labels MUST NOT rescue an unrelated page.
    # Require topical evidence in the source title or captured page excerpt.
    raw_subject = " ".join((title, body[:3500]))
    has_source_topic = any(term in raw_subject for term in RENOVATION_TERMS)
    has_unrelated_topic = any(term in raw_subject for term in UNRELATED_TERMS)
    if not has_source_topic:
        return d("REJECT", "SOURCE_TEXT_NOT_RENOVATION")
    if has_unrelated_topic:
        return d("HOLD", "MIXED_UNRELATED_CONTEXT_REVIEW")
    if any(term in raw_subject for term in AD_SIGNALS) and not record.get("amount"):
        return d("HOLD", "PROMOTIONAL_CONTENT_NO_VERIFIABLE_PRICE")

    # The collector must supply the final landing URL when a redirect occurred.
    # Its own network fetcher MUST separately check every hop against SSRF
    # protections; this pure function does not fetch external URLs.
    redirected = record.get("redirected")
    final_url = record.get("resolved_url")
    if redirected is True and not final_url:
        return d("HOLD", "REDIRECT_TARGET_NOT_DOCUMENTED")
    if final_url:
        if not public_source_url(final_url):
            return d("REJECT", "REDIRECT_TO_BLOCKED_OR_NONPUBLIC_URL")
        # A regular successful fetch often records resolved_url == url even
        # when no HTTP redirect occurred. Do not require a fictitious chain.
        if redirected is not True and final_url == url:
            final_url = None
    if final_url:
        # The collector must record and audit EVERY network redirect hop, not
        # merely set redirect_chain_verified=True on an unreviewed final URL.
        chain = record.get("redirect_chain_urls")
        if not isinstance(chain, list) or not 2 <= len(chain) <= 10:
            return d("HOLD", "REDIRECT_CHAIN_UNDOCUMENTED")
        if chain[0] != url or chain[-1] != final_url:
            return d("HOLD", "REDIRECT_CHAIN_ENDPOINT_MISMATCH")
        if any(not public_source_url(hop) for hop in chain):
            return d("REJECT", "REDIRECT_CHAIN_BLOCKED_URL")
        if record.get("redirect_chain_verified") is not True:
            return d("HOLD", "REDIRECT_CHAIN_NOT_VERIFIED")

    locality = str(record.get("locality") or record.get("region") or "")
    if not any(term in locality for term in TAIWAN_TERMS):
        return d("HOLD", "TAIWAN_LOCALITY_UNVERIFIED")

    currency = str(record.get("currency") or "").upper()
    if currency not in ("TWD", "NTD", "NT$", "新臺幣", "新台幣"):
        return d("HOLD", "CURRENCY_UNVERIFIED_OR_FOREIGN")

    amount = parse_twd_amount(record.get("amount"))
    if amount is None:
        return d("HOLD", "NO_VALID_EXPLICIT_PRICE")
    price_precision = source_price_precision(title, body, amount)
    if price_precision == "ABSENT":
        return d("HOLD", "PRICE_NOT_IN_CAPTURED_PUBLIC_SOURCE")
    evidence_type = str(record.get("evidence_type") or "").upper()
    if evidence_type not in TYPES:
        return d("HOLD", "EVIDENCE_TYPE_NOT_CLASSIFIED")

    # Requiring a recorded stage blocks "asked price" being mislabeled as paid.
    phase = str(record.get("price_phase") or "")
    if not phase:
        return d("HOLD", "PRICE_PHASE_NOT_DOCUMENTED")

    # Approximate sources still need provenance classification. Without a
    # recorded evidence type and price phase, even a reference claim is unsafe.
    if price_precision == "APPROXIMATE":
        return d("REFERENCE_ONLY", "SOURCE_PRICE_RANGE_OR_ESTIMATE_NOT_EXACT")

    if evidence_type != "PRIMARY_CASE":
        return d("REFERENCE_ONLY", "BENCHMARK_NOT_AN_INDIVIDUAL_CASE")

    raw_unit = str(record.get("unit") or "").strip()
    spec = str(record.get("spec") or "").strip()
    if not item_name or raw_unit not in UNITS or len(spec) < 2:
        return d("REFERENCE_ONLY", "ITEM_UNIT_OR_SPEC_NOT_COMPARABLE")
    return d("READY_FOR_MATCHING", "STRUCTURED_CANDIDATE_AWAITING_PAIR_MATCH")


def html_source_link(url: str, label: str = "查看原始公開來源") -> str:
    """Render raw public citation in a new tab, never as an internal redirect."""
    if not public_source_url(url):
        raise ValueError("Source URL rejected")
    return '<a href="' + escape(url, quote=True) + '" target="_blank" rel="noopener noreferrer">' + escape(label) + '</a>'



def html_evidence_source_link(record: dict, label: str = "查看原始公開來源") -> str:
    """Only link to an approved public landing URL, not a redirect guess.

    Uses the exact URL that passed the recorded redirect-chain checks.
    Not a replacement for live DNS/HTTP verification by the crawler.
    """
    verdict = evaluate(record)
    if verdict.status in ("REJECT", "HOLD"):
        raise ValueError("Citation source not verified for display")
    landing = record.get("resolved_url") or record.get("url")
    return html_source_link(landing, label)

def _canonical(value: object) -> str:
    """Strict comparison: normalize typographic width/space, not fuzzy synonyms."""
    import unicodedata
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


def compare_with_target(source: dict, customer_quote: dict) -> GateDecision:
    """Only return COMPARABLE for known-identical construction scope.

    Ambiguous differences stay reference-only rather than being silently
    transformed into an exact unit-price benchmark.
    """
    base = evaluate(source)
    if base.status != "READY_FOR_MATCHING":
        return base
    if not isinstance(customer_quote, dict):
        return GateDecision("HOLD", ("NO_CUSTOMER_QUOTE",), False, False)
    required = ("category", "item_name", "unit", "spec", "locality")
    for key in required:
        if not _canonical(source.get(key)) or not _canonical(customer_quote.get(key)):
            return GateDecision("REFERENCE_ONLY", ("PAIR_FIELD_MISSING:" + key,), False, False)
        if _canonical(source[key]) != _canonical(customer_quote[key]):
            return GateDecision("REFERENCE_ONLY", ("PAIR_SPEC_OR_REGION_MISMATCH:" + key,), False, False)
    # Same item text alone does not establish that quoted amounts share a basis.
    # A full job price (e.g. 25 坪的總價) is NOT directly comparable to 每坪單價.
    basis = source.get("price_basis")
    if basis not in ("unit_price", "total_price") or customer_quote.get("price_basis") != basis:
        return GateDecision("REFERENCE_ONLY", ("PRICE_BASIS_MISSING_OR_MISMATCH",), False, False)
    src_tax, quote_tax = source.get("tax_included"), customer_quote.get("tax_included")
    if type(src_tax) is not bool or type(quote_tax) is not bool or src_tax != quote_tax:
        return GateDecision("REFERENCE_ONLY", ("TAX_TREATMENT_MISSING_OR_MISMATCH",), False, False)
    if basis == "total_price":
        try:
            src_qty = Decimal(str(source.get("quantity", "")))
            dst_qty = Decimal(str(customer_quote.get("quantity", "")))
        except (InvalidOperation, ValueError):
            return GateDecision("REFERENCE_ONLY", ("QUANTITY_UNVERIFIED",), False, False)
        if not src_qty.is_finite() or not dst_qty.is_finite() or src_qty <= 0 or dst_qty <= 0 or src_qty != dst_qty:
            return GateDecision("REFERENCE_ONLY", ("TOTAL_PRICE_QUANTITY_MISMATCH",), False, False)

    if (str(customer_quote.get("currency") or "").upper() not in
            ("TWD", "NTD", "NT$", "新臺幣", "新台幣")):
        return GateDecision("HOLD", ("CUSTOMER_CURRENCY_UNVERIFIED",), False, False)
    if parse_twd_amount(customer_quote.get("amount")) is None:
        return GateDecision("HOLD", ("CUSTOMER_PRICE_UNVERIFIED",), False, False)
    return GateDecision("COMPARABLE", ("STRICT_PAIR_FIELDS_MATCH_PAYMENT_UNVERIFIED",),
                        False, True, False)
