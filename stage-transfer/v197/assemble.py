import base64, hashlib, json, os, subprocess
from pathlib import Path
root = Path.cwd()
src = root / "stage-transfer/v197"
dst = Path(os.environ["RUNNER_TEMP"])
def require(ok, code):
    if not ok:
        raise RuntimeError(code)
pub = root / "keys/release_signing_public.pem"
require(hashlib.sha256(pub.read_bytes()).hexdigest() == "17c8b563d224568447c3af1db57c8bb9ce51dbeac6c21371e909bc3a5635a8db", "KEY_PIN")
manifest = (src / "candidate.json").read_bytes()
sigtext = (src / "candidate.json.sig.b64").read_bytes()
sig = base64.b64decode(sigtext.strip(), validate=True)
require(len(sig) == 64, "SIG_SIZE")
(dst / "candidate.json").write_bytes(manifest)
(dst / "signature.bin").write_bytes(sig)
subprocess.run(["openssl","pkeyutl","-verify","-pubin","-inkey",str(pub),"-rawin","-in",str(dst / "candidate.json"),"-sigfile",str(dst / "signature.bin")],check=True,timeout=20)
m = json.loads(manifest)
require(m["schema"] == "judun.staging-deploy.v1" and m["base_snapshot"] == "JUDUN-1.2.196-PAID-503-RECOVERY-20261127-e9980a9cf1c0afa3f7ed052f80ff5f65e9d63f429607dd24839093e1790a9305", "BASE")
require(m["target"] == {"version":"1.2.197","artifact_id":"JUDUN-1.2.197-CORE-PREVIEW-TIMEOUT-RECOVERY-20261128","build_instance_id":"1.2.197-CORE-PREVIEW-TIMEOUT-RECOVERY-20261128","source_tree_sha256":"3ce58d45734dd0681903413f3b8639747215d4007573c2c24a50a0f3a50f9172","file_count":98}, "TARGET")
require(m["zip_sha256"] == "889a3dfef92e812b41f06bce7877f4effd31087e0615c7b34e0b8d42a27d3626", "ZIP")
names = [f"chunk-{i:02d}" for i in range(46)]
require(sorted(p.name for p in src.glob("chunk-*")) == names, "CHUNK_SET")
h=hashlib.sha256()
n=0
with (dst / "candidate.cms").open("xb") as out:
    for i,name in enumerate(names):
        p=src/name
        require(p.is_file() and not p.is_symlink(), "CHUNK")
        b=p.read_bytes()
        require(len(b)==(510596 if i==45 else 768000), "SIZE")
        out.write(b)
        h.update(b)
        n+=len(b)
require(n==35070596 and h.hexdigest()==m["cms_sha256"]=="4a952397ef04bc8b0a9b83cd9a0dddc1805b3045770d2f2838d5f53d9d8e54a6", "CMS_SHA")
(dst / "candidate.json.sig.b64").write_bytes(sigtext)
print("JUDUN_V197_ASSEMBLY_AND_ORIGINAL_ED25519_PASS")
