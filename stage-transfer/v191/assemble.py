#!/usr/bin/env python3
"""Assemble only the preverified encrypted Judun stage candidate inside CI."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "stage-transfer/v191"
DEST = Path(os.environ["RUNNER_TEMP"])
CHUNKS = 34
CHUNK_SIZE = 1_048_578
LAST_SIZE = 464_466
CMS_SIZE = 35_067_540
CMS_SHA256 = "49966399cb50ef22f1c7b6d6e559476db376302cffee44292fc465cd1d654b9b"
KEY_SHA256 = "17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db"
BASE = "JUDUN-1.2.190-SINGLEPASS-RC1-UNSIGNED-1d5a73989525643a4da6c58b36263bdcc644a3f3780fb335b968e33e7de7866a"
TREE = "141654ca761a07e3ec56cf8417403adfa69f4414098e890a860338532dbe1fd8"


def require(ok, reason):
    if not ok:
        raise RuntimeError("JUDUN_TRANSFER_" + reason)


def unique(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, "DUPLICATE_JSON_KEY")
        result[name] = value
    return result


# Verify exact part set, sizes and whole ciphertext, never read plaintext.
expected = [SOURCE / f"chunk-{i:02d}" for i in range(CHUNKS)]
require(sorted(p.name for p in SOURCE.glob("chunk-*")) == [p.name for p in expected], "CHUNK_SET")
digest = hashlib.sha256()
size = 0
out = DEST / "candidate.cms"
with out.open("xb") as dst:
    for i, file in enumerate(expected):
        require(file.is_file() and not file.is_symlink(), "CHUNK_MISSING")
        require(file.stat().st_size == (LAST_SIZE if i == CHUNKS - 1 else CHUNK_SIZE), "CHUNK_SIZE")
        with file.open("rb") as src:
            for block in iter(lambda: src.read(1024 * 1024), b""):
                dst.write(block)
                digest.update(block)
                size += len(block)
require(size == CMS_SIZE and digest.hexdigest() == CMS_SHA256, "WHOLE_CMS_SHA")

manifest = (SOURCE / "candidate.json").read_bytes()
signature = (SOURCE / "candidate.json.sig.b64").read_bytes()
require(len(manifest) < 8192 and len(signature) < 256, "CONTROL_SIZE")
data = json.loads(manifest, object_pairs_hook=unique)
require(data.get("schema") == "judun.staging-deploy.v1", "SCHEMA")
require(data.get("base_snapshot") == BASE and data.get("cms_sha256") == CMS_SHA256, "BASE_OR_CMS")
require(data.get("zip_sha256") == "e4b7d8a97c4b4db6b545259e4d2c983e57602d088f4f4d8279d0d454f8a5558c", "SOURCE_ZIP")
require(data.get("target") == {
    "version": "1.2.191",
    "artifact_id": "JUDUN-1.2.191-PIPELINE-CANARY-20261124",
    "build_instance_id": "1.2.191-PIPELINE-CANARY-20261124",
    "source_tree_sha256": TREE,
    "file_count": 98,
}, "TARGET_IDENTITY")
public = ROOT / "keys/release_signing_public.pem"
require(public.is_file() and hashlib.sha256(public.read_bytes()).hexdigest() == KEY_SHA256, "ORIGINAL_PUBLIC_KEY")
sig = base64.b64decode(b"".join(signature.split()), validate=True)
require(len(sig) == 64, "SIGNATURE_SIZE")
(DEST / "manifest.bin").write_bytes(manifest)
(DEST / "signature.bin").write_bytes(sig)
result = subprocess.run([
    "openssl", "pkeyutl", "-verify", "-pubin", "-inkey", str(public),
    "-rawin", "-in", str(DEST / "manifest.bin"), "-sigfile", str(DEST / "signature.bin"),
], capture_output=True, timeout=20, check=False)
require(result.returncode == 0, "ED25519_VERIFICATION")
(DEST / "candidate.json").write_bytes(manifest)
(DEST / "candidate.json.sig.b64").write_bytes(signature)
print("JUDUN_V191_ENCRYPTED_ASSEMBLY_AND_ORIGINAL_ED25519_PASS")
