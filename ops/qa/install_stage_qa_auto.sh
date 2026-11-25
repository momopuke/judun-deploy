#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'STOP: ROOT_REQUIRED'; exit 1; }
for x in curl python3 sha256sum systemctl systemd-analyze flock; do command -v "$x" >/dev/null; done
systemctl is-active --quiet judun-staging-isolated.service
systemctl is-active --quiet judun-staging-pull.timer
for f in /srv/judun-staging/.lock /var/lib/judun-staging-pull/.lock; do
  [[ -f "$f" && ! -L "$f" ]] || { echo 'STOP: STAGING_LOCK_MISSING'; exit 1; }
done
D=$(mktemp -d)
T=/opt/judun-stage-qa-auto
UNIT=/etc/systemd/system/judun-stage-native-qa-auto.service
DROP=/etc/systemd/system/judun-staging-pull.service.d/90-native-qa-auto.conf
NEW_UNIT=0; NEW_DROP=0; KEEP=0
cleanup() {
  rc=$?
  if [[ $KEEP == 0 ]]; then
    [[ $NEW_DROP == 0 ]] || rm -f "$DROP"
    [[ $NEW_UNIT == 0 ]] || rm -f "$UNIT"
    if [[ $NEW_DROP == 1 || $NEW_UNIT == 1 ]]; then systemctl daemon-reload || true; fi
  fi
  rm -rf "$D"
  exit "$rc"
}
trap cleanup EXIT
BASE=https://raw.githubusercontent.com/momopuke/judun-deploy
fetch() {
  curl -fsSL --proto '=https' --tlsv1.2 --retry 2 --max-time 45 "$BASE/$1" -o "$D/$2"
  echo "$3  $D/$2" | sha256sum -c -
}
fetch 372f6f4951704f4d62ca14578b361e1a27e8179d/ops/qa/stage_qa_auto.py auto.py 452ed674c51edf848c7bd4b90c2a5e0be318baa115487cdac4f4804728aeb108
fetch 4c8f34748034bbc07fdb9a07d0b891cd42da81a1/ops/qa/stage_native_qa_launcher.py launcher.py 25e060c2ce7702a59edbf01f025ec8da50d82e1fc185d21eb689b543ff760dc2
fetch dddae11693a904a7e9fa741e7222fa39bc8c3f4a/ops/qa/judun_stage_native_business_qa_v3_20261124.py native_qa.py d9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568
python3 -m py_compile "$D/auto.py" "$D/launcher.py" "$D/native_qa.py"
[[ ! -L "$T" ]] || { echo 'STOP: UNSAFE_TOOL_DIR'; exit 1; }
install -d -m 700 "$T"
for name in auto.py launcher.py native_qa.py; do
  if [[ -e "$T/$name" || -L "$T/$name" ]]; then
    [[ ! -L "$T/$name" ]] && cmp -s "$D/$name" "$T/$name" || { echo 'STOP: EXISTING_TOOL_DIFFERS'; exit 1; }
  else
    install -m 700 "$D/$name" "$T/$name"
  fi
done
# Preflight must attest the existing receipt and noninteractive test-only code.
# Do not ask the provider to run another synthetic case at installation time.
python3 -I -B "$T/auto.py" --probe | tee "$D/probe.log"
grep -q 'NONINTERACTIVE_STAGE_CODE=READY' "$D/probe.log"
grep -q 'EXISTING_NATIVE_QA_PASS' "$D/probe.log" || { echo 'STOP: EXISTING_QA_RECEIPT_REQUIRED'; exit 1; }
cat > "$D/judun-stage-native-qa-auto.service" <<'UNIT'
[Unit]
Description=Run existing native QA once for a signed Judun staging snapshot
After=judun-staging-pull.service judun-staging-isolated.service
ConditionPathExists=/srv/judun-staging/isolated.enabled

[Service]
Type=oneshot
ExecCondition=/usr/bin/python3 -I -B /opt/judun-stage-qa-auto/auto.py --needs-run
ExecStart=/usr/bin/python3 -I -B /opt/judun-stage-qa-auto/auto.py
StateDirectory=judun-stage-native-qa-auto
StateDirectoryMode=0700
TimeoutStartSec=45min
UMask=0077
ProtectSystem=strict
ReadWritePaths=/var/lib/judun-stage-business-qa /var/lib/judun-staging-pull/.lock /srv/judun-staging/.lock
ProtectHome=yes
PrivateTmp=yes
NoNewPrivileges=yes
InaccessiblePaths=-/var/www/advisor -/srv/judun -/var/lib/judun -/var/lib/advisor -/var/lib/judun-autodeploy
UNIT
cat > "$D/90-native-qa-auto.conf" <<'UNIT'
[Unit]
OnSuccess=judun-stage-native-qa-auto.service

[Service]
ExecCondition=/usr/bin/flock -n /var/lib/judun-staging-pull/.lock /usr/bin/true
UNIT
for p in "$UNIT" "$DROP"; do
  if [[ -e "$p" || -L "$p" ]]; then
    [[ ! -L "$p" ]] && cmp -s "$p" "$D/${p##*/}" || { echo 'STOP: EXISTING_UNIT_DIFFERS'; exit 1; }
  fi
done
[[ ! -L "${DROP%/*}" ]] || { echo 'STOP: UNSAFE_DROPIN_DIR'; exit 1; }
install -d -m 755 "${DROP%/*}"
if [[ ! -e "$UNIT" ]]; then install -m 644 "$D/${UNIT##*/}" "$UNIT"; NEW_UNIT=1; fi
if [[ ! -e "$DROP" ]]; then install -m 644 "$D/${DROP##*/}" "$DROP"; NEW_DROP=1; fi
systemd-analyze verify "$UNIT" judun-staging-pull.service
systemctl daemon-reload
systemctl show judun-staging-pull.service -p OnSuccess --value | grep -qw judun-stage-native-qa-auto.service
systemctl start judun-stage-native-qa-auto.service
systemctl is-active --quiet judun-staging-pull.timer
systemctl is-active --quiet judun-staging-isolated.service
KEEP=1
echo 'AUTO_STAGE_QA_HOOK_ENABLED'
python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
link=os.readlink('/srv/judun-staging/current')
p=Path('/var/lib/judun-stage-native-qa-auto')/(hashlib.sha256(link.encode()).hexdigest()+'.json')
print(p.read_text() if p.is_file() else 'AUTO_QA_WAITING_FOR_NEXT_STAGE_PULL')
PY
