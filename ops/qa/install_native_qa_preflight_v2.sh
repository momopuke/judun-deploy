#!/usr/bin/env bash
# Install an additional narrowly-scoped staging QA service entry. Never deploy or run QA.
set -Eeuo pipefail
umask 077
[[ $(id -u) == 0 && $# == 0 ]] || { echo 'HOLD:ROOT_REQUIRED'; exit 2; }
D=$(mktemp -d)
T=/opt/judun-stage-qa-auto
U=judun-stage-native-qa-auto.service
DROP=/etc/systemd/system/$U.d/94-native-preflight-v2.conf
REV=3d2319f34cb1f3ed198c63733a720e64d85f66d4
BASE=https://raw.githubusercontent.com/momopuke/judun-deploy
NEW_L=0; NEW_S=0; NEW_D=0; KEEP=0
cleanup(){
  rc=$?
  trap - EXIT
  if [[ $KEEP == 0 ]]; then
    [[ $NEW_D == 0 ]] || rm -f "$DROP"
    [[ $NEW_S == 0 ]] || rm -f "$T/native_qa_preflight_service.py"
    [[ $NEW_L == 0 ]] || rm -f "$T/launcher_preflight_v2.py"
    [[ $NEW_D == 0 ]] || systemctl daemon-reload
  fi
  rm -rf "$D"; exit "$rc"
}
trap cleanup EXIT
for x in git curl python3 systemctl systemd-analyze flock sha256sum; do command -v "$x" >/dev/null; done
fetch(){
  curl -fsSL --proto '=https' --tlsv1.2 --retry 2 --max-time 45 "$BASE/$REV/ops/qa/$1" -o "$D/$2"
  [[ $(git hash-object "$D/$2") == "$3" ]] || { echo 'HOLD:SOURCE_PIN'; exit 2; }
}
fetch stage_native_qa_launcher_preflight_v2.py launcher_preflight_v2.py f914f457b47ed44a5928170e753f5f78dc95cc61
fetch native_qa_preflight_service.py native_qa_preflight_service.py 8f83490923e5b7ce5e58b914d299b894eac12ef1
python3 -m py_compile "$D/"*.py
python3 - "$T" "$DROP" <<'PY'
import pathlib,sys,stat,hashlib
t,drop=map(pathlib.Path,sys.argv[1:])
def need(ok,code):
    if not ok: raise SystemExit('HOLD:'+code)
def safe(p,kind,private):
    s=p.lstat();need(kind(s.st_mode) and s.st_uid==0 and not(s.st_mode&(0o077 if private else 0o022)),'UNSAFE_PATH')
    if kind==stat.S_ISREG:need(s.st_nlink==1,'UNSAFE_LINK')
safe(t,stat.S_ISDIR,True)
for name,h in {
    'auto.py':'452ed674c51edf848c7bd4b90c2a5e0be318baa115487cdac4f4804728aeb108',
    'launcher.py':'25e060c2ce7702a59edbf01f025ec8da50d82e1fc185d21eb689b543ff760dc2',
    'native_qa.py':'d9c28d573ca822129c6aa053912f85543d62616575a2ff87244eb55398814568',
}.items():
    p=t/name;safe(p,stat.S_ISREG,True);need(hashlib.sha256(p.read_bytes()).hexdigest()==h,'ORIGINAL_PIN')
summary=pathlib.Path('/srv/judun-stage-health-oidc/qa_receipt_summary.py')
safe(summary,stat.S_ISREG,False)
need(hashlib.sha256(summary.read_bytes()).hexdigest()=='b2443e0590b028e0efef9f8494e146bbf6d3f697507fc7c254f57efc22c866e7','SUMMARY_PIN')
safe(drop.parent,stat.S_ISDIR,False)
for p in (drop,t/'native_qa_preflight_service.py',t/'launcher_preflight_v2.py'):
    if p.exists() or p.is_symlink():safe(p,stat.S_ISREG,p!=drop)
for p in (pathlib.Path('/var/lib/judun-staging-pull/.lock'),pathlib.Path('/srv/judun-staging/.lock')):safe(p,stat.S_ISREG,True)
PY
exec 9<>/var/lib/judun-staging-pull/.lock
flock -n 9 || { echo 'HOLD:STAGE_PULL_BUSY'; exit 2; }
exec 8<>/srv/judun-staging/.lock
flock -n 8 || { echo 'HOLD:STAGE_BUSY'; exit 2; }
[[ $(systemctl show "$U" -p LoadState --value) == loaded ]]
case "$(systemctl show "$U" -p ActiveState --value)" in inactive|failed) ;; *) echo 'HOLD:NATIVE_QA_ACTIVE'; exit 2;; esac
systemctl is-active --quiet judun-staging-isolated.service
systemctl is-active --quiet judun-staging-pull.timer
systemctl is-active --quiet judun-autodeploy.timer
# Existing service sandbox and ExecStartPost must remain intact. No new
# privileges, no changes to any of the original files or other service units.
systemctl show "$U" -p ExecCondition --value | grep -Fq '/opt/judun-stage-qa-auto/auto.py --needs-run'
systemctl show "$U" -p ExecStartPost --value | grep -Fq '/srv/judun-stage-health-oidc/qa_receipt_summary.py'
systemctl show "$U" -p ProtectSystem --value | grep -qx strict
systemctl show "$U" -p NoNewPrivileges --value | grep -qx yes
cat > "$D/drop.conf" <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -I -B /opt/judun-stage-qa-auto/native_qa_preflight_service.py
UNIT
if [[ -e "$DROP" ]]; then
  cmp -s "$DROP" "$D/drop.conf" || { echo 'HOLD:DROPIN_MISMATCH'; exit 2; }
  systemctl show "$U" -p ExecStart --value | grep -Fq '/opt/judun-stage-qa-auto/native_qa_preflight_service.py'
