import base64, hashlib, json, os, subprocess
from pathlib import Path
root = Path.cwd()
src = root / "stage-transfer/v194"
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
require(m["schema"] == "judun.staging-deploy.v1" and m["base_snapshot"] == "JUDUN-1.2.193-LIVE-ITEM-PROGRESS-20261125-f264d49a458994f80125633afbbd0591ac2520fb014d7786aaff77003dde5886", "BASE")
require(m["target"] == {"version":"1.2.194","artifact_id":"JUDUN-1.2.194-PIPELINE-CANARY-20261126","build_instance_id":"1.2.194-PIPELINE-CANARY-20261126","source_tree_sha256":"dc67871276b57b5a9b8450030220e539dde35687340859cae2319b5e3b85c355","file_count":98}, "TARGET")
require(m["zip_sha256"] == "1b987d8fc8332ae25b10edc8e33231424dc8120a60a5cf4fa34a5eb202594777", "ZIP")
names = [f"chunk-{i:02d}" for i in range(46)]
require(sorted(p.name for p in src.glob("chunk-*")) == names, "CHUNK_SET")
h=hashlib.sha256()
n=0
with (dst / "candidate.cms").open("xb") as out:
    for i,name in enumerate(names):
        p=src/name
        require(p.is_file() and not p.is_symlink(), "CHUNK")
        b=p.read_bytes()
        require(len(b)==(508692 if i==45 else 768000), "SIZE")
        out.write(b)
        h.update(b)
        n+=len(b)
require(n==35068692 and h.hexdigest()==m["cms_sha256"]=="e62d604675a31d03f9a13d329d5b340d9faa5b6b7cefbada17f85691d0bb9b8b", "CMS_SHA")
(dst / "candidate.json.sig.b64").write_bytes(sigtext)
print("JUDUN_V194_ASSEMBLY_AND_ORIGINAL_ED25519_PASS")
