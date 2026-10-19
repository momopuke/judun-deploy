"""Read-only, bounded live health audit for evidence trust. No admin or user data."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import re
import urllib.error
import urllib.request

BASE = "https://judun.142-93-91-214.sslip.io"
TARGETS = (
    ("/health/build", "build"),
    ("/health/source-exclusion", "exclusion"),
    ("/health/data-expansion", "expansion"),
    ("/trust-method", "method"),
)
def fetch(path):
    req = urllib.request.Request(BASE + path, headers={
        "Cache-Control": "no-cache", "User-Agent": "JUDUN-evidence-audit/1.0",
        "Accept": "application/json,text/html;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=20) as response:
        data = response.read(800_000)
        return response.status, response.headers.get("Content-Type", ""), data

def main():
    report = {"schema": "judun.live-evidence-health.v1",
              "checked_at_utc": datetime.now(timezone.utc).isoformat(), "checks": {}}
    errors = []
    for path, key in TARGETS:
        try:
            status, mime, raw = fetch(path)
            result = {"status": status, "bytes": len(raw)}
            if "application/json" in mime or path.startswith("/health/"):
                v = json.loads(raw.decode("utf-8"))
                if not isinstance(v, dict):
                    raise ValueError("health response is not object")
                result["available_fields"] = sorted(list(v.keys()))[:35]
                if key == "build":
                    result["version"] = str(v.get("version") or v.get("display_version") or "")
                    result["artifact_id"] = str(v.get("artifact_id") or "")
                    if not re.fullmatch(r"v?\d+\.\d+\.\d+", result["version"]):
                        errors.append("build version format invalid")
                elif key == "exclusion":
                    for k in ("remaining_cases", "remaining_records"):
                        if k not in v:
                            errors.append("exclusion missing " + k)
                        else:
                            result[k] = v[k]
                            if v[k] != 0:
                                errors.append("source exclusion failure: " + k)
                elif key == "expansion":
                    for field in ("status","running","auto_goal_status","version","display_version",
                                  "resilience_policy_version","phase","last_error","updated_at"):
                        if field in v:
                            # Do not leak internal error descriptions or paths.
                            result[field] = "<present>" if field == "last_error" else v[field]
            else:
                t = raw.decode("utf-8", "replace")
                result["brand_present"] = "居盾" in t
                if not result["brand_present"]:
                    errors.append("public trust-method missing brand")
            report["checks"][key] = result
        except Exception as exc:
            report["checks"][key] = {"error_type": type(exc).__name__}
            errors.append(key + ": " + type(exc).__name__)
    report["errors"] = errors
    Path("p1/results").mkdir(exist_ok=True, parents=True)
    Path("p1/results/public-health.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("EVIDENCE_LIVE_HEALTH", json.dumps(report, ensure_ascii=False))
    if errors:
        raise SystemExit("PUBLIC_EVIDENCE_HEALTH_FAIL " + ", ".join(errors))
    print("PUBLIC_EVIDENCE_HEALTH_PASS")

if __name__ == "__main__":
    main()
