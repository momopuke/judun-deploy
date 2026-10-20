"""P3 one-statement, fail-closed patch for the PUBLIC v1.2.114 unlock entry.

This repairs only the stale ProMax preferred-section value. It DOES NOT
change payment eligibility, entitlement verification, report rendering,
production files or signed releases.

Usage:
  python3 p3/patch_paid_preference.py --public-review
  python3 p3/patch_paid_preference.py --input existing_authoritative_index.html --output staging/index.html
  python3 p3/patch_paid_preference.py --public-stage --original-out /tmp/live.html --output /tmp/patched.html

The first command retrieves publicly served HTML solely to generate a small
reviewable patch + metadata; the second requires a locally available authorized
source and writes a new STAGING file, never overwrites the input.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import time

PUBLIC_URL = "https://judun.142-93-91-214.sslip.io/"
OLD = "const preferred = tier === 'promax' ? 'report-five-themes' : 'report-price-items';"
NEW = "const preferred = 'report-price-items';"
BOUNDED_BYTES = 3_000_000
# v1.2.114 exact public HTML verified on 2026-10-20; fail closed on drift.
OBSERVED_PUBLIC_HTML_SHA256 = "092f952d45b44e1ca5f526d610864a34893f861cc4ee3f587f8fc808ffcbbad8"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def apply_one_statement(data: bytes) -> tuple[bytes, dict, str]:
    if len(data) > BOUNDED_BYTES:
        raise ValueError("SOURCE_TOO_LARGE")
    try:
        original = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("SOURCE_NOT_UTF8") from error
    # A unique exact existing source assignment is mandatory. No best-effort
    # substring replacements, script injection, regex rewrite or fallback.
    if original.count(OLD) != 1:
        raise ValueError("EXACT_UNLOCK_STATEMENT_NOT_UNIQUE")
    if "window.unlockTier" not in original:
        raise ValueError("LIVE_UNLOCK_API_UNRECOGNIZED")
    changed = original.replace(OLD, NEW, 1)
    if changed.replace(NEW, OLD, 1) != original:
        raise ValueError("NOT_A_SINGLE_REVERSIBLE_STATEMENT_CHANGE")
    # Only the intended statement changed (no HTML/CSS/asset/brand edits).
    if original.replace(OLD, "<SENTINEL>", 1) != changed.replace(NEW, "<SENTINEL>", 1):
        raise ValueError("UNINTENDED_CONTENT_MODIFICATION")
    original_bytes, new_bytes = original.encode("utf-8"), changed.encode("utf-8")
    assert original_bytes == data
    lines = original.splitlines(keepends=True)
    new_lines = changed.splitlines(keepends=True)
    diff = "".join(difflib.unified_diff(
        lines, new_lines, fromfile="a/authoritative-homepage.html",
        tofile="b/authoritative-homepage.html", n=0,
    ))
    # Limit published output even if someone moved all JS into one giant line.
    if len(diff) > 5_000:
        raise ValueError("UNSAFE_PATCH_LINE_TOO_LONG")
    result = {
        "schema": "judun.p3.paid-price-source-patch.v1",
        "target": "unlockTier: stale ProMax preferred section only",
        "original_sha256": sha(original_bytes),
        "patched_sha256": sha(new_bytes),
        "statement_replacements": 1,
        "original_length": len(original_bytes),
        "patched_length": len(new_bytes),
        "no_payment_or_entitlement_code_changed": True,
        "no_html_css_or_assets_changed": True,
        "production_deployed": False,
        "actual_payment_e2e_passed": False,
        "requires_authorized_source_builder": True,
    }
    return new_bytes, result, diff


def fetch_public() -> bytes:
    """Read-only GET retries ONLY transient transport errors, max 3 attempts.

    A successful response with mismatched SHA/version is NOT retried or silently
    accepted; apply_one_statement() remains a fail-closed source patch.
    """
    request = Request(PUBLIC_URL, headers={
        "User-Agent": "Judun-P3-ReadOnly-ExactSourceReview/1",
        "Accept": "text/html",
        "Cache-Control": "no-cache",
    }, method="GET")
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=22) as response:
                if response.status != 200 or response.geturl().rstrip("/") != PUBLIC_URL.rstrip("/"):
                    raise ValueError("UNEXPECTED_PUBLIC_SOURCE_RESPONSE")
                if "text/html" not in response.headers.get("Content-Type", ""):
                    raise ValueError("PUBLIC_SOURCE_NOT_HTML")
                data = response.read(BOUNDED_BYTES + 1)
            if len(data) > BOUNDED_BYTES:
                raise ValueError("SOURCE_TOO_LARGE")
            return data
        except (TimeoutError, URLError, OSError) as error:
            # No retries for unexpected HTTP status and other factual content
            # mismatches; these must be diagnosed rather than hidden.
            if isinstance(error, HTTPError):
                raise ValueError("PUBLIC_SOURCE_HTTP_ERROR") from error
            last_error = error
            if attempt < 2:
                print("P3_PUBLIC_SOURCE_TRANSIENT_READ_RETRY", attempt + 1, flush=True)
                time.sleep(2 * (attempt + 1))
    raise RuntimeError("PUBLIC_SOURCE_UNAVAILABLE_AFTER_3_READ_ATTEMPTS") from last_error


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--public-review", action="store_true")
    mode.add_argument("--public-stage", action="store_true")
    mode.add_argument("--input", type=Path)
    parser.add_argument("--original-out", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.public_review and (args.output or args.original_out):
        parser.error("--public-review never writes a complete public homepage")
    if args.public_stage and (not args.output or not args.original_out):
        parser.error("--public-stage requires distinct original-out and output")
    if args.input and (not args.output or args.original_out):
        parser.error("--input requires --output and forbids --original-out")
    original = fetch_public() if (args.public_review or args.public_stage) else args.input.read_bytes()
    if (args.public_review or args.public_stage) and sha(original) != OBSERVED_PUBLIC_HTML_SHA256:
        raise ValueError("PUBLIC_VERSION_SHA_MISMATCH_STOP_AND_REVIEW")
    changed, report, patch = apply_one_statement(original)
    review_dir = Path("p3/results")
    review_dir.mkdir(parents=True, exist_ok=True)
    (review_dir / "paid-preference-exact.patch").write_text(patch, encoding="utf-8")
    (review_dir / "paid-preference-review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if args.output:
        # Never replace original, other existing artifacts, or production file.
        paths = [args.output]
        if args.original_out:
            paths.append(args.original_out)
        if len({p.resolve() for p in paths}) != len(paths):
            raise ValueError("STAGING_SOURCE_OUTPUT_PATH_COLLISION")
        if args.input and any(p.resolve() == args.input.resolve() for p in paths):
            raise ValueError("OVERWRITING_SOURCE_FORBIDDEN")
        if any(p.exists() for p in paths):
            raise ValueError("STAGING_PATH_ALREADY_EXISTS")
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
        if args.original_out:
            args.original_out.write_bytes(original)
        args.output.write_bytes(changed)
    print("P3_EXACT_SOURCE_PATCH_READY", json.dumps(report, ensure_ascii=False))
    print("NO_PRODUCTION_DEPLOYMENT_OR_PAYMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
