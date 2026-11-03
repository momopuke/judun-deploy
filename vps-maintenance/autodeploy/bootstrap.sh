#!/usr/bin/env bash
# One-time trusted enrollment for signed SC VPS releases.
# Does NOT change JUDUN, LINE, Recorder, Docker, Chromium units or credentials.
set -Eeuo pipefail
umask 077
export LC_ALL=C
REPO='https://raw.githubusercontent.com/momopuke/judun-deploy'
# Release bot commit (exact source); filled with immutable SHA after publication.
COMMIT='59d1f4b37f20457c071600e797d2c43369d46a6b'
AGENT_SHA256='f9578b6af10667556649bcd1b7f7b79ba14d145432b4ccabe80d1a2cab0b6ce5'
PUB_SHA256='5af7e7c13f1db31b0ce72f87a9e67765ca237a2cb8cdc318a0709b44c8e80418'
AGENT_URL="$REPO/$COMMIT/vps-maintenance/autodeploy/pull_agent.py"
PUB_URL="$REPO/$COMMIT/vps-maintenance/autodeploy/release-signing-public.pem"
BASE=/opt/sc-vps-autodeploy
STATE=/var/lib/sc-vps-autodeploy
SERVICE=/etc/systemd/system/sc-vps-autodeploy.service
TIMER=/etc/systemd/system/sc-vps-autodeploy.timer
log(){ printf '[SCVPS-AUTO] %s\n' "$*"; }
fail(){ log "BLOCKED: $*" >&2; exit 9; }
[[ "$(id -u)" == '0' ]] || fail 'root required'
[[ -r /etc/os-release ]] && grep -qx 'ID=debian' /etc/os-release || fail 'expected Debian system'
for c in curl sha256sum systemctl python3 openssl flock install;do command -v "$c" >/dev/null || fail "missing $c";done
[[ -d /run/systemd/system ]] || fail 'systemd unavailable'
# Existing browser and recorder must be recognizable; do not install on a new/unknown VPS.
[[ "$(systemctl show stripchat-browser-desktop.service -p LoadState --value)" == 'loaded' ]] || fail 'unknown browser service'
[[ "$(docker inspect -f '{{.State.Running}}' stripchat-recorder 2>/dev/null)" == 'true' ]] || fail 'recorder not running'
if [[ -e "$SERVICE" || -e "$TIMER" || -e "$BASE/pull_agent.py" ]]; then
  fail 'already enrolled or unit/file conflict; no overwrite permitted'
fi
exec 9>/run/sc-vps-autodeploy-enroll.lock
flock -n 9 || fail 'another installer is running'
TMP="$(mktemp -d /tmp/sc-vps-autodeploy.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
log 'Download immutable agent and pinned signing trust root'
curl -fsSL --retry 2 --connect-timeout 10 --max-time 35 "$AGENT_URL" -o "$TMP/pull_agent.py" || fail 'agent download failed'
curl -fsSL --retry 2 --connect-timeout 10 --max-time 35 "$PUB_URL" -o "$TMP/release-signing-public.pem" || fail 'public key download failed'
[[ "$(sha256sum "$TMP/pull_agent.py" | cut -d' ' -f1)" == "$AGENT_SHA256" ]] || fail 'agent integrity mismatch'
[[ "$(sha256sum "$TMP/release-signing-public.pem" | cut -d' ' -f1)" == "$PUB_SHA256" ]] || fail 'trust root integrity mismatch'
python3 -m py_compile "$TMP/pull_agent.py" || fail 'syntax validation failed'
python3 "$TMP/pull_agent.py" --check >/dev/null || fail 'selfcheck failed'
install -d -m 0700 "$BASE" "$STATE" /var/backups/sc-vps-autodeploy
install -m 0700 "$TMP/pull_agent.py" "$BASE/pull_agent.py"
install -m 0600 "$TMP/release-signing-public.pem" "$BASE/release-signing-public.pem"
cat > "$SERVICE" <<'EOF'
# SC-VPS-AUTODEPLOY-MANAGED v1
[Unit]
Description=SC VPS signed release pull and guarded acceptance
Wants=network-online.target
After=network-online.target
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/sc-vps-autodeploy/pull_agent.py
CPUQuota=15%
MemoryMax=180M
Nice=15
IOSchedulingClass=idle
TimeoutStartSec=260s
NoNewPrivileges=yes
PrivateTmp=yes
StandardOutput=journal
StandardError=journal
EOF
cat > "$TIMER" <<'EOF'
# SC-VPS-AUTODEPLOY-MANAGED v1
[Unit]
Description=Check signed SC VPS maintenance releases
[Timer]
OnBootSec=180s
OnActiveSec=20s
OnUnitActiveSec=300s
AccuracySec=10s
RandomizedDelaySec=30s
Unit=sc-vps-autodeploy.service
[Install]
WantedBy=timers.target
EOF
chmod 0644 "$SERVICE" "$TIMER"
systemctl daemon-reload
systemctl enable --now sc-vps-autodeploy.timer || fail 'timer enable failed'
log 'Signed release channel enrolled. Running first release acceptance (guarded).'
if systemctl start sc-vps-autodeploy.service;then
  log 'FIRST_RUN_FINISHED; check private state for applied/safety_refused/needs_review'
else
  log 'First run blocked (e.g. no network); timer stays active for later retries'
fi
log 'STATUS: systemctl is-active sc-vps-autodeploy.timer'
log 'RESULT: cat /var/lib/sc-vps-autodeploy/state.json'
log 'No change to protected services was requested by enrollment itself'
