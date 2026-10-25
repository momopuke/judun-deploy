#!/usr/bin/env bash
# JUDUN v1.2.148 guarded retrigger + diagnostic for the EXISTING signed auto-deploy agent.
# Does not rebuild the VPS, edit customer data, reset credentials, or bypass release signatures.
set -uo pipefail
export LC_ALL=C

BASE_VERSION='1.2.146'
BASE_ARTIFACT='JUDUN-1.2.146-PRIVATEEVIDENCEFIX20261025'
BASE_TREE='fdeaae5f8e59b520637d9eaff1b44704d8d398dc8b73dd630f64e60b9bc3f7f8'
TARGET_VERSION='1.2.148'
TARGET_ARTIFACT='JUDUN-1.2.148-FREELEADS20261026'
TARGET_RELEASE='v1.2.148-company-onboarding-lineagefix-20261026'
HEALTH='https://judun.142-93-91-214.sslip.io/health/build'
DEEP='https://judun.142-93-91-214.sslip.io/health/artifact?deep=true'
CHANNEL='https://raw.githubusercontent.com/momopuke/judun-deploy/main/channel/stable.json'

say(){ printf '[JUDUN-V148] %s\n' "$*"; }
fail(){ say "BLOCKED: $*" >&2; exit 1; }
get(){ curl --fail --silent --show-error --connect-timeout 10 --max-time 25 --retry 2 --retry-delay 2 -H 'Cache-Control: no-cache' "$1"; }

[[ "$(id -u)" == 0 ]] || fail 'Run as root on the existing VPS.'
for cmd in curl python3 systemctl journalctl; do command -v "$cmd" >/dev/null || fail "$cmd unavailable."; done
[[ -f /etc/systemd/system/judun-autodeploy.service ]] || fail 'Existing judun-autodeploy.service not found.'
[[ -f /etc/systemd/system/judun-autodeploy.timer ]] || fail 'Existing judun-autodeploy.timer not found.'

channel="$(get "$CHANNEL")" || fail 'Cannot read signed release channel.'
printf '%s' "$channel" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x.get("release_id")=="v1.2.148-company-onboarding-lineagefix-20261026"
assert x.get("base_artifact_id")=="JUDUN-1.2.146-PRIVATEEVIDENCEFIX20261025"
assert x.get("target_artifact_id")=="JUDUN-1.2.148-FREELEADS20261026"
assert x.get("expected_display_version")=="v1.2.148"
assert x.get("payload_path")=="releases/v1.2.148-company-onboarding-lineagefix-20261026.cms.b64"
' >/dev/null 2>&1 || fail 'GitHub signed channel is no longer the reviewed v1.2.148 target.'

before="$(get "$HEALTH")" || fail 'Live /health/build unavailable.'
state="$(printf '%s' "$before" | python3 -c '
import json,sys
x=json.load(sys.stdin)
print(x.get("version",""),x.get("artifact_id",""),x.get("source_tree_sha256",""))
')" || fail 'Invalid health response.'
read -r version artifact tree <<<"$state"
say "Before: version=$version artifact=$artifact"

verify_target(){
  local h d
  h="$(get "$HEALTH")" || return 1
  d="$(get "$DEEP")" || return 1
  printf '%s\n%s' "$h" "$d" | python3 -c '
import json,sys
a=sys.stdin.read().splitlines()
h=json.loads(a[0]); d=json.loads(a[1])
assert h.get("version")=="1.2.148"
assert h.get("artifact_id")=="JUDUN-1.2.148-FREELEADS20261026"
assert d.get("status")=="ok"
assert d.get("artifact_id")=="JUDUN-1.2.148-FREELEADS20261026"
assert int(d.get("files_verified") or 0)==85
assert int(d.get("mismatch_count") or 0)==0
' >/dev/null 2>&1
}

if [[ "$version" == "$TARGET_VERSION" && "$artifact" == "$TARGET_ARTIFACT" ]]; then
  verify_target || fail 'Target identity exists but 85/85 deep integrity did not pass.'
  say 'PASS: v1.2.148 already installed; deep integrity 85/85.'
  exit 0
fi

[[ "$version" == "$BASE_VERSION" && "$artifact" == "$BASE_ARTIFACT" ]] || fail 'Live version is neither reviewed base nor target.'
[[ "$tree" == "$BASE_TREE" ]] || fail 'Live v1.2.146 source tree differs from reviewed base; refusing to mutate.'

say "Timer before: $(systemctl is-active judun-autodeploy.timer 2>/dev/null || true)"
say "Service before: $(systemctl is-failed judun-autodeploy.service 2>/dev/null || true)"
systemctl enable --now judun-autodeploy.timer >/dev/null 2>&1 || fail 'Could not activate existing timer.'
systemctl reset-failed judun-autodeploy.service >/dev/null 2>&1 || true
say 'Triggering existing signed auto-deploy agent once.'
rc=0
systemctl start judun-autodeploy.service || rc=$?
say "Agent start exit code: $rc"

for i in $(seq 1 12); do
  if verify_target; then
    say 'PASS: signed v1.2.148 deployed; deep integrity 85/85.'
    exit 0
  fi
  sleep 5
done

after="$(get "$HEALTH" 2>/dev/null || printf '{}')"
printf '%s' "$after" | python3 -c '
import json,sys
try:x=json.load(sys.stdin)
except Exception:x={}
print("[JUDUN-V148] After: version=%s artifact=%s"%(x.get("version","?"),x.get("artifact_id","?")))
' 2>/dev/null || true

say '--- existing auto-deploy service status ---'
systemctl --no-pager --full status judun-autodeploy.service 2>&1  | grep -Evi '(PASSWORD|TOKEN|SECRET|API.?KEY|AUTHORIZATION|PRIVATE.?KEY)'  | tail -n 25 | cut -c1-260 || true
say '--- relevant existing agent journal ---'
journalctl -u judun-autodeploy.service -n 220 --no-pager -o cat 2>/dev/null  | grep -Ei '\[FAIL\]|\[ROLLBACK\]|Traceback|ValueError|AssertionError|error|exception|mismatch|missing|cannot|denied|rejected|invalid|drift|exit.code|source|backup|payload|release'  | grep -Evi '(PASSWORD|TOKEN|SECRET|API.?KEY|AUTHORIZATION|PRIVATE.?KEY)'  | tail -n 45 | cut -c1-260 || true
fail 'Existing signed agent did not reach v1.2.148. The diagnostic lines above are the next root cause.'
