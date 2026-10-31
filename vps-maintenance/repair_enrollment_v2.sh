#!/usr/bin/env bash
# SC VPS enrollment repair v2: only acts on the known, previously installed agent.
# Does not restart/stop the browser, recorder, LINE, JUDUN, Docker or SSH.
set -Eeuo pipefail
umask 077
export LC_ALL=C
BASE=/opt/sc-vps-maintenance
SERVICE=sc-vps-maintenance.service
TIMER=sc-vps-maintenance.timer
OLD_SHA=f2cf1c3322347b9e7814f04504d9c23e20b2d293
NEW_SHA=0709ae8da348b913bb7a56303b80a87f06e934ed
URL=https://raw.githubusercontent.com/momopuke/judun-deploy/cf92529360651f378c66d15465e3d030c45feedb/vps-maintenance/agent_v2.py
log(){ echo "[SC-VPS-REPAIR] $*"; }
fail(){ log "BLOCKED: $*" >&2; exit 7; }
[[ "$(id -u)" == "0" ]] || fail 'root required'
for x in systemctl curl python3 install flock journalctl; do command -v "$x" >/dev/null || fail "missing $x"; done
[[ -d /run/systemd/system ]] || fail 'systemd not running'
[[ -f "$BASE/agent.py" && ! -L "$BASE/agent.py" ]] || fail 'known agent missing or unsafe'
grep -qx '# SC-VPS-MAINTENANCE-MANAGED v1' /etc/systemd/system/sc-vps-maintenance.service || fail 'service ownership mismatch'
grep -qx '# SC-VPS-MAINTENANCE-MANAGED v1' /etc/systemd/system/sc-vps-maintenance.timer || fail 'timer ownership mismatch'
exec 9>/run/sc-vps-enroll.lock
flock -n 9 || fail 'another enrollment is running'
gitblob(){ python3 - "$1" <<'PY'
import hashlib,sys,pathlib
d=pathlib.Path(sys.argv[1]).read_bytes()
print(hashlib.sha1(('blob '+str(len(d))+'\0').encode()+d).hexdigest())
PY
}
CURRENT="$(gitblob "$BASE/agent.py")"
[[ "$CURRENT" == "$OLD_SHA" || "$CURRENT" == "$NEW_SHA" ]] || fail "installed agent SHA unexpected: $CURRENT"
log 'Recent failed-run evidence (read-only):'
journalctl -u "$SERVICE" -n 20 --no-pager -o cat 2>/dev/null | tail -n 20 || true
log 'Before CPU:'
systemctl show stripchat-browser-desktop.service -p ActiveState -p CPUQuotaPerSecUSec -p CPUWeight --no-pager || true
TMP="$(mktemp -d /tmp/sc-vps-repair.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
curl -fsSL --retry 2 --connect-timeout 10 --max-time 35 "$URL" -o "$TMP/agent.py" || fail 'v2 download failed'
[[ "$(gitblob "$TMP/agent.py")" == "$NEW_SHA" ]] || fail 'v2 pinned Git blob SHA mismatch'
python3 -m py_compile "$TMP/agent.py" || fail 'v2 syntax invalid'
python3 "$TMP/agent.py" --check >/dev/null || fail 'v2 selfcheck failed'
python3 - "$TMP/agent.py" <<'PY'
import importlib.util,sys
spec=importlib.util.spec_from_file_location('sc_vps_v2',sys.argv[1])
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
assert mod.cpu_percent('400ms')==40.0
assert mod.cpu_percent('250ms')==25.0
assert mod.cpu_percent('infinity')==float('inf')
print('[SC-VPS-REPAIR] local quota parser checks PASS')
PY
BACKUP=/var/backups/sc-vps-maintenance
install -d -m 0700 "$BACKUP"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
cp -a "$BASE/agent.py" "$BACKUP/agent-before-v2-$STAMP.py"
if [[ "$CURRENT" != "$NEW_SHA" ]]; then
  install -m 0755 "$TMP/agent.py" "$BASE/agent.py.new"
  mv -f "$BASE/agent.py.new" "$BASE/agent.py"
fi
systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || true
if ! systemctl start "$SERVICE"; then
  log 'First action STILL FAILED; restore previous agent; keep timer disabled'
  systemctl disable --now "$TIMER" >/dev/null 2>&1 || true
  if [[ "$CURRENT" != "$NEW_SHA" ]]; then
    install -m 0755 "$BACKUP/agent-before-v2-$STAMP.py" "$BASE/agent.py"
  fi
  journalctl -u "$SERVICE" -n 40 --no-pager -o cat 2>/dev/null || true
  fail 'VPS runtime failure, see journal above (no blind service restart)'
fi
python3 - <<'PY' || fail 'first-run result not recorded; timer will not be enabled'
import json,pathlib
p=pathlib.Path('/var/lib/sc-vps-maintenance/state.json')
data=json.loads(p.read_text())
assert data.get('last_seq',0)>=1 and data.get('operation')=='browser_limit'
assert data.get('status')=='applied'
print('[SC-VPS-REPAIR] first operation state:',json.dumps(data,ensure_ascii=False))
PY
systemctl enable --now "$TIMER" || fail 'first action succeeded but timer failed to enable'
[[ "$(systemctl is-active "$TIMER")" == "active" ]] || fail 'timer not active'
log 'After CPU:'
systemctl show stripchat-browser-desktop.service -p ActiveState -p CPUQuotaPerSecUSec -p CPUWeight --no-pager
log 'CPU PSI:'
cat /proc/pressure/cpu | head -n 1
log 'Load:'
uptime
log 'RECOVERED: timer active; browser resource limit applied without service restart'
log 'Live moderation and load reduction still require separate verification'
