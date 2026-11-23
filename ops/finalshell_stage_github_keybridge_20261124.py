#!/usr/bin/env python3
"""One-time FinalShell GitHub deploy-key bridge, pinned for Judun staging only.

Interactive: register the displayed PUBLIC key in the repository Deploy Keys UI.
Private material never leaves the VPS, is never committed, and is never printed.
"""
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

DIR = Path("/root/.ssh")
KEY = DIR / "judun_stage_repo_ed25519"
HOSTS = DIR / "judun_stage_github_known_hosts"
HOST_KEY = "[ssh.github.com]:443 ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl"
GITHUB_SETTINGS = "https://github.com/momopuke/judun-deploy/settings/keys"
UPLOADER_URL = ("https://raw.githubusercontent.com/momopuke/judun-deploy/"
                "3902bdfa332b0c7413fa65d0d7de955c60ef1b9d/"
                "ops/finalshell_ship_signed_stage_candidates_20261123.py")
UPLOADER_SHA256 = "0b20db3835ee6227f55b74100191e63de98bb3a961d3339fdc577a48854b3d79"
SSH_COMMAND = (
    f"ssh -i {KEY} -o IdentitiesOnly=yes -o UserKnownHostsFile={HOSTS} "
    "-o StrictHostKeyChecking=yes -o BatchMode=yes "
    "-o ConnectTimeout=15 -o HostName=ssh.github.com -p 443"
)

def stop(code):
    raise SystemExit("STOP: " + code)

def validate(path, private=False):
    if path.is_symlink() or not path.is_file():
        stop("NOT_REGULAR_" + path.name)
    st = path.stat()
    if st.st_uid != 0 or st.st_mode & (0o077 if private else 0o022):
        stop("UNSAFE_PERMISSIONS_" + path.name)

def make_key():
    if os.geteuid() != 0:
        stop("ROOT_REQUIRED")
    os.umask(0o077)
    if DIR.is_symlink():
        stop("SSH_FOLDER_SYMLINK")
    DIR.mkdir(mode=0o700, exist_ok=True)
    if DIR.stat().st_uid != 0 or DIR.stat().st_mode & 0o077:
        stop("SSH_FOLDER_PERMISSIONS")
    public = KEY.with_suffix(".pub")
    if not KEY.exists() and not public.exists():
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-a", "100",
                        "-N", "", "-C", "judun-stage-vps-repo-deploy-20261124",
                        "-f", str(KEY)], check=True, timeout=25)
    elif not (KEY.is_file() and public.is_file()):
        stop("EXISTING_KEY_PAIR_INCOMPLETE")
    validate(KEY, private=True)
    validate(public)
    derived = subprocess.check_output(["ssh-keygen", "-y", "-P", "", "-f", str(KEY)], timeout=15)
    displayed = public.read_bytes()
    if derived.split()[:2] != displayed.split()[:2]:
        stop("DEPLOY_KEY_PUBLIC_PRIVATE_MISMATCH")
    if HOSTS.exists():
        validate(HOSTS, private=True)
        if HOSTS.read_text().strip() != HOST_KEY:
            stop("GH_HOST_PIN_MISMATCH")
    else:
        HOSTS.write_text(HOST_KEY + "\n")
        HOSTS.chmod(0o600)
        validate(HOSTS, private=True)
    print("\n=== GITHUB PUBLIC DEPLOY KEY (ONLY PUBLIC) ===", flush=True)
    print(displayed.decode().strip(), flush=True)
    print("=== END PUBLIC KEY ===", flush=True)
    print("\nOpen this repository's Deploy keys settings:", flush=True)
    print(GITHUB_SETTINGS, flush=True)
    print("Choose Add deploy key; paste the public key above;", flush=True)
    print("Title: judun-stage-vps-20261124 ; CHECK 'Allow write access'; save.", flush=True)
    print("Do NOT paste the private key or any password into ChatGPT.", flush=True)

def wait_and_ship():
    try:
        with open("/dev/tty", "r+", encoding="utf-8") as tty:
            tty.write("\nAfter saving the deploy key in GitHub, press ENTER here to continue: ")
            tty.flush()
            if tty.readline() == "":
                stop("TTY_CLOSED_BEFORE_AUTHORIZATION")
    except OSError:
        stop("NO_INTERACTIVE_FINALSHELL_TTY")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never",
               GIT_SSH_COMMAND=SSH_COMMAND)
    p = subprocess.run(["git", "ls-remote", "--heads",
                        "git@github.com:momopuke/judun-deploy.git", "refs/heads/main"],
                       env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=70)
    if p.returncode or not p.stdout.strip():
        err = p.stderr.decode("utf-8", "replace")
        if "Permission denied (publickey)" in err:
            stop("DEPLOY_KEY_NOT_REGISTERED_OR_NOT_AUTHORIZED")
        if "Host key verification failed" in err:
            stop("GITHUB_SSH_HOST_KEY_VERIFICATION_FAILED")
        stop("GITHUB_SSH_443_CONNECTION_FAILED")
    print("GITHUB_REPO_SCOPED_DEPLOY_KEY_READ_AUTH=PASS", flush=True)
    with urlopen(Request(UPLOADER_URL, headers={"User-Agent": "JudunStageDeploy/1"}),
                 timeout=40) as response:
        if response.status != 200 or response.geturl() != UPLOADER_URL:
            stop("UPLOADER_REDIRECT_OR_STATUS")
        body = response.read(32 * 1024)
    if hashlib.sha256(body).hexdigest() != UPLOADER_SHA256:
        stop("UPLOADER_SHA256_PIN_MISMATCH")
    with tempfile.TemporaryDirectory(prefix="judun-gh-keyship-", dir="/root") as tmp:
        program = Path(tmp) / "operator.py"
        program.write_bytes(body)
        print("UPLOADER_FIXED_SHA256=PASS", flush=True)
        r = subprocess.run(["python3", "-I", "-B", str(program)],
                           env=env, stdin=subprocess.DEVNULL, timeout=900, check=False)
        if r.returncode:
            stop("SIGNATURED_STAGE_CANDIDATE_UPLOAD_FAILED")
    print("GITHUB_STAGE_UPLOAD_BRIDGE=PASS", flush=True)
    print("FULL_AUTOMATED_RELEASE=NOT_YET_VERIFIED", flush=True)

def main():
    make_key()
    wait_and_ship()

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as e:
        stop("ONE_TIME_BRIDGE_" + type(e).__name__)
