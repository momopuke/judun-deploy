"""Fail-closed P3 patch of an AUTHORITATIVE FastAPI app.py (no deployment).

The public / homepage patch alone is NOT a production source patch. This tool
operates on the original Python app.py containing its embedded JavaScript.
Always pass the current source checksum from a trusted deployment workspace.
Never paste keys, cookies, tokens, or private source into CI or chat.

python3 p3/patch_authoritative_app.py \
  --input /safe/source/app.py \
  --expect-sha256 <sha256-of-that-exact-current-file> \
  --output /safe/staging/app.py

It only writes a new candidate in a distinct path, never executes app.py,
alters deployment, changes a database, or signs/releases an artifact.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re

from patch_paid_preference import OLD, NEW, OLD_COMPLETION, NEW_COMPLETION

MAX_SOURCE_BYTES = 16_000_000
CONTEXT_WINDOW = 16_000
# Historical v1.2.87 archive (known to predate published v1.2.114).
# Compatibility review is not release authority: never stage this as current.
KNOWN_NONCURRENT_SOURCE_SHA256 = frozenset({
    "1c5c2c12bcc956af98e9349fefc35c7d0fb6b47568be50921d4ef27ca335247d",
})


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_match_context(source: str, snippet: str, function: str) -> None:
    if source.count(snippet) != 1:
        raise ValueError("EXPECTED_EXACT_STATEMENT_MISSING_OR_DUPLICATED")
    at = source.index(snippet)
    function_at = source.rfind(function, max(0, at - CONTEXT_WINDOW), at)
    if function_at < 0:
        raise ValueError("STATEMENT_NOT_IN_EXPECTED_JS_FUNCTION")
    # Stop if a distinct JS function declaration intervenes between the
    # expected entry and the target statement. This is a conservative check,
    # not a replacement for authoritative-source code review.
    between = source[function_at + len(function):at]
    if re.search(r"\b(?:async\s+)?function\s+[A-Za-z_$]\w*\s*\(", between):
        raise ValueError("FUNCTION_CONTEXT_HAS_CHANGED")


def apply_app_patch(raw: bytes, expected_sha256: str) -> tuple[bytes, dict]:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256 or ""):
        raise ValueError("EXPECTED_SOURCE_SHA256_REQUIRED")
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("INVALID_AUTHORITATIVE_SOURCE_SIZE")
    before_hash = sha256(raw)
    if before_hash != expected_sha256.lower():
        raise ValueError("SOURCE_SHA256_MISMATCH_STOP")
    if before_hash in KNOWN_NONCURRENT_SOURCE_SHA256:
        raise ValueError("KNOWN_ARCHIVED_SOURCE_NOT_PRODUCTION_CURRENT")
    try:
        original = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("SOURCE_MUST_BE_UTF8") from exc
    # Verify this is actually an app source, not a live homepage or release zip.
    if ("FastAPI(" not in original or
        '@app.get("/status/{job_id}")' not in original or
        "function checkMicroStatus(" not in original or
        "window.unlockTier" not in original):
        raise ValueError("SOURCE_NOT_EXPECTED_JUDUN_FASTAPI_APP")
    # Check Python syntax AND AST ownership. Substring-based triple-quote
    # scanning can be fooled by comments or an unrelated Python string.
    try:
        module = ast.parse(original, filename="<authoritative-app-before>")
        compile(original, "<authoritative-app-before>", "exec")
    except SyntaxError as exc:
        raise ValueError("AUTHORITATIVE_PYTHON_INVALID_BEFORE_PATCH") from exc
    assignments = [
        stmt for stmt in module.body
        if ((isinstance(stmt, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == "GLOBAL_JS"
                     for t in stmt.targets))
            or (isinstance(stmt, ast.AnnAssign)
                and isinstance(stmt.target, ast.Name)
                and stmt.target.id == "GLOBAL_JS"))
    ]
    if len(assignments) != 1:
        raise ValueError("EXPECTED_SINGLE_MODULE_GLOBAL_JS_ASSIGNMENT")
    literal = assignments[0].value
    if not (isinstance(literal, ast.Constant)
            and isinstance(literal.value, str)):
        raise ValueError("GLOBAL_JS_MUST_BE_LITERAL")
    js = literal.value
    # Require both exact statements in the one module-level JS literal;
    # reject a decoy string elsewhere even if the source hashes correctly.
    if (js.count(OLD) != 1 or js.count(OLD_COMPLETION) != 1
            or "window.unlockTier" not in js
            or "function checkMicroStatus(" not in js):
        raise ValueError("PATCH_TARGET_OUTSIDE_AUTHORITATIVE_GLOBAL_JS")
    _check_match_context(js, OLD, "window.unlockTier")
    _check_match_context(js, OLD_COMPLETION, "function checkMicroStatus(")
    after = original.replace(OLD, NEW, 1).replace(
        OLD_COMPLETION, NEW_COMPLETION, 1
    )
    if (after.replace(NEW, OLD, 1).replace(NEW_COMPLETION, OLD_COMPLETION, 1)
            != original):
        raise ValueError("PATCH_NOT_EXACTLY_REVERSIBLE")
    if (after.replace(NEW, "<A>", 1).replace(NEW_COMPLETION, "<B>", 1) !=
            original.replace(OLD, "<A>", 1).replace(OLD_COMPLETION, "<B>", 1)):
        raise ValueError("UNEXPECTED_CHANGES")
    try:
        compile(after, "<authoritative-app-after>", "exec")
    except SyntaxError as exc:
        raise ValueError("PATCHED_PYTHON_INVALID") from exc
    encoded = after.encode("utf-8")
    if raw != original.encode("utf-8"):
        raise ValueError("SOURCE_ENCODING_REWRITE_NOT_ALLOWED")
    return encoded, {
        "schema": "judun.p3.authoritative-app-surgical-patch.v1",
        "source_sha256": before_hash,
        "candidate_sha256": sha256(encoded),
        "source_bytes": len(raw),
        "candidate_bytes": len(encoded),
        "replacements": 2,
        "python_syntax": "PASS_BEFORE_AND_AFTER",
        "global_js_ast_verified": True,
        "fastapi_route_preserved": True,
        "production_deployed": False,
        "requires_original_signing_and_e2e": True,
    }


def write_staging(input_path: Path, output_path: Path, raw: bytes) -> None:
    # Do not follow output symlinks, do not overwrite any existing artifact.
    if input_path.resolve() == output_path.resolve():
        raise ValueError("REFUSE_TO_OVERWRITE_SOURCE")
    if output_path.suffix != ".py":
        raise ValueError("STAGING_OUTPUT_MUST_BE_PY")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(output_path, flags, 0o600)
    except FileExistsError as exc:
        raise ValueError("REFUSE_TO_OVERWRITE_EXISTING_STAGING") from exc
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    except BaseException:
        output_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-sha256", required=True)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("input and output cannot be the same")
    patched, result = apply_app_patch(
        args.input.read_bytes(), args.expect_sha256
    )
    write_staging(args.input, args.output, patched)
    print("P3_AUTHORITATIVE_APP_STAGING_READY", json.dumps(result))
    print("NO_DEPLOYMENT_OR_RELEASE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
