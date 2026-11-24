import base64, hashlib, json, os, subprocess
from pathlib import Path
root = Path.cwd()
src = root / "stage-transfer/v192"
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
require(m["schema"] == "judun.staging-deploy.v1" and m["base_snapshot"] == "JUDUN-1.2.191-PIPELINE-CANARY-20261124-141654ca761a07e3ec56cf8417403adfa69f4414098e890a860338532dbe1fd8", "BASE")
require(m["target"] == {"version":"1.2.192","artifact_id":"JUDUN-1.2.192-OCR-PROVIDER-RECOVERY-20261125","build_instance_id":"1.2.192-OCR-PROVIDER-RECOVERY-20261125","source_tree_sha256":"29a007c6329cfdca27aeda9952ca6e1ad904707ec2130f6b33a0d2785f5447e1","file_count":98}, "TARGET")
require(m["zip_sha256"] == "3427a968df4e3be2f6d476fabb3062f77b6228e7dd0b7ca92a34a1e96f5f9bd3", "ZIP")
names = [f"chunk-{i:02d}" for i in range(34)]
require(sorted(p.name for p in src.glob("chunk-*")) == names, "CHUNK_SET")
h=hashlib.sha256()
n=0
with (dst / "candidate.cms").open("xb") as out:
    for i,name in enumerate(names):
        p=src/name
        require(p.is_file() and not p.is_symlink(), "CHUNK")
        b=p.read_bytes()
        require(len(b)==(465492 if i==33 else 1048576), "SIZE")
        out.write(b)
        h.update(b)
        n+=len(b)
require(n==35068500 and h.hexdigest()==m["cms_sha256"]=="5e4527e4623781583f5ca214b3bee2ebc6b64103cc4daf87f55a04d4d6033b0c", "CMS_SHA")
(dst / "candidate.json.sig.b64").write_bytes(sigtext)
print("JUDUN_V192_ASSEMBLY_AND_ORIGINAL_ED25519_PASS")
