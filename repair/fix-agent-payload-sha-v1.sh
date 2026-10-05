#!/usr/bin/env bash
set -euo pipefail

AG="/opt/judun-autodeploy/agent.sh"
REPO="momopuke/judun-deploy"
BRANCH="main"
BASE="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
STAMP="$(date +%Y%m%d_%H%M%S)"
TMP="$(mktemp -d /tmp/judun-agent-payloadsha.XXXXXX)"
BK="${AG}.pre-payloadsha-${STAMP}"
trap 'rm -rf "$TMP"' EXIT

echo "=============================================================="
echo "JUDUN AutoDeploy Agent - Payload SHA Contract Repair"
echo "=============================================================="

if [[ ! -f "$AG" ]]; then
  echo "[FAIL] Agent not found: $AG"
  exit 1
fi

echo "[1/6] Proving the current release SHA contract..."
curl -fsS --connect-timeout 8 --max-time 30 -H "Cache-Control: no-cache"   "$BASE/channel/stable.json?cb=$STAMP" -o "$TMP/stable.json"

PAYLOAD_PATH="$(python3 - "$TMP/stable.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"))
print(m["payload_path"])
PY
)"
EXPECTED_SHA="$(python3 - "$TMP/stable.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"))
print(m["payload_sha256"].lower())
PY
)"
TARGET_ARTIFACT="$(python3 - "$TMP/stable.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1],encoding="utf-8"))
print(m["target_artifact_id"])
PY
)"

curl -fsS --connect-timeout 8 --max-time 120 -H "Cache-Control: no-cache"   "$BASE/$PAYLOAD_PATH?cb=$STAMP" -o "$TMP/payload.cms.b64"

TEXT_SHA="$(sha256sum "$TMP/payload.cms.b64" | awk '{print $1}')"
if ! base64 -d "$TMP/payload.cms.b64" > "$TMP/payload.cms"; then
  echo "[FAIL] Release payload is not valid base64."
  exit 1
fi
RAW_SHA="$(sha256sum "$TMP/payload.cms" | awk '{print $1}')"

echo "      manifest expected : $EXPECTED_SHA"
echo "      downloaded .b64   : $TEXT_SHA"
echo "      decoded CMS       : $RAW_SHA"

if [[ "$RAW_SHA" != "$EXPECTED_SHA" ]]; then
  echo "[FAIL] GitHub release itself is inconsistent; agent will NOT be modified."
  exit 1
fi
if [[ "$TEXT_SHA" == "$EXPECTED_SHA" ]]; then
  echo "[INFO] Transport-file SHA already matches manifest; this repair is not needed."
  exit 0
fi
echo "[OK] Confirmed: manifest hashes decoded CMS, not the base64 transport text."

echo "[2/6] Backing up current agent..."
cp -a "$AG" "$BK"
echo "[OK] Backup: $BK"

echo "[3/6] Applying the minimal hash-input repair..."
python3 - "$AG" <<'PY'
from pathlib import Path
import sys

p=Path(sys.argv[1])
s=p.read_text(encoding="utf-8")
marker="# JUDUN_PAYLOAD_SHA_DECODED_CMS_V1"

if marker in s:
    print("[OK] Payload SHA repair already installed.")
    raise SystemExit(0)

pairs=[
    ('sha256sum "$PAYLOAD_B64"', 'sha256sum <(base64 -d "$PAYLOAD_B64")'),
    ('sha256sum "${PAYLOAD_B64}"', 'sha256sum <(base64 -d "${PAYLOAD_B64}")'),
]
hits=sum(s.count(a) for a,_ in pairs)
if hits != 1:
    raise SystemExit(f"[FAIL] Expected exactly one PAYLOAD_B64 sha256sum site; found {hits}. No change made.")

for a,b in pairs:
    if a in s:
        s=s.replace(a,b,1)
        break

anchor='BASE_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}"'
if anchor in s:
    s=s.replace(anchor, anchor+"\n"+marker, 1)
else:
    s=marker+"\n"+s

p.write_text(s,encoding="utf-8")
print("[OK] Agent now hashes decoded CMS bytes, matching the signed manifest contract.")
PY

if ! bash -n "$AG"; then
  cp -a "$BK" "$AG"
  echo "[FAIL] Agent syntax check failed; backup restored."
  exit 1
fi
echo "[OK] Agent syntax PASS"

echo "[4/6] Forcing one AutoDeploy run..."
systemctl reset-failed judun-autodeploy.service || true
if ! systemctl start judun-autodeploy.service; then
  echo "[WARN] AutoDeploy returned failure. Showing the last log lines:"
  journalctl -u judun-autodeploy.service -n 50 --no-pager || true
  exit 2
fi

echo "[5/6] Verifying local runtime..."
OK=0
for i in $(seq 1 18); do
  BUILD="$(curl -fsS --max-time 10 http://127.0.0.1:8000/health/build 2>/dev/null || true)"
  if [[ -n "$BUILD" ]]; then
    echo "$BUILD"
    ART="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("artifact_id",""))' <<<"$BUILD" 2>/dev/null || true)"
    if [[ "$ART" == "$TARGET_ARTIFACT" ]]; then
      OK=1
      break
    fi
  fi
  sleep 5
done
if [[ "$OK" != "1" ]]; then
  echo "[FAIL] Agent repair applied, but runtime did not converge to $TARGET_ARTIFACT."
  journalctl -u judun-autodeploy.service -n 80 --no-pager || true
  exit 3
fi
echo "[OK] Local runtime converged to $TARGET_ARTIFACT"

echo "[6/6] Verifying public runtime..."
curl -4 --http1.1 -kfsS --connect-timeout 5 --max-time 15   "https://judun.142-93-91-214.sslip.io/health/build?probe=$(date +%s)" || true
echo
systemctl enable --now judun-autodeploy.timer >/dev/null 2>&1 || true
echo "[OK] Repair complete; AutoDeploy timer is enabled."
