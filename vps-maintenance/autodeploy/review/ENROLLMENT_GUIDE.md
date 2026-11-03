# SC VPS single enrollment, signed status first (review v5)

**Production enrollment status: NOT YET RUN ON THE VPS.**

For VPS `142.93.91.214` only, from an existing authenticated `root` shell:

```bash
curl -fsSL --retry 2 --connect-timeout 10 --max-time 35 \
  'https://raw.githubusercontent.com/momopuke/judun-deploy/9cdc4a724ed36fa0f2c5534c6d3327e554be03be/vps-maintenance/autodeploy/review/bootstrap_v5.sh' \
  -o /tmp/sc-vps-signed-enroll-v5.sh &&
printf '%s  %s\n' '1102d5c0f3b8a2145ce0073df3b62b969dbc6b9243a2b7289e3ceeb8b4f3fef2' /tmp/sc-vps-signed-enroll-v5.sh | sha256sum -c - &&
bash -n /tmp/sc-vps-signed-enroll-v5.sh &&
bash /tmp/sc-vps-signed-enroll-v5.sh
```

* Publisher bootstrap: commit `9cdc4a724ed36fa0f2c5534c6d3327e554be03be`; Git blob `1fce7fe827455a5c649d0d4a8651ad75ce41cf6c`; published SHA256 `1102d5c0f3b8a2145ce0073df3b62b969dbc6b9243a2b7289e3ceeb8b4f3fef2`.
* The bootstrap pins the signed agent to immutable commit `7219554c0c21ed4031e0856b3749e7fca5b8cd23` and SHA256 `9113ce881789bad728cb8015f4f94d3cb685a1245d4b6bec8f271ebae5ff7c89`.
* The signed channel is **sequence 1 = status (read-only)**. The first activation must log `SIGNED_READ_ONLY_STATUS_PASS`, then `ENROLLED`. No v10 memory changes are requested by this release.
* The installer does **not** request an SSH password inside the script, does **not** reset services, and keeps the new timer disabled on failed first-run checks.
* The existing `sc-vps-maintenance.timer` remains separate and unaffected.
* Once enrolled, the signed release agent polls every few minutes. Future signed sequence 2 `apply` must not be published until on-VPS seq 1 acceptance is verified; v10 enforces its own memory safety/rollback guards.
* To inspect exact VPS state: `cat /var/lib/sc-vps-autodeploy/state.json` and `systemctl is-active sc-vps-autodeploy.timer`.
* Not yet proven: actual v10 host execution, sustained CPU PSI improvement, uninterrupted recording or real Stripchat moderation.

**Do not use the older** `vps-maintenance/autodeploy/bootstrap.sh` path; this approved entrypoint is only the `review/bootstrap_v5.sh` path at its pinned immutable commit.
