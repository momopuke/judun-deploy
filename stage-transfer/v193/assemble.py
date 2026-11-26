import base64, hashlib, json, os, subprocess
from pathlib import Path
root = Path.cwd()
src = root / "stage-transfer/v193"
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
require(m["schema"] == "judun.staging-deploy.v1" and m["base_snapshot"] == "JUDUN-1.2.192-OCR-PROVIDER-RECOVERY-20261125-29a007c6329cfdca27aeda9952ca6e1ad904707ec2130f6b33a0d2785f5447e1", "BASE")
require(m["target"] == {"version":"1.2.193","artifact_id":"JUDUN-1.2.193-LIVE-ITEM-PROGRESS-20261125","build_instance_id":"1.2.193-LIVE-ITEM-PROGRESS-20261125","source_tree_sha256":"f264d49a458994f80125633afbbd0591ac2520fb014d7786aaff77003dde5886","file_count":98}, "TARGET")
require(m["zip_sha256"] == "197bebf3923fc3f54ddb0e9d22c1115544c673458840dca09fd716e0aa640ca5", "ZIP")
names = [f"chunk-{i:02d}" for i in range(34)]
require(sorted(p.name for p in src.glob("chunk-*")) == names, "CHUNK_SET")
h=hashlib.sha256()
n=0
with (dst / "candidate.cms").open("xb") as out:
    for i,name in enumerate(names):
        p=src/name
        require(p.is_file() and not p.is_symlink(), "CHUNK")
        b=p.read_bytes()
        require(len(b)==(464180 if i==33 else 1048576), "SIZE")
        out.write(b)
        h.update(b)
        n+=len(b)
require(n==35067188 and h.hexdigest()==m["cms_sha256"]=="f61fd93d9b3420bada2ef7aacc2ee649849710812f1ce4f5c9f80f9a375c5f4d", "CMS_SHA")
(dst / "candidate.json.sig.b64").write_bytes(sigtext)
print("JUDUN_V193_ASSEMBLY_AND_ORIGINAL_ED25519_PASS")
