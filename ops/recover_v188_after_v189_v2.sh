#!/usr/bin/env bash
set -euo pipefail
umask 077

app=/var/www/advisor
agent=/opt/judun-autodeploy
work=$agent/work/program-rollback-v189
commit=d4df52d9054c0df8e7a650fd6847ea902e402584
release_id=v1.2.189-r18-2-20261117
remote="https://raw.githubusercontent.com/momopuke/judun-deploy/$commit"
key="$agent/keys/release_signing_public.pem"
base=JUDUN-1.2.188-RISKREVIEW20261115
target=JUDUN-1.2.189-CODEX20261116

[[ $EUID -eq 0 ]] || { echo "Run on the existing VPS as root." >&2; exit 1; }
systemctl cat advisor.service >/dev/null
exec 9>/run/lock/judun-autodeploy-agent.lock
flock -w 25 9 || { echo "The original deploy agent is still running." >&2; exit 1; }

live_artifact="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["artifact_id"])' "$app/DEPLOY_MANIFEST.json")"
if [[ $live_artifact != "$base" && $live_artifact != "$target" ]]; then
    echo "Unexpected on-disk build. No files were modified." >&2
    exit 1
fi

if [[ $live_artifact == "$target" || -f "$work/journal.json" ]]; then
    tmp=$(mktemp -d /run/judun-v188-recovery.XXXXXXXX)
    trap 'rm -rf -- "$tmp"' EXIT
    fetch() { curl -fsS --retry 2 --connect-timeout 8 --max-time 50 "$remote/$1" -o "$2"; }
    fetch channel/stable.json "$tmp/stable.json"
    fetch channel/stable.json.sig.b64 "$tmp/stable.sig.b64"
    fetch "releases/$release_id.cms.b64" "$tmp/release.cms.b64"
    base64 -d "$tmp/stable.sig.b64" > "$tmp/stable.sig"
    base64 -d "$tmp/release.cms.b64" > "$tmp/release.cms"
    openssl pkeyutl -verify -pubin -inkey "$key" -rawin -in "$tmp/stable.json" -sigfile "$tmp/stable.sig"
    python3 - "$tmp" "$release_id" "$base" "$target" <<'PY'
import hashlib, json, sys
from pathlib import Path
d = Path(sys.argv[1])
m = json.loads((d / "stable.json").read_bytes())
assert (m["release_id"], m["base_artifact_id"], m["target_artifact_id"]) == tuple(sys.argv[2:])
assert m["target_build_instance_id"] == "1.2.189-CODEX-CANDIDATE20261116"
assert hashlib.sha256((d / "release.cms").read_bytes()).hexdigest() == m["payload_sha256"]
PY
    openssl cms -decrypt -binary -inform DER -in "$tmp/release.cms" \
        -recip "$agent/keys/payload_encrypt_cert.pem" \
        -inkey "$agent/keys/payload_decrypt_private.pem" -out "$tmp/release.tar.gz"
    python3 - "$tmp" <<'PY'
import sys, tarfile
from pathlib import Path
d = Path(sys.argv[1])
with tarfile.open(d / "release.tar.gz") as z:
    for name in ("release.json", "base_manifest.json", "payload/DEPLOY_MANIFEST.json", "runtime_apply_v189.py"):
        entry = z.getmember(name)
        assert entry.isfile()
        dest = d / "release" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(z.extractfile(entry).read())
PY
    python3 - "$tmp/release" "$work" <<'PY'
import hashlib
import importlib.util
import json
import stat
import sys
from pathlib import Path

release, work = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("verified_recovery", release / "runtime_apply_v189.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)

journal_path = work / "journal.json"
backup_path = work / "backup.json"
if journal_path.is_file():
    for path in (journal_path, backup_path):
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0:
            raise SystemExit("RECOVERY_BACKUP_FILE_UNSAFE")
    journal = json.loads(journal_path.read_bytes())
    raw_backup = backup_path.read_bytes()
    if hashlib.sha256(raw_backup).hexdigest() != journal.get("backup_sha"):
        raise SystemExit("RECOVERY_BACKUP_DIGEST_MISMATCH")
    backup = json.loads(raw_backup)
    original = bytes.fromhex(backup["DEPLOY_MANIFEST.json"]["data"])
    actual = json.loads(original)
    signed = json.loads((release / "base_manifest.json").read_bytes())
    actual_rows = runtime.validate_manifest(actual, runtime.BASE_ID, "1.2.188", runtime.BASE_TREE, "tabs")
    signed_rows = runtime.validate_manifest(signed, runtime.BASE_ID, "1.2.188", runtime.BASE_TREE, "tabs")
    if actual_rows != signed_rows:
        raise SystemExit("RECOVERY_BASE_FILE_ROWS_MISMATCH")
    # Use the verified backup's original serialization for byte-exact rollback.
    # The pinned artifact, source tree, all file hashes and backup digest passed above.
    if (release / "base_manifest.json").read_bytes() != original:
        (release / "base_manifest.json").write_bytes(original)
        print("RECOVERY_BASE_MANIFEST_PINNED_FILES_MATCH")
PY
    JUDUN_SIMULATE=0 JUDUN_TEST_MODE=0 JUDUN_RELEASE_ID="$release_id" \
    JUDUN_BASE_ARTIFACT_ID="$base" JUDUN_TARGET_ARTIFACT_ID="$target" \
    JUDUN_TARGET_BUILD_INSTANCE_ID=1.2.189-CODEX-CANDIDATE20261116 \
        python3 "$tmp/release/runtime_apply_v189.py" recover --root "$app" \
        --release "$tmp/release" --work "$work"
fi

systemctl restart advisor.service
for _ in {1..20}; do
    if curl -fsS --max-time 5 'http://127.0.0.1:8000/health/artifact?deep=true' | python3 -c '
import json, sys
try:
    a = json.load(sys.stdin)
except ValueError:
    raise SystemExit(1)
assert (a["artifact_id"], a["files_verified"], a["mismatch_count"]) == ("JUDUN-1.2.188-RISKREVIEW20261115", 88, 0)
print("JUDUN_RECOVERY_OK v1.2.188 88/88")
'; then
        exit 0
    fi
    sleep 2
done

echo "The old build was not verified. Check advisor.service on the VPS." >&2
exit 1
