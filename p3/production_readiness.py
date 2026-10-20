"""P3 production GO/NO-GO audit: read-only, never deploy or unlock.

This probe determines only what the PUBLIC production endpoints can prove.
The candidate repository holds encrypted releases, not editable production
source. Passing HTTP checks cannot authorize a new release or real payments.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE = "https://judun.142-93-91-214.sslip.io"
MAX_RESPONSE_BYTES = 1_000_000
TIMEOUT_SECONDS = 5


class PublicHome(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = set()
        self.duplicate_ids = 0
        self.text_parts = []

    def handle_starttag(self, tag, attributes):
        values = dict(attributes)
        identifier = values.get("id")
        if identifier:
            if identifier in self.ids:
                self.duplicate_ids += 1
            self.ids.add(identifier)

    def handle_data(self, data):
        if len(self.text_parts) < 12000:
            self.text_parts.append(data)


def public_get(path: str) -> dict:
    """One bounded HTTPS GET; log no response bodies or private exception data."""
    request = Request(BASE + path, headers={
        "User-Agent": "Judun-P3-readonly-integration-audit/1",
        "Cache-Control": "no-cache",
    }, method="GET")
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                return {"status": "OVERSIZED_RESPONSE"}
            if response.status != 200:
                return {"status": "HTTP_NOT_OK", "http_status": response.status}
            return {"status": "OK", "content": raw}
    except (HTTPError, URLError, OSError, TimeoutError, ValueError):
        return {"status": "NOT_VERIFIED"}


def public_json(path: str) -> dict:
    result = public_get(path)
    if result["status"] != "OK":
        return {"status": result["status"]}
    try:
        data = json.loads(result["content"].decode("utf-8"))
        if not isinstance(data, dict):
            return {"status": "INVALID_SHAPE"}
        return {"status": "OK", "data": data}
    except (UnicodeError, ValueError):
        return {"status": "INVALID_JSON"}


def assess_published_channel(channel: dict, live_artifact: str | None) -> str:
    """A counterfactual channel identity check; NOT proof agent ran.

    A stale stable channel can never apply to a later live artifact under
    original AutoDeploy's fail-closed base-artifact equality check.
    """
    if not live_artifact:
        return "LIVE_IDENTITY_NOT_VERIFIED"
    if channel.get("target_artifact_id") == live_artifact:
        return "TARGET_ALREADY_LIVE_IF_AGENT_ACTIVE"
    if channel.get("base_artifact_id") == live_artifact:
        return "BASE_MATCH_IF_AGENT_ACTIVE"
    return "BASE_MISMATCH_IF_AGENT_ACTIVE"



def audit() -> dict:
    channel = json.loads((PROJECT_ROOT / "channel/stable.json").read_text("utf-8"))
    historical = json.loads(
        (PROJECT_ROOT / "assets/v1.2.114-expansion-resilience-verification-20261017.json")
        .read_text("utf-8")
    )
    build_result = public_json("/health/build")
    live_version = None
    live_artifact = None
    live_build_identity = "NOT_VERIFIED"
    if build_result["status"] == "OK":
        data = build_result["data"]
        version = str(data.get("display_version") or data.get("version") or "").lstrip("v")
        artifact = data.get("artifact_id")
        if re.fullmatch(r"\d+\.\d+\.\d+", version) and isinstance(artifact, str) and re.fullmatch(r"JUDUN-[A-Za-z0-9._-]{1,100}", artifact):
            live_version = version
            live_artifact = artifact
            live_build_identity = "OBSERVED"
    integrity = public_json("/health/artifact?deep=true")
    integrity_status = "NOT_VERIFIED"
    if integrity["status"] == "OK":
        data = integrity["data"]
        if (live_artifact is not None and data.get("status") == "ok"
                and data.get("artifact_id") == live_artifact
                and type(data.get("mismatch_count")) is int
                and data["mismatch_count"] == 0
                and type(data.get("files_verified")) is int
                and data["files_verified"] >= 79
                and (data.get("manifest_file_count") is None
                     or data.get("manifest_file_count") == data["files_verified"])):
            integrity_status = "PASS"
        else:
            integrity_status = "MISMATCH_OR_UNVERIFIED"

    home = public_get("/")
    homepage = {"status": "NOT_VERIFIED", "approved_visual_unchanged": "NOT_VERIFIED"}
    pricing_mode = "NOT_VERIFIED"
    if home["status"] == "OK":
        try:
            text = home["content"].decode("utf-8")
            parsed = PublicHome()
            parsed.feed(text)
            value = "".join(parsed.text_parts)
            homepage["status"] = (
                "ENTRY_IDS_PRESENT" if {"fileInput", "dataConsentInput", "submitBtn"}.issubset(parsed.ids)
                and parsed.duplicate_ids == 0 and "居盾" in value
                else "ENTRY_MISSING_OR_DUPLICATE_ID"
            )
            # HTML inspection is NOT a pixel/brand review; do not overclaim.
            pricing_mode = (
                "PUBLIC_TEST_MODE_NOTICE_PRESENT" if "目前為付費功能測試模式" in value
                else "NOT_VERIFIED_BY_PUBLIC_HTML"
            )
        except (UnicodeError, ValueError):
            homepage["status"] = "INVALID_HTML"

    exclusion = public_json("/health/source-exclusion")
    exclusion_status = "NOT_VERIFIED"
    if exclusion["status"] == "OK":
        data = exclusion["data"]
        if data.get("remaining_cases") == 0 and data.get("remaining_records") == 0:
            exclusion_status = "ZERO_REMAINING_REPORTED"
        else:
            exclusion_status = "EXCLUSIONS_UNRESOLVED_OR_UNVERIFIED"

    status_result = {
        "schema": "judun.p3.production-readiness.v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "purpose": "READ_ONLY_INTEGRATION_BLOCKER_DIAGNOSIS",
        "production_was_modified": False,
        "payment_or_upload_performed": False,
        "public_live": {
            "build_identity": live_build_identity,
            "display_version": live_version,
            "artifact_id": live_artifact,
            "deep_integrity": integrity_status,
            "homepage_entry": homepage["status"],
            "approved_visual_unchanged": "NOT_VERIFIED",
            "payment": pricing_mode,
            "source_exclusion": exclusion_status,
        },
        "signed_channel": {
            "expected_display_version": channel.get("expected_display_version"),
            "base_artifact_id": channel.get("base_artifact_id"),
            "target_artifact_id": channel.get("target_artifact_id"),
            "counterfactual_agent_base_check": assess_published_channel(
                channel, live_artifact
            ),
            "agent_actual_service_status": "UNKNOWN",
            "release_id": channel.get("release_id"),
            "note": "Stable channel version need not equal currently deployed production; do not roll back.",
            "matches_observed_live_version": (
                live_version is not None
                and str(channel.get("expected_display_version") or "").lstrip("v") == live_version
            ),
        },
        "historical_build_attestation": {
            "version": historical.get("version"),
            "artifact_id": historical.get("artifact_id"),
            "same_as_live": (
                live_artifact is not None and historical.get("artifact_id") == live_artifact
            ),
            "not_live_proof": True,
        },
        "source_in_this_git_repository": "ENCRYPTED_DEPLOYMENT_ASSETS_ONLY",
        "editable_authoritative_source": "NOT_AVAILABLE_IN_THIS_WORKSPACE",
        "existing_formal_qa_schema": "NOT_VERIFIED",
        "authorized_release_signing": "NOT_AVAILABLE_IN_THIS_WORKSPACE",
        "real_customer_quote_e2e": "NOT_RUN",
        "real_payment_e2e": "NOT_RUN",
        "real_report_pdf_e2e": "NOT_RUN",
        "decision": "BLOCKED_FOR_PRODUCTION_INTEGRATION",
        "required_next_action": "Use the existing trusted production source builder and signed-deployment environment; verify actual schema, payment and report/PDF flows before a single signed release.",
    }
    return status_result


def main() -> int:
    result = audit()
    out = PROJECT_ROOT / "p3/results/production-readiness.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Public metadata only, no cookies, response HTML, raw exception or DB.
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "decision": result["decision"],
        "observed_build": result["public_live"]["display_version"],
        "observed_artifact_id": result["public_live"]["artifact_id"],
        "integrity": result["public_live"]["deep_integrity"],
        "pricing_mode": result["public_live"]["payment"],
        "source_authority": result["editable_authoritative_source"],
    }
    print("P3_RELEASE_GATE", json.dumps(summary, ensure_ascii=False))
    print("NO_DEPLOYMENT_OR_PAYMENT_PERFORMED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
