"""Public, read-only probe of the existing JUDUN HTTPS deployment receiver.

No upload, authorization attempt, personal data, or release action.  This
cannot reveal whether the VPS systemd pull-agent is installed or enabled.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

RECEIVER = "https://deploy-judun.142-93-91-214.sslip.io"
ENDPOINTS = ("/health", "/version")
MAX_BYTES = 16384
MAX_SECONDS = 12


class NeverRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def classify(path: str, opener=None) -> dict:
    """Classify only HTTP transport/shape; never publish raw server output."""
    if path not in ENDPOINTS:
        raise ValueError("READ_ONLY_ENDPOINT_NOT_ALLOWED")
    req = Request(
        RECEIVER + path,
        headers={"Accept": "application/json, text/plain", "Cache-Control": "no-cache",
                 "User-Agent": "Judun-P3-Receiver-Public-Probe/1"},
        method="GET",
    )
    client = opener if opener is not None else build_opener(NeverRedirect())
    try:
        with client.open(req, timeout=MAX_SECONDS) as response:
            code = response.status
            final_url = response.geturl()
            raw = response.read(MAX_BYTES + 1)
            if final_url != RECEIVER + path:
                return {"state": "UNEXPECTED_DESTINATION", "http_status": code}
            if len(raw) > MAX_BYTES:
                return {"state": "OVERSIZED_PUBLIC_RESPONSE", "http_status": code}
            if code != 200:
                return {"state": "HTTP_OTHER", "http_status": code}
            # Keep all response content private. A successful health endpoint
            # shows only endpoint liveness; not signed-agent health.
            return {"state": "HTTP_200", "http_status": 200, "body_received": bool(raw)}
    except HTTPError as error:
        code = error.code
        if code in (301, 302, 303, 307, 308):
            state = "REDIRECT_NOT_FOLLOWED"
        elif code in (401, 403):
            state = "AUTH_REQUIRED"
        elif code == 404:
            state = "NOT_FOUND"
        elif code in (502, 503, 504):
            state = "UPSTREAM_UNAVAILABLE"
        else:
            state = "HTTP_ERROR"
        return {"state": state, "http_status": code}
    except (URLError, TimeoutError, OSError, ValueError):
        return {"state": "TRANSPORT_NOT_VERIFIED"}


def assess(results: dict[str, dict]) -> str:
    if all(results.get(path, {}).get("state") == "HTTP_200" for path in ENDPOINTS):
        return "PUBLIC_RECEIVER_RESPONDS_AGENT_UNKNOWN"
    if any(results.get(path, {}).get("state") == "HTTP_200" for path in ENDPOINTS):
        return "RECEIVER_PARTIALLY_REACHABLE"
    return "RECEIVER_NOT_PUBLICLY_VERIFIED"


def main() -> int:
    results = {path: classify(path) for path in ENDPOINTS}
    out = {
        "schema": "judun.p3.readonly-receiver-probe.v1",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "receiver": "original_judun_https_receiver",
        "checks": results,
        "decision": assess(results),
        "only_get_requests": True,
        "vps_agent_status": "NOT_OBSERVABLE_FROM_PUBLIC_HTTPS",
        "deployed_or_modified": False,
        "production_safe_to_release": False,
    }
    path = Path(__file__).resolve().parent / "results" / "receiver-readiness.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("P3_READONLY_RECEIVER_PROBE", json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
