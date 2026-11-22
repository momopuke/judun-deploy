#!/usr/bin/env bash
# One authorized local-only install. Does NOT change nginx/Caddy or release.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'STOP: ROOT_REQUIRED'; exit 2; }
[[ $# -eq 3 ]] || { echo 'STOP: EXPECT_COMMIT_GATEWAY_BLOB_UNIT_BLOB'; exit 2; }
COMMIT=$1 GATE_BLOB=$2 UNIT_BLOB=$3
for value in "$COMMIT" "$GATE_BLOB" "$UNIT_BLOB"; do
  [[ $value =~ ^[0-9a-f]{40}$ ]] || { echo 'STOP: PIN_FORMAT'; exit 2; }
done
for binary in python3 curl systemctl systemd-analyze ss; do
  command -v "$binary" >/dev/null || { echo "STOP: TOOL_UNAVAILABLE_$binary"; exit 2; }
done
python3 -c 'import cryptography' || { echo 'STOP: python3-cryptography unavailable'; exit 2; }
[[ $(systemctl show -P ActiveState judun-staging-isolated.service) == active ]] || {
  echo 'STOP: STAGING_NOT_ACTIVE'; exit 2;
}
[[ ! -e /etc/systemd/system/judun-stage-health-oidc.service ]] || {
  echo 'STOP: GATEWAY_ALREADY_INSTALLED_REVIEW_MANUALLY'; exit 2;
}
[[ ! -e /srv/judun-stage-health-oidc/stage_health_oidc_gateway.py ]] || {
  echo 'STOP: GATEWAY_SOURCE_ALREADY_INSTALLED'; exit 2;
}
TMP=$(mktemp -d)
installed=0 success=0
cleanup() {
  if [[ $success -eq 0 && $installed -eq 1 ]]; then
    systemctl disable --now judun-stage-health-oidc.service >/dev/null 2>&1 || true
    rm -f /etc/systemd/system/judun-stage-health-oidc.service
    rm -f /srv/judun-stage-health-oidc/stage_health_oidc_gateway.py
    systemctl daemon-reload >/dev/null 2>&1 || true
    echo 'NEW_GATEWAY_FILES_REVERTED=TRUE' >&2
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT
BASE="https://raw.githubusercontent.com/momopuke/judun-deploy/$COMMIT/ops"
curl -fsSL --proto '=https' --tlsv1.2 --retry 2 --max-time 30 "$BASE/stage_health_oidc_gateway.py" -o "$TMP/gateway.py"
curl -fsSL --proto '=https' --tlsv1.2 --retry 2 --max-time 30 "$BASE/judun-stage-health-oidc.service" -o "$TMP/gateway.service"
python3 - "$TMP/gateway.py" "$GATE_BLOB" "$TMP/gateway.service" "$UNIT_BLOB" <<'PY'
import hashlib,sys
from pathlib import Path
for filename,expected in zip(sys.argv[1::2],sys.argv[2::2]):
    data=Path(filename).read_bytes()
    oid=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
    if oid != expected: raise SystemExit('STOP: PINNED_BLOB_MISMATCH')
print('PINNED_GATEWAY_AND_SERVICE=PASS')
PY
python3 -m py_compile "$TMP/gateway.py"
# Verify the two local stage health identities without changing either service.
python3 - <<'PY'
import json,urllib.request
for path in ('/health/build','/health/artifact?deep=true','/health/ready'):
    with urllib.request.urlopen('http://127.0.0.1:8011'+path,timeout=5) as r:
        assert r.status==200 and isinstance(json.load(r),dict)
print('ORIGINAL_ISOLATED_STAGE_LOCAL_HEALTH=PASS')
PY
installed=1
mkdir -p -m 0755 /srv/judun-stage-health-oidc
install -o root -g root -m 0644 "$TMP/gateway.py" /srv/judun-stage-health-oidc/stage_health_oidc_gateway.py
install -o root -g root -m 0644 "$TMP/gateway.service" /etc/systemd/system/judun-stage-health-oidc.service
systemd-analyze verify /etc/systemd/system/judun-stage-health-oidc.service || {
  echo 'STOP: SYSTEMD_UNIT_INVALID'; exit 2;
}
systemctl daemon-reload
systemctl enable --now judun-stage-health-oidc.service
systemctl is-active --quiet judun-stage-health-oidc.service || {
  echo 'STOP: GATEWAY_SERVICE_FAILED'; exit 2;
}
python3 - <<'PY'
import urllib.request,urllib.error
req=urllib.request.Request('http://127.0.0.1:18762/__jd_stage_health/v1/health/build')
try:
    urllib.request.urlopen(req,timeout=8)
    raise SystemExit('STOP: UNAUTHENTICATED_GATEWAY_EXPOSED')
except urllib.error.HTTPError as e:
    if e.code!=403: raise SystemExit('STOP: GATEWAY_UNEXPECTED_STATUS')
print('GATEWAY_ANONYMOUS_REQUEST_DENIED=PASS')
PY
ss -H -lnt '( sport = :18762 )' | grep -Eq '^LISTEN .+127\.0\.0\.1:18762 ' || {
  echo 'STOP: NOT_LOOPBACK_BOUND'; exit 2;
}
success=1
echo 'LOCAL_OIDC_GATEWAY_READY=PASS'
echo 'HTTPS_INGRESS=NOT_CONFIGURED; SIGNED_RELEASE_GATE=HOLD_UNTIL_REAL_CI_OIDC_ATTESTATION'
