"""P3 exact two-statement, fail-closed patch for PUBLIC v1.2.114.

This repairs two small client-side issues: a stale ProMax preferred-section
value and completion-string false positives. It DOES NOT
change payment eligibility, server entitlement verification, report rendering,
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
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import time

PUBLIC_URL = "https://judun.142-93-91-214.sslip.io/"
OLD = "const preferred = tier === 'promax' ? 'report-five-themes' : 'report-price-items';"
NEW = "const preferred = 'report-price-items';"
OLD_COMPLETION = "if (String(data.status || '').includes('完成')) {"
NEW_COMPLETION = ("if (String(data.status || '').includes('完成') "
                  "&& !data.error "
                  "&& !/(?:未完成|未能完成|完成失敗|失敗|取消|中止)/.test(String(data.status || '')) "
                  "&& (!tierMonitor || (task && task.state === 'completed'))) {")
BOUNDED_BYTES = 3_000_000
# v1.2.114 exact public HTML verified on 2026-10-20; fail closed on drift.
OBSERVED_PUBLIC_HTML_SHA256 = "092f952d45b44e1ca5f526d610864a34893f861cc4ee3f587f8fc808ffcbbad8"
CURRENT_PUBLIC_HTML_SHA256 = "734850d449b8d586f75f4af7ec7436a8dae17aa74a9b57f16ceb8031e1bf41fe"


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
    if original.count(OLD_COMPLETION) != 1:
        raise ValueError("EXACT_COMPLETION_STATUS_STATEMENT_NOT_UNIQUE")
    if "window.unlockTier" not in original:
        raise ValueError("LIVE_UNLOCK_API_UNRECOGNIZED")
    changed = original.replace(OLD, NEW, 1).replace(OLD_COMPLETION, NEW_COMPLETION, 1)
    if (changed.replace(NEW, OLD, 1).replace(NEW_COMPLETION, OLD_COMPLETION, 1)
            != original):
        raise ValueError("NOT_EXACTLY_TWO_REVERSIBLE_STATEMENT_CHANGES")
    # Only the intended statements changed (no HTML/CSS/asset/brand edits).
    sentinel_original = original.replace(OLD, "<SENTINEL_A>", 1).replace(OLD_COMPLETION, "<SENTINEL_B>", 1)
    sentinel_changed = changed.replace(NEW, "<SENTINEL_A>", 1).replace(NEW_COMPLETION, "<SENTINEL_B>", 1)
    if sentinel_original != sentinel_changed:
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
        "target": "unlockTier preferred section and negative completion status guard",
        "original_sha256": sha(original_bytes),
        "patched_sha256": sha(new_bytes),
        "statement_replacements": 2,
        "original_length": len(original_bytes),
        "patched_length": len(new_bytes),
        "server_payment_or_entitlement_code_changed": False,
        "completion_status_gate_hardened": True,
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


def review_public_source(data: bytes) -> tuple[bytes, dict, str]:
    """Recognize only independently reviewed exact historical/current bytes."""
    if sha(data) == OBSERVED_PUBLIC_HTML_SHA256:
        return apply_one_statement(data)
    if sha(data) != CURRENT_PUBLIC_HTML_SHA256:
        raise ValueError("PUBLIC_VERSION_SHA_MISMATCH_STOP_AND_REVIEW")
    text = data.decode('utf-8')
    if text.count(NEW) != 1 or text.count(NEW_COMPLETION) != 1 or OLD in text or OLD_COMPLETION in text:
        raise ValueError("DEPLOYED_FIX_SOURCE_GUARD_MISMATCH")
    return data, {
        "schema": "judun.p3.paid-price-source-patch.v1",
        "observed_release": "1.2.120",
        "original_sha256": sha(data), "patched_sha256": sha(data),
        "statement_replacements": 0,
        "live_source_already_contains_fixes": True,
        "completion_status_gate_hardened": True,
        "no_html_css_or_assets_changed": True,
        "production_deployed_by_this_tool": False,
        "actual_payment_e2e_passed_by_this_tool": False,
    }, ""


def historical_regression_source(data: bytes) -> bytes:
    """Reproduce exact v114 fixture; never represent it as current production."""
    if sha(data) == OBSERVED_PUBLIC_HTML_SHA256:
        return data
    review_public_source(data)
    historical = (data.decode('utf-8').replace(NEW, OLD, 1)
                  .replace(NEW_COMPLETION, OLD_COMPLETION, 1)
                  .replace('1.2.120', '1.2.114').encode('utf-8'))
    if sha(historical) != OBSERVED_PUBLIC_HTML_SHA256:
        raise ValueError("HISTORICAL_FIXTURE_SHA_MISMATCH")
    return historical



def write_staging_artifacts(artifacts: list[tuple[Path, bytes]]) -> None:
    """Create staging artifacts exclusively; never overwrite an existing path.

    Roll back only files created by this invocation if a later create fails.
    Preflight Path.exists() alone is insufficient (dangling symlinks/races).
    """
    created: list[Path] = []
    try:
        for target, contents in artifacts:
            if target.suffix not in {".html"}:
                raise ValueError("STAGING_ARTIFACT_MUST_BE_HTML")
            target.parent.mkdir(parents=True, exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                fd = os.open(target, flags, 0o600)
            except FileExistsError as exc:
                raise ValueError("STAGING_PATH_ALREADY_EXISTS") from exc
            created.append(target)
            with os.fdopen(fd, "wb") as stream:
                stream.write(contents)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException:
        for target in reversed(created):
            target.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--public-review", action="store_true")
    mode.add_argument("--public-stage", action="store_true")
    mode.add_argument("--historical-stage", action="store_true")
    mode.add_argument("--input", type=Path)
    parser.add_argument("--original-out", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.public_review and (args.output or args.original_out):
        parser.error("--public-review never writes a complete public homepage")
    if (args.public_stage or args.historical_stage) and (not args.output or not args.original_out):
        parser.error("staging requires distinct original-out and output")
    if args.input and (not args.output or args.original_out):
        parser.error("--input requires --output and forbids --original-out")
    public_mode = args.public_review or args.public_stage or args.historical_stage
    original = fetch_public() if public_mode else args.input.read_bytes()
    if args.historical_stage:
        observed_sha = sha(original)
        original = historical_regression_source(original)
        changed, report, patch = apply_one_statement(original)
        report.update(historical_regression_fixture=True, observed_public_sha256=observed_sha,
                      fixture_is_current_production=False)
    elif public_mode:
        changed, report, patch = review_public_source(original)
    else:
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
        artifacts = ([(args.original_out, original)] if args.original_out else [])
        artifacts.append((args.output, changed))
        write_staging_artifacts(artifacts)
    print("P3_EXACT_SOURCE_PATCH_READY", json.dumps(report, ensure_ascii=False))
    print("NO_PRODUCTION_DEPLOYMENT_OR_PAYMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
