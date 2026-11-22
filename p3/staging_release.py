"""Verify, select, and boot a candidate in the separate Judun staging service."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener
from zipfile import ZipFile


STAGE_ROOT = Path("/srv/judun-staging")
STAGE_DATA = Path("/var/lib/judun-staging")
STAGE_URL = "https://judun-test.tony870490.chatgpt.site"
STAGE_SERVICE = "judun-staging-isolated.service"
MANIFEST = "DEPLOY_MANIFEST.json"
IDENTITY = ".staging-identity.json"
MANIFEST_MAX = 512 * 1024
PAYLOAD_MAX = 512 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}\Z")
PRODUCTION_ROOTS = tuple(map(Path, (
    "/var/www/advisor",
    "/srv/judun",
    "/var/lib/judun",
    "/var/lib/advisor",
    "/opt/judun-autodeploy",
    "/var/lib/judun-autodeploy",
)))


@dataclass(frozen=True)
class Release:
    version: str
    artifact_id: str
    build_instance_id: str
    source_tree_sha256: str
    file_count: int

    def __post_init__(self):
        if (
            not isinstance(self.version, str)
            or not re.fullmatch(r"\d+\.\d+\.\d+", self.version)
            or not all(isinstance(item, str) and NAME.fullmatch(item)
                       for item in (self.artifact_id, self.build_instance_id))
            or not isinstance(self.source_tree_sha256, str)
            or not HEX.fullmatch(self.source_tree_sha256)
            or type(self.file_count) is not int
            or not 0 < self.file_count <= 2048
        ):
            raise ValueError("Invalid release identity")

    @property
    def name(self):
        return f"{self.artifact_id}-{self.source_tree_sha256}"


def outside_production(path):
    path = path.resolve()
    if any(path == base or path in base.parents or base in path.parents
           for base in PRODUCTION_ROOTS):
        raise ValueError("Stage paths must be separate from production")
    return path


def read_regular(path, maximum):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError(f"Invalid source file: {path.name}")
    data = path.read_bytes()
    if len(data) > maximum:
        raise ValueError(f"Oversized source file: {path.name}")
    return data


def load_manifest(raw, release):
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or manifest.get("schema") != "judun.deploy-manifest.v1":
        raise ValueError("Unknown deployment manifest schema")
    for field in ("version", "artifact_id", "build_instance_id", "source_tree_sha256"):
        if manifest.get(field) != getattr(release, field):
            raise ValueError(f"Candidate identity mismatch: {field}")
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != release.file_count:
        raise ValueError("Candidate file count mismatch")
    rows = {}
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("Invalid manifest row")
        name, size, digest = item.get("path"), item.get("size"), item.get("sha256")
        if not isinstance(name, str) or not name:
            raise ValueError("Missing manifest path")
        path = PurePosixPath(name)
        if (not path.parts or path.is_absolute() or path.as_posix() != name
                or any(part in {"", ".", ".."} or part.startswith(".") for part in path.parts)
                or any(ord(char) < 32 or char == "\\" for char in name)
                or name == MANIFEST or name in rows
                or type(size) is not int or not 0 <= size <= PAYLOAD_MAX
                or not isinstance(digest, str) or not HEX.fullmatch(digest)):
            raise ValueError(f"Invalid manifest entry: {name!r}")
        rows[name] = (size, digest)
    if "app.py" not in rows or sum(size for size, _ in rows.values()) > PAYLOAD_MAX:
        raise ValueError("Missing app.py or oversized candidate")
    fingerprint = "".join(f"{name}\t{digest}\t{size}\n"
                          for name, (size, digest) in sorted(rows.items())).encode()
    if hashlib.sha256(fingerprint).hexdigest() != release.source_tree_sha256:
        raise ValueError("Source tree fingerprint mismatch")
    return rows


@contextmanager
def source_reader(source):
    source = outside_production(source)
    if source.is_dir():
        def read(relative, maximum):
            path = source / relative
            if path.resolve() != path:
                raise ValueError(f"Symlink in source: {relative}")
            return read_regular(path, maximum)
        yield read
        return
    with ZipFile(source) as archive:
        names = {}
        for info in archive.infolist():
            if info.filename in names:
                raise ValueError("Duplicate ZIP entry")
            names[info.filename] = info

        def read(relative, maximum):
            info = names.get("payload/" + relative)
            if (info is None or info.is_dir() or info.file_size > maximum
                    or stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG)):
                raise ValueError(f"Missing or invalid ZIP entry: {relative}")
            with archive.open(info) as entry:
                data = entry.read(maximum + 1)
            if len(data) != info.file_size or len(data) > maximum:
                raise ValueError(f"Invalid ZIP entry size: {relative}")
            return data
        yield read


@contextmanager
def store_lock(root):
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    path = root / ".lock"
    descriptor = os.open(path, os.O_NOFOLLOW | os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        os.close(descriptor)


def release_dir(root, name):
    releases = root / "releases"
    if releases.is_symlink():
        raise ValueError("A staging release store cannot be a symlink")
    path = releases / name
    if path.is_symlink():
        raise ValueError("A staging snapshot cannot be a symlink")
    return path


def verify_snapshot(path, expected=None):
    release = Release(**json.loads(read_regular(path / IDENTITY, 4096)))
    if expected is not None and release != expected:
        raise ValueError("Staged release identity mismatch")
    if release.name != path.name:
        raise ValueError("Staged release directory mismatch")
    rows = load_manifest(read_regular(path / MANIFEST, MANIFEST_MAX), release)
    for name, (size, digest) in rows.items():
        file = path / name
        if file.resolve() != file:
            raise ValueError(f"Symlink in staged release: {name}")
        verify_bytes(name, read_regular(file, size), size, digest)
    expected_paths = set(rows) | {MANIFEST, IDENTITY}
    actual_paths = {str(item.relative_to(path)) for item in path.rglob("*")
                    if not item.is_dir() or item.is_symlink()}
    if actual_paths != expected_paths:
        unexpected = sorted(actual_paths - expected_paths)
        raise ValueError("Unmanifested files in staged release: " + repr(unexpected[:5]))
    return release


def verify_bytes(name, data, size, digest):
    if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Candidate contents mismatch: {name}")


def prepare(root, source, release):
    root = outside_production(root)
    source = outside_production(source)
    if source == root or source in root.parents or root in source.parents:
        raise ValueError("Source and release storage must be separate")
    with store_lock(root):
        target = release_dir(root, release.name)
        target.parent.mkdir(mode=0o755, exist_ok=True)
        if target.exists():
            return verify_snapshot(target, release)
        temp = Path(tempfile.mkdtemp(prefix=".prepare-", dir=target.parent))
        try:
            with source_reader(source) as read:
                raw = read(MANIFEST, MANIFEST_MAX)
                for name, (size, digest) in load_manifest(raw, release).items():
                    data = read(name, size)
                    verify_bytes(name, data, size, digest)
                    file = temp / name
                    file.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                    file.write_bytes(data)
                (temp / MANIFEST).write_bytes(raw)
                (temp / IDENTITY).write_text(json.dumps(asdict(release)) + "\n", encoding="utf-8")
            for item in temp.rglob("*"):
                item.chmod(0o755 if item.is_dir() else 0o444)
            temp.chmod(0o755)
            temp.rename(target)
        finally:
            if temp.exists():
                shutil.rmtree(temp)
        return release


def check_name(name):
    if not isinstance(name, str) or "/" in name or len(name) > 193:
        raise ValueError("Invalid staging snapshot name")
    parts = name.rsplit("-", 1)
    if len(parts) != 2 or not NAME.fullmatch(parts[0]) or not HEX.fullmatch(parts[1]):
        raise ValueError("Invalid staging snapshot name")
    return name


def selection(root):
    pointer = root / "current"
    if not pointer.is_symlink():
        raise ValueError("Staging requires an initial release; run init")
    target = os.readlink(pointer)
    if not target.startswith("releases/"):
        raise ValueError("Must select a release directly under the staging store")
    name = check_name(target.removeprefix("releases/"))
    return release_dir(root, name)


def replace_pointer(root, name):
    # Work under the same filesystem so rename replaces the pointer atomically.
    with tempfile.TemporaryDirectory(prefix=".switch-", dir=root) as work:
        link = Path(work) / "current"
        link.symlink_to("releases/" + check_name(name))
        link.replace(root / "current")
        sync_directory(root)


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def initialize(root, name):
    root = outside_production(root)
    with store_lock(root):
        if os.path.lexists(root / "current"):
            raise ValueError("An existing release must be changed with switch")
        chosen = verify_snapshot(release_dir(root, check_name(name)))
        replace_pointer(root, name)
        return chosen


def process_state(root, target, restart, wait_for_health, *, before_switch=None):
    pending = root / ".switch-pending.json"
    previous = verify_snapshot(selection(root))
    target = verify_snapshot(release_dir(root, check_name(target)))
    if os.path.lexists(pending):
        raise ValueError("An earlier switch was interrupted; run recover")
    wait_for_health(previous)
    if previous == target:
        return target
    if before_switch is not None:
        before_switch()
    with tempfile.TemporaryDirectory(prefix=".journal-", dir=root) as work:
        journal = Path(work) / pending.name
        with journal.open("x", encoding="utf-8") as file:
            json.dump({"previous": previous.name, "target": target.name}, file)
            file.flush()
            os.fsync(file.fileno())
        journal.replace(pending)
        sync_directory(root)
    try:
        replace_pointer(root, target.name)
        restart()
        wait_for_health(target)
    except BaseException:
        recover(root, restart, wait_for_health)
        raise
    pending.unlink()
    sync_directory(root)
    return target


def recover(root, restart, wait_for_health):
    pending = root / ".switch-pending.json"
    state = json.loads(read_regular(pending, 4096))
    previous = verify_snapshot(release_dir(root, check_name(state["previous"])))
    replace_pointer(root, previous.name)
    restart()
    wait_for_health(previous)
    pending.unlink()
    sync_directory(root)
    return previous


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def fetch_health(port, endpoint, timeout):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(f"http://127.0.0.1:{port}{endpoint}", timeout=timeout) as response:
        raw = response.read(MANIFEST_MAX + 1)
        if response.status != 200 or len(raw) > MANIFEST_MAX:
            raise ValueError("Invalid staging health response")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Invalid staging health JSON")
    return data



# The sole previously accepted R1 Sandbox snapshot runs an isolated ECPay
# sandbox. Older staging snapshots and production-compatible RC1 candidates
# must retain test_unlock. This pin is exact, not a general mode allowlist.
KNOWN_R1_SANDBOX_IDENTITY = (
    "1.2.190",
    "JUDUN-1.2.190-STAGE-SANDBOX-E2E-R1-UNSIGNED",
    "1.2.190-STAGE-SANDBOX-E2E-R1-20261122",
    "464a6d76b1ecb723c8a4767c0e4b354d649f582f6c565c1174ccdd3f89c55c32",
    98,
)


def expected_stage_payment_mode(release):
    identity = (
        release.version,
        release.artifact_id,
        release.build_instance_id,
        release.source_tree_sha256,
        release.file_count,
    )
    return "ecpay_stage" if identity == KNOWN_R1_SANDBOX_IDENTITY else "test_unlock"


def check_running(release, port=8011, timeout=75):
    deadline = time.monotonic() + timeout
    expected = {field: getattr(release, field) for field in (
        "version", "artifact_id", "build_instance_id", "source_tree_sha256")}
    while True:
        try:
            build = fetch_health(port, "/health/build", 3)
            deep = fetch_health(port, "/health/artifact?deep=true", 3)
            ready = fetch_health(port, "/health/ready", 3)
            if (all(all(data.get(key) == value for key, value in expected.items())
                    for data in (build, deep))
                    and build.get("payment_mode") == expected_stage_payment_mode(release)
                    and build.get("status") == deep.get("status") == "ok"
                    and deep.get("deep_verified") is True and type(deep.get("mismatch_count")) is int
                    and deep["mismatch_count"] == 0
                    and deep.get("files_verified") == deep.get("manifest_file_count") == release.file_count
                    and ready.get("status") == "ready" and ready.get("version") == release.version):
                return
        except (OSError, ValueError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Staging health did not match {release.artifact_id}")
        time.sleep(0.25)


def stage_unit():
    return subprocess.run(["systemctl", "show", STAGE_SERVICE, "--property=ExecStart",
                           "--property=PartOf", "--property=DynamicUser",
                           "--property=InaccessiblePaths"],
                          text=True, capture_output=True, check=True, timeout=15).stdout


def restart_service():
    subprocess.run(["systemctl", "reset-failed", STAGE_SERVICE], check=False, timeout=15)
    subprocess.run(["systemctl", "restart", STAGE_SERVICE], check=True, timeout=45)


def enforce_service(root):
    if root != STAGE_ROOT or os.geteuid() != 0:
        raise ValueError("Live stage switching requires the dedicated root and a VPS operator")
    if not root.is_dir() or root.stat().st_uid != 0 or root.stat().st_mode & 0o022:
        raise ValueError("Dedicated staging root must be root-owned")
    properties = dict(line.split("=", 1) for line in stage_unit().splitlines() if "=" in line)
    command = properties.get("ExecStart", "")
    if (str(root / "venv/bin/python") not in command
            or str(root / "staging_release.py") not in command
            or properties.get("PartOf")
            or properties.get("DynamicUser") != "yes"
            or "/var/www/advisor" not in
            [item.lstrip("-+") for item in properties.get("InaccessiblePaths", "").split()]):
        raise ValueError("Independent staging service configuration is not active")


def serve(root):
    if root != STAGE_ROOT or os.geteuid() == 0:
        raise ValueError("Staging must run under its unprivileged service account")
    if len(os.environ.get("JUDUN_STAGING_SESSION", "")) < 40:
        raise ValueError("Existing staging session configuration required")
    path = selection(root)
    verify_snapshot(path)
    for key in tuple(os.environ):
        if key.startswith(("ECPAY_", "SMTP_", "MAIL_", "JUDUN_ECPAY_", "JUDUN_MAIL_")):
            del os.environ[key]
    os.environ.update(
        JUDUN_STAGING="1",
        ENABLE_TEST_MODE="true",
        COOP_MODE="simulation",
        APP_DATA_DIR=str(STAGE_DATA),
        PUBLIC_BASE_URL=STAGE_URL,
        COMMERCIAL_FOLLOWUP_ENABLED="false",
        PYTHONDONTWRITEBYTECODE="1",
    )
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(path))
    from app import app
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8011, workers=1,
                proxy_headers=True, forwarded_allow_ips="127.0.0.1", access_log=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=STAGE_ROOT)
    subs = parser.add_subparsers(dest="action", required=True)
    stage = subs.add_parser("prepare")
    stage.add_argument("source", type=Path)
    for name in ("version", "artifact-id", "build-instance-id", "source-tree-sha256", "file-count"):
        stage.add_argument("--" + name, required=True, type=int if name == "file-count" else str)
    subs.add_parser("init").add_argument("name")
    subs.add_parser("switch").add_argument("name")
    subs.add_parser("recover")
    subs.add_parser("serve")
    subs.add_parser("status")
    subs.add_parser("probe")
    args = parser.parse_args()
    root = outside_production(args.root)
    try:
        if args.action == "serve":
            serve(root)
            return
        if args.action == "prepare":
            release = Release(args.version, args.artifact_id, args.build_instance_id,
                              args.source_tree_sha256, args.file_count)
            result = prepare(root, args.source, release)
        elif args.action == "init":
            result = initialize(root, args.name)
        elif args.action in {"status", "probe"}:
            result = verify_snapshot(selection(root))
            if args.action == "probe":
                enforce_service(root)
                check_running(result)
        else:
            enforce_service(root)
            with store_lock(root):
                if args.action == "switch":
                    result = process_state(root, args.name, restart_service, check_running)
                else:
                    result = recover(root, restart_service, check_running)
        print(json.dumps({**asdict(result), "snapshot": result.name}, ensure_ascii=False))
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
