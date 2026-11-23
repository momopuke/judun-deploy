#!/usr/bin/env python3
"""Upload two pre-signed, encrypted, stage-only candidates to immutable GitHub commits.

No edits to production, main, channel/stable, staging-request or running services.
Git pushes require an existing GitHub write credential; never prompt for one.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from zipfile import ZipFile

REPO = "https://github.com/momopuke/judun-deploy.git"
SSH_REPO = "git@github.com:momopuke/judun-deploy.git"
MAIN = "438b2a58ccd56330fd76059b5e8531955d16503c"
ARCHIVE = Path("/root/JUDUN_FinalShell_StageRollback_OneClick_20261123.zip")
ARCHIVE_SHA = "a51b08642d885b156771290e44e6948a248581c83fc16496323bd4e549de028b"
INNER_SHA = "ed3ca4a6d5656486190efd4239905867fac9d725334b90f587127eb2d8a123c6"
PUB = Path("/etc/judun-staging-pull/release_signing_public.pem")
PUB_SHA = "17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db"
STAGE = Path("/srv/judun-staging")
EXPECTED = (
    ("01_v190_to_v189", "JUDUN-1.2.190-SINGLEPASS-RC1-UNSIGNED-1d5a73989525643a4da6c58b36263bdcc644a3f3780fb335b968e33e7de7866a",
     "JUDUN-1.2.189-CODEX20261117-ca831e119db0ff9d35a114ef6ee52edc55c1ba4cf6598a9ddc0b986e2029ca4d",
     "stage-drill/v190-to-v189-20261123"),
    ("02_v189_to_v190", "JUDUN-1.2.189-CODEX20261117-ca831e119db0ff9d35a114ef6ee52edc55c1ba4cf6598a9ddc0b986e2029ca4d",
     "JUDUN-1.2.190-SINGLEPASS-RC1-UNSIGNED-1d5a73989525643a4da6c58b36263bdcc644a3f3780fb335b968e33e7de7866a",
     "stage-drill/v189-to-v190-20261123"),
)
EVIDENCE = Path("/root/judun-stage-drill-evidence/signed-stage-drill-20261123T125300Z.json")
TIME = "2026-11-23T12:53:00+00:00"
DEPLOY_KEY = Path("/root/.ssh/judun_stage_repo_ed25519")
KNOWN_HOSTS = Path("/root/.ssh/judun_stage_github_known_hosts")
GITHUB_HOST_KEY = "[ssh.github.com]:443 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
SSH_COMMAND = (
    f"ssh -i {DEPLOY_KEY} -o IdentitiesOnly=yes "
    f"-o UserKnownHostsFile={KNOWN_HOSTS} -o StrictHostKeyChecking=yes "
    "-o BatchMode=yes -o ConnectTimeout=15 -o HostName=ssh.github.com -p 443"
)
ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never",
           GIT_SSH_COMMAND=SSH_COMMAND)

def stop(reason):
    print("STOP: " + reason, flush=True)
    raise SystemExit(2)

def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def git(*parts, repo=None, timeout=180, check=True, env=None):
    args = ["git"] + (["-C", str(repo)] if repo else []) + list(parts)
    result = subprocess.run(args, env=(env or ENV), capture_output=True,
                            timeout=timeout, check=False)
    if check and result.returncode:
        stop("GIT_" + str(parts[0]).upper().replace("-", "_") + "_FAILED")
    return result

def extract(zipf, path, out):
    with zipf.open(path) as src, out.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)

def ensure_root_file(file, expected=None):
    st = file.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
        stop("UNTRUSTED_LOCAL_FILE_" + file.name)
    if expected and sha(file) != expected:
        stop("SHA_PIN_" + file.name)

def preflight():
    if os.geteuid() != 0:
        stop("ROOT_REQUIRED")
    if not shutil.which("git") or not shutil.which("openssl") or not shutil.which("ssh"):
        stop("GIT_OPENSSL_OR_SSH_MISSING")
    if not DEPLOY_KEY.is_file() or not KNOWN_HOSTS.is_file():
        stop("GITHUB_DEPLOY_KEY_NOT_INSTALLED")
    ensure_root_file(DEPLOY_KEY)
    ensure_root_file(KNOWN_HOSTS)
    if DEPLOY_KEY.stat().st_mode & 0o077:
        stop("DEPLOY_KEY_PERMISSIONS_NOT_0600")
    if KNOWN_HOSTS.read_text().strip() != GITHUB_HOST_KEY:
        stop("GITHUB_HOST_PUBLIC_KEY_PIN_MISMATCH")
    if shutil.disk_usage("/root").free < 600 * 1024 * 1024:
        stop("DISK_BELOW_600MB")
    for f, dig in ((ARCHIVE, ARCHIVE_SHA), (PUB, PUB_SHA)):
        ensure_root_file(f, dig)
    ensure_root_file(EVIDENCE)
    e = json.loads(EVIDENCE.read_text())
    if (e.get("schema") != "judun.local-signed-stage-drill.v1"
        or e.get("result") != "PASS"
        or e.get("real_stage_downgrade") != "PASS"
        or e.get("real_stage_restore") != "PASS"
        or e.get("formal_production_unchanged") is not True
        or e.get("github_pointer_modified") is not False
        or e.get("original_stage_final") != EXPECTED[0][1]
        or e.get("stage_db_backup", {}).get("state") != "PASS"):
        stop("SIGNED_REAL_DRILL_RECEIPT_NOT_PASS")
    for svc in ("judun-staging-isolated.service", "judun-staging-pull.timer", "judun-autodeploy.timer"):
        p = subprocess.run(["systemctl", "is-active", "--quiet", svc], timeout=12)
        if p.returncode:
            stop("SERVICE_NOT_ACTIVE_" + svc)
    if not (STAGE / "current").is_symlink():
        stop("STAGE_POINTER_MISSING")
    if (STAGE / "current").readlink().as_posix() != "releases/" + EXPECTED[0][1]:
        stop("STAGE_NOT_ORIGINAL_V190")
    print("PINNED_ZIP_AND_REAL_STAGE_RECEIPT=PASS", flush=True)

def verify_part(src, folder, targetdir, base, target):
    raw = src.read(folder + "/candidate.json")
    signature = base64.b64decode(b"".join(src.read(folder + "/candidate.json.sig.b64").split()), validate=True)
    if len(signature) != 64:
        stop("BAD_SIGNATURE_LENGTH_" + folder)
    manifest = json.loads(raw)
    if (set(manifest) != {"schema","base_snapshot","target","cms_sha256","zip_sha256"}
            or manifest["schema"] != "judun.staging-deploy.v1"
            or manifest["base_snapshot"] != base
            or (manifest["target"]["artifact_id"] + "-" + manifest["target"]["source_tree_sha256"]) != target
            or manifest["target"]["file_count"] != 98):
        stop("CANDIDATE_IDENTITY_MISMATCH_" + folder)
    manifest_file = targetdir / "candidate.json"
    sig_file = targetdir / "candidate.json.sig.b64"
    cms_file = targetdir / "candidate.cms"
    manifest_file.write_bytes(raw)
    sig_file.write_bytes(base64.b64encode(signature) + b"\n")
    extract(src, folder + "/candidate.cms", cms_file)
    if sha(cms_file) != manifest["cms_sha256"]:
        stop("CMS_SHA_MISMATCH_" + folder)
    raw_sig = targetdir / "signature.raw"
    raw_sig.write_bytes(signature)
    result = subprocess.run(["openssl","pkeyutl","-verify","-pubin","-inkey",str(PUB),
                             "-rawin","-in",str(manifest_file),"-sigfile",str(raw_sig)],
                            capture_output=True, timeout=30)
    raw_sig.unlink()
    if result.returncode:
        stop("ORIGINAL_ED25519_SIGNATURE_INVALID_" + folder)
    print(folder.upper() + "_ED25519_AND_CMS_SHA=PASS", flush=True)

def main():
    lock = Path("/root/.judun-stage-github-ship.lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        stop("UPLOAD_ALREADY_RUNNING")
    preflight()
    with tempfile.TemporaryDirectory(prefix="judun-github-stage-", dir="/root") as t:
        tmp = Path(t)
        inner = tmp / "signed.zip"
        with ZipFile(ARCHIVE) as outer:
            if outer.testzip():
                stop("OUTER_ZIP_CORRUPT")
            extract(outer, "signed_payload.zip", inner)
        if sha(inner) != INNER_SHA:
            stop("SIGNED_INNER_ZIP_SHA_MISMATCH")
        work = tmp / "repository"
        work.mkdir()
        git("init", "-q", str(work), timeout=30)
        git("remote", "add", "origin", REPO, repo=work)
        git("fetch", "--depth=1", "--filter=blob:none", "origin", "refs/heads/main", repo=work, timeout=180)
        sha_main = git("rev-parse", "FETCH_HEAD", repo=work).stdout.decode().strip()
        if sha_main != MAIN:
            stop("PROTECTED_MAIN_MOVED_REVERIFY_BEFORE_UPLOAD")
        request = git("show", "FETCH_HEAD:ops/staging-request.json", repo=work).stdout
        if json.loads(request) != {"candidate_commit": None}:
            stop("STAGE_REQUEST_NOT_NULL")
        git("config", "core.sparseCheckout", "true", repo=work)
        info = work / ".git" / "info" / "sparse-checkout"
        info.write_text("staging/\n")
        git("checkout", "-q", "-b", "stage-drill-local", "FETCH_HEAD", repo=work)
        git("config", "user.name", "Judun Stage Operator", repo=work)
        git("config", "user.email", "judun-stage-operator@users.noreply.github.com", repo=work)
        staging = work / "staging"
        staging.mkdir(exist_ok=True)
        commits = []
        with ZipFile(inner) as z:
            if z.testzip():
                stop("INNER_ZIP_CORRUPT")
            for folder, base, target, branch in EXPECTED:
                for name in ("candidate.json", "candidate.json.sig.b64", "candidate.cms"):
                    (staging / name).unlink(missing_ok=True)
                verify_part(z, folder, staging, base, target)
                git("-c", "core.autocrlf=false", "add", "--", "staging/candidate.json",
                    "staging/candidate.json.sig.b64", "staging/candidate.cms", repo=work)
                env = dict(ENV, GIT_AUTHOR_DATE=TIME, GIT_COMMITTER_DATE=TIME)
                git("-c", "commit.gpgsign=false", "commit", "-q",
                    "-m", "stage-only signed CMS " + folder, repo=work, env=env)
                commit = git("rev-parse", "HEAD", repo=work).stdout.decode().strip()
                if len(commit) != 40:
                    stop("INVALID_GIT_COMMIT_SHA")
                commits.append((folder, branch, commit))
        print("LOCAL_GIT_CANDIDATES_SIGNED=PASS", flush=True)
        for folder, branch, commit in commits:
            pushed = False
            for remote in (SSH_REPO,):
                git("remote", "set-url", "origin", remote, repo=work)
                result = git("push", "--porcelain", "origin",
                             commit + ":refs/heads/" + branch,
                             repo=work, timeout=180, check=False)
                if result.returncode == 0:
                    pushed = True
                    break
                error = result.stderr.decode("utf-8", "replace")
                if "Permission denied (publickey)" in error:
                    stop("GITHUB_DEPLOY_KEY_NOT_REGISTERED_OR_NO_ACCESS_" + folder)
                if "Repository not found" in error:
                    stop("GITHUB_DEPLOY_KEY_REPO_ACCESS_MISSING_" + folder)
                if "Host key verification failed" in error:
                    stop("GITHUB_HOST_KEY_VERIFICATION_FAILED_" + folder)
                if "Permission to " in error and "denied" in error:
                    stop("GITHUB_DEPLOY_KEY_WRITE_ACCESS_NOT_ENABLED_" + folder)
            if not pushed:
                stop("GITHUB_SSH_PUSH_REJECTED_CHECK_NETWORK_OR_BRANCH_RULE_" + folder)
            ref = git("ls-remote", "--heads", "origin", "refs/heads/" + branch,
                      repo=work, timeout=45).stdout.decode().strip().split()
            if not ref or ref[0] != commit:
                stop("GITHUB_REMOTE_REF_NOT_MATCH_" + folder)
            print(folder.upper() + "_GITHUB_IMMUTABLE_COMMIT=" + commit, flush=True)
        print("BOTH_STAGE_CANDIDATES_UPLOADED=PASS", flush=True)
        print("PROTECTED_MAIN_UNMODIFIED=PASS", flush=True)
        print("NEXT=PROTECTED_STAGE_REQUEST_PR_VIA_ORIGINAL_GITHUB_CONNECTOR", flush=True)

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError, TimeoutError, subprocess.SubprocessError) as e:
        stop("OPERATOR_PRECONDITION_OR_COMMAND_" + type(e).__module__ + "." + type(e).__name__ + " DETAILS=" + str(e)[:240].replace("\\n", " "))