else
  systemctl show "$U" -p ExecStart --value | grep -Fq '/opt/judun-stage-qa-auto/auto.py'
fi
if [[ -e "$T/launcher_preflight_v2.py" ]]; then
  cmp -s "$D/launcher_preflight_v2.py" "$T/launcher_preflight_v2.py" || { echo 'HOLD:LAUNCHER_V2_DIFFERS'; exit 2; }
else
  install -o root -g root -m 700 "$D/launcher_preflight_v2.py" "$T/launcher_preflight_v2.py"; NEW_L=1
fi
if [[ -e "$T/native_qa_preflight_service.py" ]]; then
  cmp -s "$D/native_qa_preflight_service.py" "$T/native_qa_preflight_service.py" || { echo 'HOLD:SERVICE_V2_DIFFERS'; exit 2; }
else
  install -o root -g root -m 700 "$D/native_qa_preflight_service.py" "$T/native_qa_preflight_service.py"; NEW_S=1
fi
if [[ ! -e "$DROP" ]]; then
  install -o root -g root -m 644 "$D/drop.conf" "$DROP"; NEW_D=1
fi
systemd-analyze verify "$U"
systemctl daemon-reload
systemctl show "$U" -p ExecStart --value | grep -Fq '/opt/judun-stage-qa-auto/native_qa_preflight_service.py'
systemctl show "$U" -p ExecCondition --value | grep -Fq '/opt/judun-stage-qa-auto/auto.py --needs-run'
systemctl show "$U" -p ExecStartPost --value | grep -Fq '/srv/judun-stage-health-oidc/qa_receipt_summary.py'
systemctl show "$U" -p ProtectSystem --value | grep -qx strict
systemctl show "$U" -p NoNewPrivileges --value | grep -qx yes
KEEP=1
echo 'NATIVE_QA_PREFLIGHT_V2_INSTALLED_NO_QA_RUN'
echo 'REAL_FUTURE_PREFLIGHT_RECOVERY_NOT_YET_VERIFIED'
