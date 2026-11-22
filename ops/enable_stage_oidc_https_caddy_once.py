#!/usr/bin/env python3
"""Authorized, single-pass Caddy HTTPS ingress for the already-live Judun OIDC gateway.

Adds only an independent sslip.io hostname. Does not replace any existing
production vhost or edit the app, payment processor, Ed25519 signer or VPS agent.
If the live Caddy configuration cannot be established unambiguously, it stops.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener

HOST = "judun-oidc.142-93-91-214.sslip.io"
IP = "142.93.91.214"
PROD = "https://judun.142-93-91-214.sslip.io/health/build"
GATEWAY = "http://127.0.0.1:18762/__jd_stage_health/v1/health/build"
PUBLIC = "https://" + HOST + "/__jd_stage_health/v1/health/build"
PREFIX = "JD-STAGE-OIDC-HTTPS-V1"

# Separate new vhost, NOT an edit to the existing production hostname.
BLOCK = """
# JD-STAGE-OIDC-HTTPS-V1-BEGIN
judun-oidc.142-93-91-214.sslip.io {
    @jd_oidc_health {
        method GET
        path /__jd_stage_health/v1/health/build /__jd_stage_health/v1/health/artifact /__jd_stage_health/v1/health/ready
    }
    handle @jd_oidc_health {
        reverse_proxy 127.0.0.1:18762 {
            header_up Authorization {http.request.header.Authorization}
        }
    }
    handle {
        respond "Forbidden" 403
    }
}
# JD-STAGE-OIDC-HTTPS-V1-END
""".encode("ascii")


class Stop(RuntimeError):
    pass


def require(ok, name):
    if not ok:
        raise Stop(name)


def run(argv, timeout=15):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise Stop("SYSTEM_COMMAND_FAILED") from None
    return result


def checked(argv, code, timeout=15):
    result = run(argv, timeout)
    require(result.returncode == 0, code)
    return result.stdout


def no_proxy():
    return build_opener(ProxyHandler({}))


def response_code(url, timeout=8):
    try:
        with no_proxy().open(Request(url, headers={"Cache-Control":"no-store",
                              "User-Agent":"JudunOIDCInstallation/1"}), timeout=timeout) as r:
            return r.status, r.read(32769)
    except HTTPError as e:
        return e.code, b""


def validate_local():
    require(run(["systemctl", "is-active", "--quiet",
                 "judun-stage-health-oidc.service"]).returncode == 0,
            "GATEWAY_SERVICE_NOT_ACTIVE")
    try:
        code, _ = response_code(GATEWAY)
    except (URLError, OSError, TimeoutError):
        raise Stop("GATEWAY_NOT_REACHABLE") from None
    require(code == 403, "GATEWAY_MUST_REFUSE_ANONYMOUS")
    sockets = checked(["ss", "-H", "-lnt", "(", "sport", "=", ":18762", ")"],
                      "GATEWAY_SOCKET_CHECK_FAILED")
    require("127.0.0.1:18762" in sockets and
            "0.0.0.0:18762" not in sockets and "[::]:18762" not in sockets,
            "GATEWAY_NOT_LOOPBACK_ONLY")
    print("LOCAL_GATEWAY_HTTP_403_AND_LOOPBACK=PASS", flush=True)


def production_identity():
    try:
        code, raw = response_code(PROD, timeout=12)
        require(code == 200 and 0 < len(raw) < 32769, "PRODUCTION_HEALTH_UNAVAILABLE")
        health = json.loads(raw)
        require(isinstance(health, dict), "PRODUCTION_HEALTH_INVALID")
        fields = ("version", "artifact_id", "build_instance_id", "source_tree_sha256")
        require(all(isinstance(health.get(k), str) and health[k] for k in fields),
                "PRODUCTION_HEALTH_IDENTITY_MISSING")
        return {key: health[key] for key in fields}
    except (URLError, OSError, TimeoutError, ValueError):
        raise Stop("PRODUCTION_HEALTH_CHECK_FAILED") from None


def candidate_caddies(items):
    """Find host-network Caddy; host-writable files may be Docker RO binds."""
    result = []
    for obj in items:
        if not isinstance(obj, dict) or not obj.get("State", {}).get("Running"):
            continue
        conf = obj.get("Config") or {}
        desc = str(conf.get("Image", "")) + " " + str(obj.get("Name", ""))
        if "caddy" not in desc.lower():
            continue
        host = obj.get("HostConfig") or {}
        if host.get("NetworkMode") != "host":
            continue
        mounts = obj.get("Mounts") or []
        valid = []
        for m in mounts:
            if m.get("Type") != "bind":
                continue
            target = m.get("Destination", "")
            # A read-only *container* bind is fine: root updates the host
            # source in place, so Docker's pinned inode stays visible.
            # Directory binds still require RW; those use atomic replace.
            if target == "/etc/caddy/Caddyfile" and m.get("RW") in (True, False):
                valid.append((len(target), Path(m["Source"]), True))
            elif target == "/etc/caddy" and m.get("RW") is True:
                valid.append((len(target), Path(m["Source"]) / "Caddyfile", False))
        if valid:
            valid.sort(key=lambda item: item[0], reverse=True)
            result.append((obj["Id"], valid[0][1], valid[0][2]))
    return result


def find_active_caddy():
    ids = checked(["docker", "ps", "-q"], "DOCKER_UNAVAILABLE").splitlines()
    require(bool(ids), "NO_DOCKER_CONTAINERS")
    data = json.loads(checked(["docker", "inspect", *ids], "DOCKER_INSPECT_FAILED"))
    choices = candidate_caddies(data)
    require(len(choices) == 1, "CADDY_HOST_MOUNT_AMBIGUOUS")
    ident, config, file_bind = choices[0]
    require(len(ident) >= 12 and config.is_file() and not config.is_symlink(),
            "CADDY_CONFIG_NOT_REGULAR_BIND")
    mode = config.stat()
    require(mode.st_uid == 0 and stat.S_ISREG(mode.st_mode)
            and 0 < mode.st_size <= 262144,
            "CADDY_CONFIG_OWNER_OR_SIZE_INVALID")
    # Check host-side write access. Container RW=false does not imply that
    # the root-owned host source is unwritable, and does not require remount.
    # Opening without truncation is non-mutating; write_caddy_config still
    # validates ownership and preserves the existing file inode.
    try:
        fd = os.open(config, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    except OSError:
        raise Stop("CADDY_HOST_CONFIG_NOT_WRITABLE") from None
    try:
        opened = os.fstat(fd)
        require(opened.st_ino == mode.st_ino and opened.st_dev == mode.st_dev
                and opened.st_uid == 0 and stat.S_ISREG(opened.st_mode),
                "CADDY_HOST_CONFIG_CHANGED")
    finally:
        os.close(fd)
    # Check the actual Caddy executable, never use nginx to serve TLS here.
    checked(["docker", "exec", ident, "caddy", "version"], "CADDY_BINARY_UNAVAILABLE")
    return ident, config, file_bind


def caddy_check(container, mode):
    result = run(["docker", "exec", container, "caddy", mode,
                  "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"],
                 timeout=30)
    require(result.returncode == 0, "CADDY_" + mode.upper() + "_FAILED")


def confirm_running_config_matches_caddyfile(container):
    """Prevent reloading stale on-disk Caddyfile over newer live admin routes."""
    # Adapt inside the SAME active Docker container, with its environment.
    adapted = checked([
        "docker", "exec", container, "caddy", "adapt",
        "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile",
    ], "CADDY_ADAPT_FAILED", timeout=30)
    require(len(adapted) <= 1048576, "CADDY_ADAPTED_CONFIG_TOO_LARGE")
    try:
        with no_proxy().open(
                Request("http://127.0.0.1:2019/config/",
                        headers={"Cache-Control": "no-store"}), timeout=5) as response:
            require(response.status == 200, "CADDY_ADMIN_NOT_AVAILABLE")
            raw = response.read(1048577)
        require(len(raw) <= 1048576, "CADDY_RUNTIME_CONFIG_TOO_LARGE")
        actual = json.loads(raw)
        expected = json.loads(adapted)
    except (URLError, OSError, TimeoutError, ValueError):
        raise Stop("CADDY_ADMIN_OR_CONFIG_COMPARE_FAILED") from None
    require(actual == expected, "CADDYFILE_DIFFERS_FROM_RUNNING_CONFIG")
    return True


def backup_config(config, original):
    root = Path("/root/judun-oidc-health-caddy-backups")
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    tag = hashlib.sha256(original).hexdigest()[:20]
    dest = root / ("Caddyfile.original." + tag + ".bak")
    if not dest.exists():
        with dest.open("xb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(original)
            f.flush()
            os.fsync(f.fileno())
    require(dest.read_bytes() == original, "CONFIG_BACKUP_MISMATCH")
    print("ORIGINAL_CADDYFILE_BACKUP_VERIFIED=PASS", flush=True)


def write_caddy_config(config, data, mode, owner, group, *, file_bind=False):
    if file_bind:
        # Docker bind-mounting a *single file* pins its inode. os.replace()
        # would write a new host inode invisible inside the running container.
        # Keep the existing inode and reload Caddy only after fsync.
        fd = os.open(config, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        with os.fdopen(fd, "wb") as f:
            st = os.fstat(f.fileno())
            require(st.st_uid == owner and st.st_gid == group
                    and stat.S_ISREG(st.st_mode),
                    "CADDY_BIND_FILE_OWNER_CHANGED")
            f.seek(0)
            f.write(data)
            f.truncate()
            f.flush()
            os.fsync(f.fileno())
    else:
        fd, temp = tempfile.mkstemp(prefix=".judun-oidc.", dir=config.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
                os.fchmod(f.fileno(), mode)
                os.fchown(f.fileno(), owner, group)
            os.replace(temp, config)
        finally:
            if os.path.lexists(temp):
                os.unlink(temp)


def public_probe():
    """TLS verified, external HTTPS hostname, unauthorized must remain 403."""
    deadline = time.monotonic() + 110
    last = "NO_RESPONSE"
    while True:
        try:
            code, _ = response_code(PUBLIC, timeout=7)
            if code == 403:
                return True
            require(code != 200, "PUBLIC_UNAUTHENTICATED_HEALTH_LEAK")
            last = "HTTP_" + str(code)
        except (URLError, OSError, TimeoutError):
            last = "TLS_OR_CONNECT_NOT_READY"
        if time.monotonic() >= deadline:
            raise Stop("PUBLIC_TLS_OR_GATEWAY_UNREADY_" + last)
        time.sleep(2)


def apply():
    require(os.geteuid() == 0, "ROOT_REQUIRED")
    validate_local()
    before = production_identity()
    require(before["version"] == "1.2.190", "UNEXPECTED_PRODUCTION_BASE")
    try:
        addrs = {x[4][0] for x in socket.getaddrinfo(HOST, 443,
                 family=socket.AF_INET, type=socket.SOCK_STREAM)}
    except OSError:
        raise Stop("NEW_OIDC_DOMAIN_DNS_UNAVAILABLE") from None
    require(IP in addrs, "NEW_OIDC_DOMAIN_DNS_MISMATCH")
    ident, config, file_bind = find_active_caddy()
    confirm_running_config_matches_caddyfile(ident)
    print("CADDY_PERSISTED_EQUALS_ACTIVE=PASS", flush=True)
    original = config.read_bytes()
    require(b"judun.142-93-91-214.sslip.io" in original,
            "PRODUCTION_CADDY_VHOST_NOT_FOUND")
    require(b"lineguard.142-93-91-214.sslip.io" in original,
            "CADDY_SHARED_VHOSTS_NOT_CONFIRMED")
    if PREFIX.encode() in original:
        require(original.endswith(BLOCK), "EXISTING_OIDC_BLOCK_DIFFERS")
        public_probe()
        require(production_identity() == before, "PRODUCTION_CHANGED_DURING_RECHECK")
        print("CADDY_OIDC_HTTPS_ALREADY_CONFIGURED=PASS", flush=True)
        return
    require(HOST.encode() not in original, "OIDC_HOST_CONFLICT_EXISTS")
    backup_config(config, original)
    changed = original.rstrip(b"\n") + b"\n" + BLOCK
    st = config.stat()
    installed = False
    try:
        # Fail closed if any other process changed the config after inspection.
        require(config.read_bytes() == original, "CADDY_CONFIG_CONCURRENTLY_CHANGED")
        # Arm recovery before touching a Docker single-file bind: even a
        # partial in-place write must not evade rollback if an I/O error occurs.
        installed = True
        write_caddy_config(config, changed, stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid,
                           file_bind=file_bind)
        caddy_check(ident, "validate")
        caddy_check(ident, "reload")
        confirm_running_config_matches_caddyfile(ident)
        print("CADDY_NEW_HOST_ROUTE_INSTALLED=PASS", flush=True)
        public_probe()
        require(production_identity() == before, "PRODUCTION_IDENTITY_CHANGED")
        print("OIDC_HTTPS_UNAUTHENTICATED_403=PASS", flush=True)
        print("PRODUCTION_IDENTITY_PRESERVED=PASS", flush=True)
    except (Stop, OSError):
        if installed:
            current = config.read_bytes()
            # A partial inode-preserving write is necessarily a prefix of our
            # new config. Other unexpected contents mean concurrency -> STOP.
            own_partial = (file_bind and current != original
                           and changed.startswith(current))
            if current == changed or own_partial:
                write_caddy_config(config, original, stat.S_IMODE(st.st_mode),
                                   st.st_uid, st.st_gid, file_bind=file_bind)
                result = run(["docker", "exec", ident, "caddy", "reload", "--config",
                              "/etc/caddy/Caddyfile", "--adapter", "caddyfile"], timeout=30)
                print("CADDY_CONFIG_ROLLED_BACK=" +
                      ("PASS" if result.returncode == 0 else "UNVERIFIED"), flush=True)
            elif current != original:
                print("STOP: CADDY_CONFIG_CONCURRENT_CHANGE_MANUAL_REVIEW", flush=True)
        raise


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    require(args.apply, "EXPLICIT_APPLY_REQUIRED")
    with open("/run/lock/judun-oidc-caddy.lock", "a") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Stop("ANOTHER_OIDC_INSTALLER_IS_RUNNING") from None
        apply()
    print("JUDUN_OIDC_HTTPS_BRIDGE=READY", flush=True)
    print("SIGNATURE_RELEASE_VERSION_NOT_CHANGED=TRUE", flush=True)
    print("NEXT_CHECK=RUN_SIGNED_GITHUB_OIDC_60_SECOND_SITE_ATTESTATION", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (Stop, ValueError, json.JSONDecodeError) as e:
        print("STOP:", str(e), file=sys.stderr, flush=True)
        sys.exit(2)
