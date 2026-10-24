#!/usr/bin/env bash
# JUDUN v1.2.145: safely retrigger the EXISTING signed auto-deploy agent.
# Never rebuild VPS, edit application files, reset passwords, or alter databases.
set -uo pipefail
export LC_ALL=C
BASE='JUDUN-1.2.144-PDFRECOVERY20261025'
TARGET='JUDUN-1.2.145-PRIVATEEVIDENCE20261025'
HEALTH_URL='https://judun.142-93-91-214.sslip.io/health/build'
CHANNEL_URL='https://raw.githubusercontent.com/momopuke/judun-deploy/main/channel/stable.json'

say(){ printf '[JUDUN-V145] %s\n' "$*"; }
fail(){ say "BLOCKED: $*" >&2; exit 1; }
[[ "$(id -u)" == '0' ]] || fail 'Run as root from the existing VPS Console.'
command -v systemctl >/dev/null || fail 'systemctl unavailable.'
command -v curl >/dev/null || fail 'curl unavailable.'
command -v python3 >/dev/null || fail 'python3 unavailable.'
[[ -f /etc/systemd/system/judun-autodeploy.service ]] || fail 'Existing deploy service not found; no new service will be installed.'

get_json(){ curl --fail --silent --show-error --connect-timeout 10 --max-time 25 --retry 2 --retry-delay 2 -H 'Cache-Control: no-cache' "$1"; }
channel="$(get_json "$CHANNEL_URL")" || fail 'Cannot read signed release channel.'
if ! printf '%s' "$channel" | python3 -c '
import json,sys
v=json.load(sys.stdin)
assert v.get("expected_display_version")=="v1.2.145"
assert v.get("base_artifact_id")=="JUDUN-1.2.144-PDFRECOVERY20261025"
assert v.get("target_artifact_id")=="JUDUN-1.2.145-PRIVATEEVIDENCE20261025"
assert v.get("payload_path")=="releases/v1.2.145-private-evidence-20261025.cms.b64"
' >/dev/null 2>&1;then
  fail 'Signed channel target has changed or channel is invalid; refusing to install an unreviewed version.'
fi

current="$(get_json "$HEALTH_URL")" || fail 'Live /health/build unavailable; service will not be forced.'
state="$(printf '%s' "$current" | python3 -c '
import json,sys
x=json.load(sys.stdin)
print(x.get("version",""),x.get("artifact_id",""),x.get("source_tree_sha256",""))
' 2>/dev/null)" || fail 'Invalid live health response.'
read -r version artifact tree <<<"$state"
say "Before: version=$version artifact=$artifact"
verify_deep(){
  local raw
  raw="$(get_json 'https://judun.142-93-91-214.sslip.io/health/artifact?deep=true')" || return 1
  printf '%s' "$raw" | python3 -c '
import json,sys
x=json.load(sys.stdin)
assert x.get("status")=="ok"
assert x.get("artifact_id")=="JUDUN-1.2.145-PRIVATEEVIDENCE20261025"
assert int(x.get("files_verified") or 0)==85
assert int(x.get("mismatch_count") or 0)==0
' >/dev/null 2>&1
}
if [[ "$version" == '1.2.145' && "$artifact" == "$TARGET" ]];then
  verify_deep || fail 'Release is installed but deep file integrity did not pass.'
  say 'PASS: target release already installed, deep integrity 85/85. No service changes made.'
  exit 0
fi
[[ "$version" == '1.2.144' && "$artifact" == "$BASE" ]] || fail 'Live version no longer matches the signed release base.'
[[ "$tree" == '291ce79c42de8380ac760035d02ba02ec17c00a434c6d6e8a83b0deb55fb94de' ]] || fail 'Base source tree differs; refusing to overwrite.'

say 'Re-enabling the existing minute-based timer (no new software or files).'
systemctl enable --now judun-autodeploy.timer >/dev/null 2>&1 || fail 'Could not activate existing timer.'
systemctl reset-failed judun-autodeploy.service >/dev/null 2>&1 || true
say 'Triggering the original signed release agent once.'
rc=0
systemctl start judun-autodeploy.service || rc=$?
say "Agent exit code: $rc"

latest="$(get_json "$HEALTH_URL" 2>/dev/null)" || latest='{}'
check="$(printf '%s' "$latest" | python3 -c 'import json,sys; x=json.load(sys.stdin); print(x.get("version","?"),x.get("artifact_id","?"))' 2>/dev/null)" || check='? ?'
say "After: $check"
if [[ "$check" == "1.2.145 $TARGET" ]];then
  verify_deep || fail 'Release is installed but deep file integrity did not pass.'
  say 'PASS: signed v1.2.145 deployed, deep integrity 85/85.'
  exit 0
fi
say 'NOT DEPLOYED. Safe diagnostic excerpts from the existing agent:'
journalctl -u judun-autodeploy.service -n 130 --no-pager -o cat 2>/dev/null \
  | grep -Ei '\[FAIL\]|\[ROLLBACK\]|error|exception|mismatch|missing|cannot|denied|rejected|invalid|exit.code|source.changed|backup' \
  | grep -Evi '(PASSWORD|TOKEN|SECRET|API.?KEY|AUTHORIZATION|PRIVATE.?KEY)' \
  | tail -n 20 | cut -c1-250 || true
fail 'Agent did not reach the v1.2.145 target. Do not update to another release without the actual failure reason.'