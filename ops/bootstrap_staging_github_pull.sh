#!/usr/bin/env bash
# One-time setup for EXISTING Judun staging pull; no product/prod code touched.
# Must run from a SHA-pinned bundle. Do not run on an unverified branch.
set -Eeuo pipefail
umask 077
[[ $# == 1 && ( "$1" == "--check-only" || "$1" == "--enable" ) ]] || {
  echo 'Usage: bash ops/bootstrap_staging_github_pull.sh --check-only|--enable' >&2
  exit 64
}
mode="$1"
[[ $(id -u) -eq 0 ]] || { echo "STOP: ROOT_REQUIRED" >&2; exit 1; }
bundle=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
root=/srv/judun-staging
config=/etc/judun-staging-pull
systemd=/etc/systemd/system
pin='17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db'
legacy_agent_blob='10222d8a35f2ce6a4f4e06525afb9259ef8de575'
new_agent_blob='79c600023c92a1c769f26a333ea7b49d2eee96bd'
unit_blob='8dd15b2f5016b21eeb81bce9444504fff3c913b3'
timer_blob='57c8751c1d2f4f0babf827df348f9800247cc451'

stop(){ echo "STOP: $*" >&2; exit 2; }
blob() {
  python3 -I -B - "$1" <<'PY'
import hashlib,sys
from pathlib import Path
data=Path(sys.argv[1]).read_bytes()
print(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest())
PY
}
regular_root(){
  local p=$1
  [[ -f "$p" && ! -L "$p" && $(stat -c '%u' "$p") == 0 ]]
}
private_root(){
  local p=$1
  regular_root "$p" && [[ $(stat -c '%a' "$p") == 600 || $(stat -c '%a' "$p") == 400 ]]
}
expect_blob(){
  local p=$1 hash=$2
  [[ -f "$p" && ! -L "$p" ]] || stop "MISSING_SOURCE:${p##*/}"
  [[ "$(blob "$p")" == "$hash" ]] || stop "UNPINNED_SOURCE:${p##*/}"
}
request_default_off(){
  # Never enable the timer until protected main contains a safe null request.
  python3 -I -B - <<'PY'
import json
from urllib.request import ProxyHandler, HTTPRedirectHandler, Request, build_opener
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None
url='https://raw.githubusercontent.com/momopuke/judun-deploy/main/ops/staging-request.json'
try:
    op=build_opener(ProxyHandler({}), NoRedirect())
    with op.open(Request(url,headers={'Cache-Control':'no-cache'}),timeout=10) as r:
        assert r.status == 200 and r.geturl() == url
        raw=r.read(2049)
    def pairs(items):
        out={}
        for k,v in items:
            if k in out: raise ValueError('duplicate key')
            out[k]=v
        return out
    d=json.loads(raw,object_pairs_hook=pairs)
    assert type(d) is dict and d == {'candidate_commit':None}
except Exception:
    raise SystemExit(1)
PY
}
[[ -d "$root" && ! -L "$root" ]] || stop 'STAGE_ROOT_INVALID'
[[ -f "$root/isolated.enabled" && ! -L "$root/isolated.enabled" ]] || stop 'STAGE_NOT_ISOLATED'
systemctl is-active --quiet judun-staging-isolated.service || stop 'STAGE_ISOLATED_SERVICE_DOWN'
regular_root "$root/staging_release.py" || stop 'STAGE_SNAPSHOT_MANAGER_NOT_TRUSTED'
regular_root "$config/release_signing_public.pem" || stop 'RELEASE_PUBLIC_KEY_MISSING'
[[ $(sha256sum "$config/release_signing_public.pem" | cut -d' ' -f1) == "$pin" ]] || stop 'RELEASE_PUBLIC_KEY_CHANGED'
expect_blob "$bundle/p3/staging_deploy_request.py" "$new_agent_blob"
expect_blob "$bundle/ops/judun-staging-pull.service" "$unit_blob"
expect_blob "$bundle/ops/judun-staging-pull.timer" "$timer_blob"

agent="$root/staging_deploy_request.py"
if [[ -e "$agent" || -L "$agent" ]]; then
  regular_root "$agent" || stop 'EXISTING_AGENT_NOT_TRUSTED'
  agent_sha=$(blob "$agent")
  [[ "$agent_sha" == "$legacy_agent_blob" || "$agent_sha" == "$new_agent_blob" ]] || stop 'EXISTING_AGENT_UNKNOWN_DO_NOT_OVERWRITE'
fi
for unit in judun-staging-pull.service judun-staging-pull.timer; do
  src="$bundle/ops/$unit"
  dst="$systemd/$unit"
  if [[ -e "$dst" || -L "$dst" ]]; then
    regular_root "$dst" && cmp -s -- "$src" "$dst" || stop "EXISTING_UNIT_DIFFERS:$unit"
  fi
done
if [[ -e "$config" || -L "$config" ]]; then
  [[ -d "$config" && ! -L "$config" && $(stat -c '%u' "$config") == 0 ]] || stop 'CONFIG_DIRECTORY_UNTRUSTED'
fi
for file in recipient.pem recipient-key.pem; do
  [[ ! -L "$config/$file" ]] || stop "RECIPIENT_SYMLINK:$file"
done
if [[ -e "$config/recipient.pem" || -e "$config/recipient-key.pem" ]]; then
  regular_root "$config/recipient.pem" && private_root "$config/recipient-key.pem" || stop 'PARTIAL_OR_UNSAFE_RECIPIENT_PAIR'
  [[ $(sha256sum "$config/recipient.pem" | cut -d' ' -f1) == '8af33e638d5ba58efa24c192fb11e46f24ef7b2a5125460c2a63d5b668a2833e' ]] || stop 'RECIPIENT_CERT_UNEXPECTED_ROTATION'
fi

if ! request_default_off; then
  stop 'GITHUB_PROTECTED_REQUEST_NOT_READY_OR_NOT_NULL'
fi
echo 'PREFLIGHT_PASS: signed staging request channel ready, service isolated'
if [[ "$mode" == "--check-only" ]]; then
  if [[ ! -f "$config/recipient.pem" ]]; then
    echo 'RECIPIENT_PAIR=ABSENT (will generate only in --enable)'
  else
    echo 'RECIPIENT_PAIR=EXISTS'
  fi
  echo 'NO_CHANGES_MADE'
  exit 0
fi

# Only a newly absent stage-only CMS recipient is generated. The signer is NOT touched.
if [[ ! -d "$config" ]]; then
  install -d -o root -g root -m 0700 "$config"
fi
if [[ ! -f "$config/recipient.pem" ]]; then
  tmp=$(mktemp -d "$config/.new-recipient.XXXXXXXX")
  trap 'rm -rf -- "$tmp"' EXIT
  openssl req -x509 -newkey rsa:3072 -nodes -sha256 -days 825 \
    -subj '/CN=Judun Staging CMS Recipient' \
    -keyout "$tmp/recipient-key.pem" -out "$tmp/recipient.pem" \
    > /dev/null 2>&1 || stop 'CMS_RECIPIENT_GENERATION_FAILED'
  printf 'staging-key-pair-probe' > "$tmp/plain"
  openssl cms -encrypt -binary -aes256 -outform DER \
    -in "$tmp/plain" -out "$tmp/probe.cms" "$tmp/recipient.pem" \
    >/dev/null 2>&1 || stop 'CMS_ENCRYPT_SELFTEST_FAILED'
  openssl cms -decrypt -binary -inform DER -in "$tmp/probe.cms" \
    -recip "$tmp/recipient.pem" -inkey "$tmp/recipient-key.pem" \
    -out "$tmp/recovered" >/dev/null 2>&1 || stop 'CMS_DECRYPT_SELFTEST_FAILED'
  cmp -s "$tmp/plain" "$tmp/recovered" || stop 'CMS_RECIPIENT_MISMATCH'
  [[ ! -e "$config/recipient.pem" && ! -e "$config/recipient-key.pem" ]] || stop 'RECIPIENT_ALREADY_PRESENT'
  install -o root -g root -m 0600 "$tmp/recipient-key.pem" "$config/recipient-key.pem"
  install -o root -g root -m 0644 "$tmp/recipient.pem" "$config/recipient.pem"
  trap - EXIT
  rm -rf -- "$tmp"
fi
openssl x509 -in "$config/recipient.pem" -noout -checkend 86400 >/dev/null || stop 'RECIPIENT_CERT_EXPIRED'
[[ $(sha256sum "$config/recipient.pem" | cut -d' ' -f1) == '8af33e638d5ba58efa24c192fb11e46f24ef7b2a5125460c2a63d5b668a2833e' ]] || stop 'RECIPIENT_CERT_PIN_MISMATCH'
private_root "$config/recipient-key.pem" || stop 'RECIPIENT_KEY_PERMISSION'
# Ensure cert matches private key and both can handle test CMS encryption.
tmp=$(mktemp -d "$config/.pair-check.XXXXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
openssl pkey -in "$config/recipient-key.pem" -pubout -out "$tmp/key.pub" 2>/dev/null || stop 'PRIVATE_KEY_INVALID'
openssl x509 -in "$config/recipient.pem" -pubkey -noout -out "$tmp/cert.pub" 2>/dev/null || stop 'RECIPIENT_CERT_INVALID'
cmp -s "$tmp/key.pub" "$tmp/cert.pub" || stop 'RECIPIENT_KEY_CERT_MISMATCH'

# Stage snapshots and client data remain untouched. Make an exact backup of old agent.
if [[ -f "$agent" && $(blob "$agent") == "$legacy_agent_blob" ]]; then
  install -d -o root -g root -m 0700 "$root/.pull-agent-backup"
  backup="$root/.pull-agent-backup/staging_deploy_request.legacy.py"
  if [[ -e "$backup" ]]; then
    cmp -s "$agent" "$backup" || stop 'CONFLICTING_AGENT_BACKUP'
  else
    install -o root -g root -m 0600 "$agent" "$backup"
  fi
fi
if [[ ! -f "$agent" || $(blob "$agent") != "$new_agent_blob" ]]; then
  install -o root -g root -m 0644 "$bundle/p3/staging_deploy_request.py" "$root/.staging_deploy_request.py.tmp.$$"
  mv -f -- "$root/.staging_deploy_request.py.tmp.$$" "$agent"
fi
for unit in judun-staging-pull.service judun-staging-pull.timer; do
  dst="$systemd/$unit"
  [[ -e "$dst" ]] || install -o root -g root -m 0644 "$bundle/ops/$unit" "$dst"
done
python3 -I -B - <<'PY'
import sys
sys.path.insert(0,'/srv/judun-staging')
import staging_deploy_request as a
assert a.REQUEST == 'main/ops/staging-request.json'
assert a.request_commit(a.fetch) is None
PY
systemctl daemon-reload
systemctl enable --now judun-staging-pull.timer
systemctl is-enabled --quiet judun-staging-pull.timer || stop 'TIMER_NOT_ENABLED'
systemctl is-active --quiet judun-staging-pull.timer || stop 'TIMER_NOT_ACTIVE'
echo "CMS_RECIPIENT_PUBLIC_CERT_SHA256=$(sha256sum "$config/recipient.pem" | cut -d' ' -f1)"
echo 'STAGE_PULL_TIMER=ACTIVE'
echo 'STAGE_REQUEST=NONE (no new candidate, production not modified)'
echo 'FULL_RELEASE_GATE0=NOT_VERIFIED'
