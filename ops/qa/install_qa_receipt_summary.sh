#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 ]] || { echo 'STOP: ROOT_REQUIRED'; exit 1; }
G=/srv/judun-stage-health-oidc
GW=$G/stage_health_oidc_gateway.py
MOD=$G/qa_receipt_summary.py
EXPORT=$G/qa-summary
DROP=/etc/systemd/system/judun-stage-native-qa-auto.service.d/95-receipt-summary.conf
SERVICE=judun-stage-health-oidc.service
QA=judun-stage-native-qa-auto.service
BASE=https://raw.githubusercontent.com/momopuke/judun-deploy
D=$(mktemp -d)
CHANGED=0; ADDED_MODULE=0; ADDED_DROP=0; KEEP=0
cleanup() {
  rc=$?
  if [[ $KEEP == 0 ]]; then
    if [[ $ADDED_DROP == 1 ]]; then rm -f "$DROP"; systemctl daemon-reload || true; fi
    if [[ $CHANGED == 1 ]]; then
      cp -p "$D/gateway.before" "$GW"
      systemctl restart "$SERVICE" || echo 'ROLLBACK_GATEWAY_RESTART_FAILED'
    fi
    if [[ $ADDED_MODULE == 1 ]]; then rm -f "$MOD"; fi
  fi
  rm -rf "$D"
  exit "$rc"
}
trap cleanup EXIT
systemctl is-active --quiet "$SERVICE"
systemctl is-active --quiet judun-staging-pull.timer
systemctl is-active --quiet judun-staging-isolated.service
[[ $(systemctl show "$QA" -p LoadState --value) == loaded ]]
[[ $(systemctl show "$QA" -p ActiveState --value) == inactive ]]
systemctl show judun-staging-pull.service -p OnSuccess --value | grep -qw "$QA"
fetch() { curl -fsSL --proto '=https' --tlsv1.2 --retry 2 --max-time 30 "$BASE/$1" -o "$D/$2"; }
fetch f8c533a54de669c7d486917c660dfd73c3895b64/ops/qa/qa_receipt_summary.py qa_receipt_summary.py
echo "b2443e0590b028e0efef9f8494e146bbf6d3f697507fc7c254f57efc22c866e7  $D/qa_receipt_summary.py" | sha256sum -c -
fetch 46cceca50177d094ec81b8f0548bffa7bc7f4262/ops/stage_health_oidc_gateway.py gateway.base
python3 - "$D" "$G" "$GW" "$MOD" "$EXPORT" "$DROP" <<'PY'
import hashlib, pathlib, stat, sys
D,G,GW,MOD,EXPORT,DROP=map(pathlib.Path,sys.argv[1:])
def need(x,code):
    if not x: raise SystemExit('STOP: '+code)
def safe(p,kind):
    s=p.lstat(); need(s.st_uid==0 and not(s.st_mode&0o022) and kind(s.st_mode),'UNSAFE_PATH')
safe(G,stat.S_ISDIR); safe(GW,stat.S_ISREG)
for p in (MOD,DROP):
    if p.exists() or p.is_symlink(): safe(p,stat.S_ISREG)
for p in (EXPORT,DROP.parent):
    if p.exists() or p.is_symlink(): safe(p,stat.S_ISDIR)
old=(D/'gateway.base').read_bytes()
need(hashlib.sha1(('blob '+str(len(old))+'\0').encode()+old).hexdigest()=='78168a8e4186721236e343773b35a95a857e2880','GATEWAY_SOURCE_PIN')
a=b'import base64\n'; b=b'            body = json.dumps(health_get(ROUTES[self.path]),\n'
need(old.count(a)==old.count(b)==1,'GATEWAY_PATCH_ANCHOR')
new=old.replace(a,a+b'import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parent))\nfrom qa_receipt_summary import decorate as qa_decorate\n').replace(b,b'            path = ROUTES[self.path]\n            result = health_get(path)\n            if path == "/health/build":\n                result = qa_decorate(result)\n            body = json.dumps(result,\n')
compile(new,'gateway.py','exec'); need(GW.read_bytes() in (old,new),'GATEWAY_BASE_MISMATCH')
(D/'gateway.new').write_bytes(new)
if MOD.exists(): need(MOD.read_bytes()==(D/'qa_receipt_summary.py').read_bytes(),'MODULE_MISMATCH')
PY
cat > "$D/95-receipt-summary.conf" <<'UNIT'
[Service]
ReadWritePaths=/srv/judun-stage-health-oidc/qa-summary
ExecStartPost=/usr/bin/python3 -I -B /srv/judun-stage-health-oidc/qa_receipt_summary.py
UNIT
if [[ -e "$DROP" ]]; then cmp -s "$DROP" "$D/95-receipt-summary.conf" || { echo 'STOP: DROPIN_MISMATCH'; exit 1; }; fi
if [[ ! -e "$MOD" ]]; then install -m 644 "$D/qa_receipt_summary.py" "$MOD"; ADDED_MODULE=1; fi
install -d -m 755 "$EXPORT" "${DROP%/*}"
# Only a previously attested PASS record may be published. This is read-only for the app.
python3 -I -B "$MOD"
if [[ ! -e "$DROP" ]]; then install -m 644 "$D/95-receipt-summary.conf" "$DROP"; ADDED_DROP=1; fi
systemd-analyze verify "$QA" "$SERVICE"
if ! cmp -s "$GW" "$D/gateway.new"; then
  cp -p "$GW" "$D/gateway.before"
  # Preserve a root-only rollback copy across successful installation.
  B=/var/backups/judun-qa-receipt-gateway
  [[ ! -L "$B" ]]; install -d -m 700 "$B"
  cp -p "$GW" "$B/gateway.$(date +%s).py"
  CHANGED=1
  install -m 644 "$D/gateway.new" "$GW"
fi
systemctl daemon-reload
if [[ $CHANGED == 1 ]]; then systemctl restart "$SERVICE"; fi
# Check the unchanged authorization boundary on all old routes.
for path in 'health/build' 'health/artifact?deep=true' 'health/ready'; do
  ok=0
  for attempt in 1 2 3 4 5; do
    code=$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:18762/__jd_stage_health/v1/$path" || true)
    if [[ $code == 403 ]]; then ok=1; break; fi
    sleep 1
  done
  [[ $ok == 1 ]] || { echo 'STOP: OIDC_ANONYMOUS_BOUNDARY'; exit 1; }
done
systemctl is-active --quiet "$SERVICE"
systemctl show "$QA" -p ExecStartPost --value | grep -Fq "$MOD"
systemctl is-active --quiet judun-staging-isolated.service
systemctl is-active --quiet judun-staging-pull.timer
KEEP=1
echo 'NATIVE_QA_RECEIPT_READBACK_ENABLED; AUTHENTICATED_CI_PROOF_PENDING'
