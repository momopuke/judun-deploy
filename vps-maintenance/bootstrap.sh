#!/usr/bin/env bash
# One-time enrollment. No inbound ports, SSH secrets, Docker restarts or JUDUN changes.
set -Eeuo pipefail
umask 077
export LC_ALL=C
REPO='https://raw.githubusercontent.com/momopuke/judun-deploy/vps-maintenance/vps-maintenance'
AGENT_GIT_BLOB_SHA='f2cf1c3322347b9e7814f04504d9c23e20b2d293'
BASE='/opt/sc-vps-maintenance'
UNIT='/etc/systemd/system/sc-vps-maintenance.service'
TIMER='/etc/systemd/system/sc-vps-maintenance.timer'
log(){ echo "[SC-VPS-ENROLL] $*"; }
fail(){ log "BLOCKED $*" >&2; exit 6; }
[[ "$(id -u)" == 0 ]] || fail 'root required'
for name in curl python3 systemctl install flock; do command -v "$name" >/dev/null || fail "missing $name"; done
[[ -f /etc/os-release ]] && grep -q '^ID=debian$' /etc/os-release || fail 'expected Debian'
[[ -d /run/systemd/system ]] || fail 'systemd not running'
[[ "$(systemctl show stripchat-browser-desktop.service -p LoadState --value)" == 'loaded' ]] || fail 'browser service absent'
if [[ -e "$UNIT" || -e "$TIMER" || -e "$BASE/agent.py" ]]; then
  fail 'already installed or name collides (no overwrite)'
fi
exec 9>/run/sc-vps-enroll.lock
flock -n 9 || fail 'enrollment in progress'
TMP="$(mktemp -d /tmp/sc-vps-agent.XXXXXXXX)"
cleanup(){ rm -rf -- "$TMP"; }
trap cleanup EXIT
log 'Fetch immutable-agent content and verify pinned Git blob digest'
curl -fsSL --connect-timeout 10 --max-time 35 --retry 2 "$REPO/agent.py" -o "$TMP/agent.py" || fail 'agent download'
python3 - "$TMP/agent.py" "$AGENT_GIT_BLOB_SHA" <<'PY'
import hashlib, pathlib, sys
data = pathlib.Path(sys.argv[1]).read_bytes()
assert hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest()==sys.argv[2], 'agent digest mismatch'
PY
python3 -m py_compile "$TMP/agent.py" || fail 'agent compile'
python3 "$TMP/agent.py" --check >/dev/null || fail 'agent selfcheck'
install -d -m 0700 "$BASE" /var/lib/sc-vps-maintenance
install -m 0755 "$TMP/agent.py" "$BASE/agent.py"
cat > "$UNIT" <<'EOF'
# SC-VPS-MAINTENANCE-MANAGED v1
[Unit]
Description=SC VPS narrow-scope GitHub maintenance agent
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/sc-vps-maintenance/agent.py
CPUQuota=15%
MemoryMax=100M
TimeoutStartSec=80
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
EOF
cat > "$TIMER" <<'EOF'
# SC-VPS-MAINTENANCE-MANAGED v1
[Unit]
Description=Poll allowlisted maintenance operations
[Timer]
OnBootSec=50s
OnActiveSec=15s
OnUnitActiveSec=60s
AccuracySec=5s
RandomizedDelaySec=5s
Unit=sc-vps-maintenance.service
[Install]
WantedBy=timers.target
EOF
chmod 0644 "$UNIT" "$TIMER"
systemctl daemon-reload
if ! systemctl start sc-vps-maintenance.service; then
  systemctl disable --now sc-vps-maintenance.timer >/dev/null 2>&1 || true
  log 'First action BLOCKED; timer not enabled; see journalctl -u sc-vps-maintenance.service'
  exit 5
fi
systemctl enable --now sc-vps-maintenance.timer
log 'ENROLLED: independent agent and timer running. Recorder, LINE and browser were not restarted.'
log 'Inspect: journalctl -u sc-vps-maintenance.service -n 20 --no-pager'
log 'Live Stripchat moderation verification is separately required.'
