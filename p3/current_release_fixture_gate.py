"""Fail-closed routing of *historical* browser fixtures after a live upgrade.

Never edits a live server, writes a release or authorizes payment. A newer
public site must show both repaired client-side statements before the old
v1.2.114/v1.2.120 SHA-pinned regression is called obsolete.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from patch_paid_preference import (
    CURRENT_PUBLIC_HTML_SHA256,
    OBSERVED_PUBLIC_HTML_SHA256,
    NEW,
    NEW_COMPLETION,
    OLD,
    OLD_COMPLETION,
)
from production_readiness import public_get, public_json

PINNED = {
    "1.2.114": OBSERVED_PUBLIC_HTML_SHA256,
    "1.2.120": "734850d449b8d586f75f4af7ec7436a8dae17aa74a9b57f16ceb8031e1bf41fe",
    "1.2.124": "22c00b3b7ea5794c09b54a19c2e809472a57af1847832e2bd9a565e04058b082",
    "1.2.125": CURRENT_PUBLIC_HTML_SHA256,
}
LAST_PINNED_VERSION = (1, 2, 120)


def assess(build_result: dict, homepage_result: dict) -> dict:
    """Decide whether the legacy regression is valid, obsolete or unsafe.

    A positive SKIP is never a release GO: it only means the old fixture is
    not the current site's source. A missing/malformed response hard-fails.
    """
    if build_result.get("status") != "OK" or not isinstance(build_result.get("data"), dict):
        return {"decision": "BLOCK", "reason": "LIVE_BUILD_UNVERIFIED"}
    data = build_result["data"]
    version = data.get("display_version") or data.get("version")
    if not isinstance(version, str):
        return {"decision": "BLOCK", "reason": "LIVE_VERSION_INVALID"}
    version = version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        return {"decision": "BLOCK", "reason": "LIVE_VERSION_INVALID"}
    artifact = data.get("artifact_id")
    if not isinstance(artifact, str) or not artifact.startswith(f"JUDUN-{version}-"):
        return {"decision": "BLOCK", "reason": "ARTIFACT_VERSION_MISMATCH"}
    if homepage_result.get("status") != "OK" or not isinstance(homepage_result.get("content"), bytes):
        return {"decision": "BLOCK", "reason": "PUBLIC_HOMEPAGE_UNVERIFIED"}
    raw = homepage_result["content"]
    if len(raw) > 1_000_000:
        return {"decision": "BLOCK", "reason": "PUBLIC_HOMEPAGE_OVERSIZED"}
    digest = hashlib.sha256(raw).hexdigest()
    if version in PINNED:
        if digest != PINNED[version]:
            return {"decision": "BLOCK", "reason": "PINNED_RELEASE_SHA_DRIFT"}
        return {"decision": "RUN", "reason": "EXACT_PINNED_HISTORICAL_FIXTURE"}
    if tuple(map(int, version.split("."))) <= LAST_PINNED_VERSION:
        return {"decision": "BLOCK", "reason": "UNKNOWN_OLDER_VERSION"}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"decision": "BLOCK", "reason": "PUBLIC_HOMEPAGE_NOT_UTF8"}
    if (text.count(NEW) != 1 or text.count(NEW_COMPLETION) != 1
            or OLD in text or OLD_COMPLETION in text):
        return {"decision": "BLOCK", "reason": "NEWER_LIVE_GUARDS_NOT_PROVEN"}
    return {"decision": "SKIP", "reason": "SUPERSEDED_PINNED_FIXTURE_WITH_GUARDS",
            "live_version": version}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    decision = assess(public_json("/health/build"), public_get("/"))
    print("P3_HISTORICAL_FIXTURE_GATE", json.dumps(decision, sort_keys=True))
    if decision["decision"] == "BLOCK":
        # Do not weaken the SHA pin to make CI artificially green.
        return 1
    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as output:
            output.write(
                "run_pinned_fixture=" + ("true" if decision["decision"] == "RUN" else "false") + "\n"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
