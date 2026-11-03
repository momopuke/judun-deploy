# SC VPS overload — verified baseline and final acceptance procedure (2026-11-02)

This path is independent of the production JUDUN signed release channel. Do not update JUDUN through this path.

## Verified live by VPS owner output
- Narrow maintenance agent command **seq 3 APPLIED**: browser `CPUQuotaPerSecUSec=200ms`, `CPUWeight=10`, browser active.
- `sc-vps-maintenance.timer` active; `line-openchat-guard.service` active; `stripchat-recorder` container running.
- VPS: 1 vCPU / 2 GB RAM; load 13.22 / 15.14 / 15.78; CPU PSI some avg10=99.54% (measurement after seq 3).
- Prior FFmpeg in `activating` and moderation `protection_verified=false`.
- Invalid streamer `---irene` already removed from tracked list (51 to 50) without video deletion.

## Important constraints
- Existing installed agent allows only `status` and `browser_limit`. GitHub updates to other Python files do **not** execute remotely; an authorized VPS console session is necessary to run diagnostics and do protected upgrades.
- `CPU PSI some` near 100% means runnable contention, **not** a proof of 100% physical CPU utilization.
- Never blindly lower the 20% browser cap further or stop Chromium; login/headless moderation behavior has not passed real validation.
- Never restart Docker, recorder, LINE Guard, JUDUN or FFmpeg merely to improve the load average. Do not open SSH ports, share passwords, publish private logs, or resize paid droplet without separate approval.

## Reviewed read-only diagnostics
- `diagnostic_v1.py` records per-host CPU busy and iowait, CPU/IO PSI, Chromium process count, cgroup throttling, service states and FFmpeg restart delay/count.
- Does not read cookies, profiles, streaming credentials, private logs, video names or member data.
- No process kill, container restart, systemd config changes, network uploads, or credential handling.
- Unit tests: `test_diagnostic_v1.py` — 15 assertions × 5 rounds PASS locally. This does **not** prove VPS run.

## When an authenticated VPS console is available
Use read-only inspection first:
```bash
curl --fail --silent --show-error --retry 2 --max-time 35   https://raw.githubusercontent.com/momopuke/judun-deploy/35ad4f51ca6eb100b009441ff0c27638c014bc08/vps-maintenance/diagnostic_v1.py   -o /tmp/sc-vps-diagnostic.py &&
python3 - <<'PY'
import hashlib,pathlib
d=pathlib.Path('/tmp/sc-vps-diagnostic.py').read_bytes()
assert hashlib.sha1(('blob '+str(len(d))+'\0').encode()+d).hexdigest()=='235acabd79067a650dbfc9c3fab342735f3aa3c3'
print('PINNED_DIAGNOSTIC_SHA_PASS')
PY
python3 /tmp/sc-vps-diagnostic.py --sample 10 --print
```
NOTE: Read-only diagnostics are *not deployed by this GitHub commit*. Do not claim completion until the actual report is returned from the VPS.

## Completion gate
1. Collect several independent load/CPU busy/iowait/throttling samples; distinguish quota-induced runnable backlog from host CPU saturation.
2. Confirm recorder writes healthy new recordings during active sessions; `docker running` alone is insufficient.
3. Confirm real Stripchat mute/block action on an authorized test account and verify login state; `active` alone is insufficient.
4. Confirm FFmpeg no rapid restart storm and no interrupted live transfer.
5. Confirm LINE Guard actual moderation behavior, as applicable, without testing against ordinary members.
6. Only then make a minimal guarded production fix; back up exactly what is touched, retain an immediate rollback, recheck 5 rounds. Do not spend money without explicit authorization.
7. Mark final acceptance PASS **only** when live evidence supports the functional tests and sustained pressure improvement.

## 2026-11-03 continuation when Work quota is unavailable
Single-run source: `vps-maintenance/vps_rescue_v5.py` (Git blob `a990121349e486c1153caa36488529b12fa3d353`, introduced at `d996bd9e8ac207fe857513ecfc23c61bceabc7ea`).
- This is a **manual one-time** authorized SSH-console run; the existing GitHub polling agent cannot execute it.
- Runs pinned `diagnostic_v1.py` 5 rounds, records a local/private JSON report at `/var/lib/sc-vps-maintenance/v5-final-report.json`.
- Only mutating repair: when `livevpn-stripchat-forward.service` is `activating/auto-restart` with NRestarts >= 1000, nonzero exit, and RestartUSec < 180s, install managed 180s restart delay and reload systemd **without restarting services**. Other situations are skipped.
- It does not alter Chromium profile/processes/flags, recorders, LINE Guard, JUDUN, video data, or credentials.
- The publication has separately available source-level 28-test suite `test_rescue_v5.py` and GitHub CI workflow; **GitHub CI/VPS execution not yet verified**.
- Its exit code 3 and status PARTIAL are expected while true live moderation and active recording-output verification are missing.
- **Never describe this as solved until observed 5-round host metrics plus real protection/recording tests pass.**
