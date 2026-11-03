> **2026-11-04 host recovery v3, awaiting VPS execution.** The owner-reported unit is byte-exact `sc-vps-autodeploy.service` legacy `TimeoutStartSec=260s`, 424 bytes, SHA256 `ed365efa923a6210147cfdbffd4b812891ea992b5e832bf95ddbad367034e730`. Audited `review/reconcile_v3.py` recognizes ONLY those exact legacy unit bytes, backs up the existing service and known legacy agent before changing them, upgrades the service timeout to 900s, runs signed read-only status and enables the timer. Unknown agents, trust roots, state and unit settings still fail closed. Five local rounds of 33 tests PASS (165/165); **no live v3 outcome yet**. SHA256 of v3 source `c1632eb339bfe655199f134017dcc376e7f3e6a5f7519a36ac868c9df7996e8f`; verified Git blob `085581e97b3b62a5370e978df931414aac1baf02`. This supersedes reconcile v1/v2 for the exact known 260s service.

> **2026-11-04 recovery v2:** Host rejected old reconciler with `UNKNOWN_UNIT_CONTENTS:sc-vps-autodeploy.service`; this indicates a non-identical preexisting unit, not a failed SHA check. New `review/reconcile_v2.py` (SHA256 `c787f34a21e101881233a2e0d4c64fc4955488f7a9992bbc21714b296c27c50c`, Git blob `dd37516a8d4d62729f9bbec156f510d26f463588`) accepts only nonfunctional comment/whitespace differences; otherwise stops without mutation and prints a redacted fingerprint. Five rounds × 30 offline tests PASS. **No new agent enrollment or host success has yet been verified. Never delete or overwrite unknown unit files.**

> **CURRENT CANONICAL ENTRYPOINT (2026-11-04):** `review/bootstrap_v5.sh` at commit `9cdc4a724ed36fa0f2c5534c6d3327e554be03be`, verified SHA256 `1102d5c0f3b8a2145ce0073df3b62b969dbc6b9243a2b7289e3ceeb8b4f3fef2`. See `review/ENROLLMENT_GUIDE.md`. Historical references below to root `bootstrap.sh` are superseded. The reviewed v5 agent includes the watchdog, first-run-read-only and nested-parent-symlink guards. VPS enrollment and v10 functional acceptance remain **NOT VERIFIED**.

# SC VPS signed deployment — current status

## 2026-11-04 source review / release boundary
- The **new** agent and immutable bootstrap have been published to the independent `vps-maintenance` branch.
- **NOT ENROLLED ON THE VPS** (DigitalOcean integration does not provide SSH, terminal or remote script execution).
- First signed channel action: `sequence=1, operation=status`, **read-only**. It is not `apply`.
- Signed channel Ed25519 verification PASS; all pinned v10 file SHA256 values match.
- Agent version commit: `53430996dd856643f3f68c5686afb8b1470114ae`; pinned agent SHA256: `9113ce881789bad728cb8015f4f94d3cb685a1245d4b6bec8f271ebae5ff7c89`.
- Bootstrap commit: `ee3693e9913337ae58dc947181e75eb231a3466c`; pinned bootstrap SHA256: `5f7b9d4fa998a1659de7e1ff20a3d3386661344b63d72855456f467f1f03b169`.
- Bootstrap starts signed read-only status **before** enabling the new `sc-vps-autodeploy.timer`.
- The new agent refuses initial `apply`, unsafe nested target symlinks, duplicate/past releases, unsigned content, partial/unknown rollback states; writes an in-progress fence before any signed `apply`.
- Guarded first-run service timeout is 900s rather than the older unsafe 260s.
- Local offline pre-release: 28 agent/channel checks + 12 signed v10 source tests, five rounds PASS (200 checks); 27 guard/state tests × five rounds PASS (135 checks); independent full apply-path mock PASS. CI workflow exists, but cloud run status has not been independently verified.
- This does **not** establish that v10 was executed on the VPS, that CPU pressure improved or that Stripchat mute/block works.

## Single-owner enrollment boundary
The server operator must authorize one initial root-side agent installation via an authenticated VPS terminal. This is a technical limitation of existing DigitalOcean and GitHub app permissions, **not a missing user authorization**. Do not ask the owner to disclose any password or private key.

After that, signed updates are fetched by the VPS every ~5 minutes from the GitHub channel with a fail-closed state machine. A further release with `sequence>=2` and `operation=apply` requires an **independent valid Ed25519 signature** after real status receipt and protected service checks. GitHub edits alone cannot bypass the signed release gate.

## Production acceptance gate
- Initial agent `state.json`: `last_sequence=1, status=applied, operation=status, code_installed=false`.
- Signed apply release must be explicitly published as a new numbered release after initial state verified.
- Actual v10 `persistent_verified` or diagnosis-only/safety refusal separately confirmed.
- Recorder video continuity, Gateway health, Stripchat live mute/block, LINE moderation, RTMP retry health, and sustained CPU/IO pressure must be independently tested.
- No service restart, data deletion, paid resize or SSH credential collection without separate scoped authorization.
