#!/usr/bin/env bash
# Judun one-time QA encrypted export install. No production or staging deploy.
set -Eeuo pipefail
umask 077
D=$(mktemp -d); trap 'rm -rf "$D"' EXIT
base64 -d > "$D/bundle.tar.gz" <<'PAYLOAD'
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
nPXNltWTr5rGOOGcvr2MX3plUCONwVk3p7SHd14jf+e03vVVId8dX5fbnbuy8TLOSh65ur7vDDt+tjFtF+/rpdPqXeLhLDcvX3vDlzfzXunXB92zr6609AZS
v9+fHEn+qD7qvVyNh6eXp1e5yWwyvTnKl7P5B0frG4ve/TTROmuP8mW/4N5M2pXFvHCT/9Amdna0spZVuTifW6uHXu3h6rJZbBwtruvSfNX9KN+c5ksgHKyj
/kOi1z227++vTF9/1o8uc6P5uH7f8QrTu4ItST5sXO1B8opn99Zi0G6ZdtFqdzrto0Wjd9Ty5061mvCUU1MnzVdn9va86M210vVkPumPlQ85u+g5i8uHamEg
Hd1nV/3SkTN4Nk+f9Yp1uciWX0rGaJqTE9WeotSUo2Zp+vXhY+KdFDud65zpdlvzZv1WmcxWdq0rTVsVSWo8Dz8qvVYlhxyo16bXt5XKoJ04nd+dvRXN485U
0e86Lw85oudrykfl+kOaVKbtm8t+S27UpNspAO+DTQTAXQoM40uTU7kykGrS9WW2JeUa1f5Lo6+MirVruVJ9G0pSSalMr6tnd7nn5tn4spb4qOQmnclDqeh3
3itfm/Vhszw7eba157uX0nQwOVk+9xaLHpko7m335aN1O1m9t8rjh+fjk+n7UdUbJ276o7uqU+4XTxuNu47urspV3XnPfh10pOdxcXXfm01uq6VSrjI7epfO
HONk3By3Ox+j2l2FNP3WMuHNrquF57dCq3iSz2knfclf3J40ev1KW5emr9lBftB0dfm1/v7xOjz5umwsXOfSap1Y8tnH88Np8TYhFduOfXpETm+L5qpXlR4+
VitYxHBqmlfL2cfc7tbfBjfN/GL+8dCtd1dl17fvSlZ2OtNKlYfmMuG0y50byztrnvVuqo7Xa3kv/mrpTMbdXjXfUMp3Jzm5XtAm16+949lry7zTuvrx/PRS
spbP5PiklSjcnHSHp42vtZr70rp/Gzs9azRzsuQ9156bjUW/KTXmN4tC035/GB4Z73NvdLZYWlVjXlDcXqs1Snx0jr+26w2tV5SbV6euOby8Ou3cXX3cZ0uT
m7Oz+ZlUK96/VZ1h3el3rav5rFnW3nKX2XK7OX1/LecSL8f28fDluGssx5OWNSy6xknLv71vvJcLtyfG9G22NPPEUpwb++Ry1Rrdrt6HrUZlKiaoUJfbtV1B
fzCD/m3LZ++yCOBtvRpj8gfYf/ny8fbv/4H5Vz7Yf39EeRxahv+UqEVelg5e/NoXDWRxwsirXxj8SkgTcLfF4GcAMR5mWEQAqk6Jz8XfbVpfzAi4K3Gr4cWy
vV0TVdvSDcQI/XqZZpnF3XeqstuXPRKJxz4b/SkxwJeRbYvgZeGE/E7GffwxIXH9yts6KFfhfvgmWHb7NclEH++WrrPZ4mcdt+Dofc3cSS6XGLY0by7mcicn
ieDGJkWtT8bi8cKwEvLmxwzE7v3gstNud4Z9uddXBrKYT3Rd24ch+yvPJwuRpVfDykt7wS5Y0NBkIvgdx8HCwZuiibbdJm9YZ5hkSjxaF3S8Iq5FzMGS0nFP
C2C/3GqAPfJd22zgSx2soUcYNv2hUus3lFqsUtJ1/B2eurYwTANGkurqsK3ccfCptOVB+HmcUCz83UbPMwAT3H5PzNC32t7e3rKa/gp77nKZDTNwmfg7b5Hv
G+j4W3H4Fhx7eQuw0/Rb/BUCNtMeHqMXabgfvLDHIBItssBd1t7F4mmplah2h9dL29fEYvk/EgPYcI82FRL/B+Q/xtrdP8T/zxVL2/5/8bh8cpD//yL53xmh
dCbcxLDobaN4NggjwoxFIkkQGvQEGcYtNAt/d5WFRz0QxSjc3KdEx6rYNpVuRZRuHQunxUOO4ep1tTQeL11tvMKKfNlLIJD4WxYKTKJYeE/GfKLqhOiVFX1X
wvVCTXIw8w7lUA7lUA7lUA7lUA7lUA7lUA7lUA7lUA7lUA7lUA7lUA7lUA7lUA7lUA7l/3n5b96uriIAeAAA
PAYLOAD
printf '%s  %s\n' '6f4b42e963bedcd4dd3187bf962a986d702b16422dd5b52454e3bfd208b7061e' "$D/bundle.tar.gz" | sha256sum -c -
mkdir "$D/src"; tar -xzf "$D/bundle.tar.gz" -C "$D/src" --no-same-owner --no-same-permissions
S="$D/src"
python3 -B - "$S" <<'PY'
import ast,sys,pathlib
for p in pathlib.Path(sys.argv[1]).glob('*.py'):ast.parse(p.read_text())
print('INSTALLER_EMBEDDED_AST=PASS')
PY
if [[ ${1:-} == --self-test ]]; then exit 0; fi
[[ $# == 0 && $(id -u) == 0 ]] || { echo 'STOP: ROOT_REQUIRED'; exit 1; }
for x in git ssh openssl systemctl systemd-analyze curl; do command -v "$x" >/dev/null; done
systemctl is-active --quiet judun-staging-isolated.service
systemctl is-active --quiet judun-staging-pull.timer
systemctl is-active --quiet judun-autodeploy.timer
TREE=f264d49a458994f80125633afbbd0591ac2520fb014d7786aaff77003dde5886
RECEIPT=6017b2cc6029868e21e16f6159d511466f7b43cd1ad0442d04f3e71768b9bb85
ART=JUDUN-1.2.193-LIVE-ITEM-PROGRESS-20261125
[[ $(readlink /srv/judun-staging/current) == releases/$ART-$TREE ]] || { echo 'STOP: STAGE_BASELINE_CHANGED'; exit 1; }
printf '%s  %s\n' "$RECEIPT" "/var/lib/judun-stage-business-qa/$TREE.receipt.json" | sha256sum -c -
prod_check(){ curl -fsS --max-time 10 https://judun.142-93-91-214.sslip.io/health/build | python3 -c 'import json,sys; d=json.load(sys.stdin); assert str(d.get("version", "")).lstrip("v")=="1.2.193" and d.get("source_tree_sha256")=="f264d49a458994f80125633afbbd0591ac2520fb014d7786aaff77003dde5886" and d.get("payment_mode")=="ecpay_live"; print("PROD_V193_IDENTITY_PRESERVED=PASS")'; }
prod_check
T=/opt/judun-qa-envelope-export
U=/etc/systemd/system/judun-qa-envelope-export.service
M=/etc/systemd/system/judun-qa-envelope-export.timer
STATE=/var/lib/judun-qa-envelope-export
[[ ! -L "$T" && ! -L "$STATE" && ! -L "$U" && ! -L "$M" ]] || { echo 'STOP: UNSAFE_PATH'; exit 1; }
NEW_T=0; NEW_U=0; NEW_M=0; KEEP=0; ENABLED=0
cleanup(){
  rc=$?; trap - EXIT
  if [[ $KEEP == 0 ]]; then
    if [[ $ENABLED == 1 ]]; then systemctl disable --now judun-qa-envelope-export.timer >/dev/null 2>&1 || true; fi
    if [[ $NEW_M == 1 ]]; then rm -f "$M"; fi
    if [[ $NEW_U == 1 ]]; then rm -f "$U"; fi
    if [[ $NEW_T == 1 ]]; then rm -f "$T"/{qa_evidence_transport.py,export_worker.py,workflow.yml,recipient.pem}; rmdir "$T" || true; fi
    systemctl daemon-reload || true
    echo 'QA_EXPORT_INSTALL=HOLD; production and prior QA unchanged; retry preserves private export state'
  fi
  rm -rf "$D"; exit "$rc"
}
trap cleanup EXIT
if [[ -e "$T" ]]; then
  [[ $(stat -c '%u:%a' "$T") == 0:700 ]] || exit 2
  for n in qa_evidence_transport.py export_worker.py workflow.yml recipient.pem; do [[ -f "$T/$n" && ! -L "$T/$n" ]] && cmp -s "$S/$n" "$T/$n" || { echo 'STOP: EXISTING_EXPORT_TOOL_DIFFERS'; exit 2; }; done
else
  install -d -o root -g root -m 700 "$T"; NEW_T=1
  for n in qa_evidence_transport.py export_worker.py workflow.yml recipient.pem; do install -o root -g root -m 600 "$S/$n" "$T/$n"; done
fi
for p in "$U" "$M"; do if [[ -e "$p" ]]; then cmp -s "$S/${p##*/}" "$p" || { echo 'STOP: EXISTING_EXPORT_UNIT_DIFFERS'; exit 2; }; fi; done
if [[ ! -e "$U" ]]; then install -m 644 "$S/${U##*/}" "$U"; NEW_U=1; fi
if [[ ! -e "$M" ]]; then install -m 644 "$S/${M##*/}" "$M"; NEW_M=1; fi
systemd-analyze verify "$U" "$M"
systemctl daemon-reload
P="$STATE/$TREE-$RECEIPT/published.json"
for i in 1 2 3 4 5 6; do
  if ! systemctl start judun-qa-envelope-export.service; then journalctl -u judun-qa-envelope-export.service -n 12 --no-pager -o cat; exit 2; fi
  [[ -f "$P" ]] && break
  sleep 5
done
[[ -f "$P" && ! -L "$P" ]] || { echo 'STOP: EXPORT_READBACK_MISSING'; exit 2; }
python3 - "$P" "$TREE" "$RECEIPT" <<'PY'
import json,re,sys
p,tree,receipt=sys.argv[1:];d=json.load(open(p));assert d['tree']==tree and d['native_receipt_sha256']==receipt and re.fullmatch('[a-f0-9]{40}',d['commit']);print('QA_EXPORT_REMOTE_COMMIT='+d['commit']);print('QA_EXPORT_CIPHERTEXT_SHA256='+d['ciphertext_sha256'])
PY
prod_check
if ! systemctl is-enabled --quiet judun-qa-envelope-export.timer; then ENABLED=1; fi
systemctl enable --now judun-qa-envelope-export.timer
systemctl is-active --quiet judun-qa-envelope-export.timer
KEEP=1
echo 'QA_EXPORT_TIMER_ENABLED=PASS'
echo 'QA_EXPORT_V193_SMOKE_REMOTE_READBACK=PASS'
echo 'NEXT: independently download and decrypt Actions artifact; full automation not yet verified'
