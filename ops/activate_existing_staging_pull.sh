#!/usr/bin/env bash
# One-time opt-in activation of the EXISTING signed staging pull mechanism.
# No signer generation, no production writes, no public source/key disclosure.
set -Eeuo pipefail
umask 077

usage() {
  echo 'Usage: bash ops/activate_existing_staging_pull.sh --check-only|--enable' >&2
  exit 64
}
[[ $# == 1 ]] || usage
case "$1" in --check-only|--enable) mode="$1" ;; *) usage ;; esac
[[ $(id -u) -eq 0 ]] || { echo 'STOP: ROOT_REQUIRED' >&2; exit 1; }
source_root=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
root=/srv/judun-staging
config=/etc/judun-staging-pull
units=/etc/systemd/system
pin='17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'

regular_root() {
  local f=$1
  [[ -f "$f" && ! -L "$f" && $(stat -c '%u' "$f") == 0 ]]
}
private_file() {
  local f=$1 mode
  regular_root "$f" || return 1
  mode=$(stat -c '%a' "$f")
  [[ "$mode" == 600 || "$mode" == 400 ]]
}
stop() { echo "STOP: $1" >&2; exit 1; }

[[ -d "$root" && ! -L "$root" ]] || stop 'STAGE_ROOT_INVALID'
regular_root "$root/isolated.enabled" || stop 'ISOLATION_MARKER_MISSING'
systemctl is-active --quiet judun-staging-isolated.service || stop 'ISOLATED_STAGE_NOT_ACTIVE'
[[ -d "$config" && ! -L "$config" && $(stat -c '%u' "$config") == 0 ]] || stop 'CONFIG_DIR_MISSING'
private_file "$config/nexus-read-token" || stop 'NEXUS_CREDENTIAL_NOT_PROTECTED'
private_file "$config/recipient-key.pem" || stop 'CMS_RECIPIENT_KEY_NOT_PROTECTED'
regular_root "$config/recipient.pem" || stop 'CMS_RECIPIENT_CERT_MISSING'
regular_root "$config/release_signing_public.pem" || stop 'PINNED_RELEASE_KEY_MISSING'
regular_root "$source_root/keys/release_signing_public.pem" || stop 'SOURCE_KEY_MISSING'
[[ $(sha256sum "$config/release_signing_public.pem" | cut -d' ' -f1) == "$pin" ]] || stop 'RELEASE_KEY_PIN_MISMATCH'
cmp -s -- "$source_root/keys/release_signing_public.pem" "$config/release_signing_public.pem" || stop 'RELEASE_KEY_SOURCE_MISMATCH'

for file in staging_release.py staging_deploy_request.py; do
  src="$source_root/p3/$file"; dst="$root/$file"
  [[ -f "$src" && ! -L "$src" ]] || stop "MISSING_SOURCE_$file"
  if [[ -e "$dst" || -L "$dst" ]]; then
    regular_root "$dst" && cmp -s -- "$src" "$dst" || stop "EXISTING_AGENT_DIFFERS_$file"
  fi
done
for file in judun-staging-pull.service judun-staging-pull.timer; do
  src="$source_root/ops/$file"; dst="$units/$file"
  [[ -f "$src" && ! -L "$src" ]] || stop "MISSING_SOURCE_$file"
  if [[ -e "$dst" || -L "$dst" ]]; then
    regular_root "$dst" && cmp -s -- "$src" "$dst" || stop "EXISTING_UNIT_DIFFERS_$file"
  fi
done

# Prove owner-only NEXUS read authorization BEFORE enabling automated pulls.
python3 -I -B - "$source_root/ops/automation_bridge.py" "$config/nexus-read-token" <<'PY' || stop 'NEXUS_REQUEST_AUTH_FAILED'
import importlib.util, sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('judun_automation_bridge_probe',sys.argv[1])
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
if not m.request_auth_ok(Path(sys.argv[2])):
    raise SystemExit(1)
PY

echo 'JUDUN_STAGING_PULL_PREFLIGHT_PASS (production signer/QA NOT verified)'
[[ "$mode" == '--enable' ]] || exit 0

for file in staging_release.py staging_deploy_request.py; do
  [[ -e "$root/$file" ]] || install -o root -g root -m 0644 "$source_root/p3/$file" "$root/$file"
done
for file in judun-staging-pull.service judun-staging-pull.timer; do
  [[ -e "$units/$file" ]] || install -o root -g root -m 0644 "$source_root/ops/$file" "$units/$file"
done
systemctl daemon-reload
systemctl enable --now judun-staging-pull.timer
systemctl is-enabled --quiet judun-staging-pull.timer || stop 'STAGE_TIMER_NOT_ENABLED'
systemctl is-active --quiet judun-staging-pull.timer || stop 'STAGE_TIMER_NOT_ACTIVE'
echo 'JUDUN_STAGING_PULL_ARMED (not QA, SIGNED, DEPLOYED or LIVE_VERIFIED)'
