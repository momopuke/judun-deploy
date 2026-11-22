# Judun staging health-only OIDC gateway (2026-11-22)

**Status: implementation + offline CI only. VPS systemd service and HTTPS routing are NOT installed until an authorized operator confirms the existing proxy's precise configuration. No complete automatic release acceptance yet.**

## Why

ChatGPT Sites SIWC bypass grants site-level access, not endpoint-scoped read-only authorization. Putting that token into GitHub Actions would give the CI runner a much larger capability than it needs. The replacement uses **GitHub Actions short-lived OIDC JWTs** and an independent VPS-local staging health-only service. It does not relax Ed25519/CMS signing, PR review, staging isolation, independent QA or production rollback.

Trust pins, to verify before installation:
- GitHub OIDC issuer: `https://token.actions.githubusercontent.com`
- Signing JWKS: `https://token.actions.githubusercontent.com/.well-known/jwks`
- JWT audience: `judun-stage-health-v1`
- GitHub repository: `momopuke/judun-deploy` / immutable repository ID `1404145305` / owner ID `126347129`
- Allow only trusted base workflows on `refs/heads/main`: `verify-v1286-live.yml` for push/dispatch, `release-pr-gate.yml` for pull_request_target
- Public HTTPS origin: `https://judun-oidc.142-93-91-214.sslip.io` (separate OIDC-only TLS hostname, NOT the existing production hostname); exact route prefix `/__jd_stage_health/v1`

## Server implementation and no-secrets boundary

- Existing isolated staging local HTTP process `http://127.0.0.1:8011` remains unchanged.
- `ops/stage_health_oidc_gateway.py` listens on **127.0.0.1:18762 only**, not `0.0.0.0`. It accepts only three exact read-only GETs:
  - `/__jd_stage_health/v1/health/build`
  - `/__jd_stage_health/v1/health/artifact?deep=true`
  - `/__jd_stage_health/v1/health/ready`
- JWT validation includes RS256 signature via pinned GitHub JWKS HTTPS (no redirect), exact issuer, audience, repository owner ID/repository ID/name, branch, workflow reference and event, issued/expiration times. Invalid JWTs and other paths FAIL closed. Upstream response JSON is filtered to the exact public health identity/verification fields; never forwards database/customer/PDF/email/secret fields. No JWT/header/request URI logging.
- `ops/judun-stage-health-oidc.service` uses a dynamic unprivileged systemd account, hardening, resource limits and restart. It does not change existing VPS production service, keys, agent or DB.
- GitHub existing release PR gate and 60-second final verification now obtain short-lived OIDC identity using `p3/stage_oidc_client.py`. Their jobs have scoped `id-token: write` and **no** `JUDUN_STAGE_AUTH_TOKEN` secret. Release PR must check exact staged candidate and paid-mode isolation before merge; post-release remains fail-closed.
- Private builder `p3/direct_deploy_publish.py --publish` continues validating the original Ed25519 signed manifest, exact public key, encrypted CMS, fixed-score/independent same-SHA QA receipt, current live base and protected GitHub commit. It can **open a PR without a Sites-wide bypass**; this is **not a deploy approval**. Only the protected `judun/release-gate`, which requires a real GitHub OIDC proof against the exact staged candidate, can authorize merging. `--verify-published` also uses OIDC rather than a reusable Sites login token.

## HTTPS integration: dedicated Docker Caddy vhost, one-shot and fail closed

**Current VPS evidence** (GitHub #22 comment 7066301647): port 443 was served by a **Caddy process inside Docker** loaded from `/etc/caddy/Caddyfile`; Nginx primarily served other ports. A later stage-domain deployment also succeeded using Caddy. These are historical observations, **not** authority to assume today's Docker network/mount topology is identical.

The new `ops/enable_stage_oidc_https_caddy_once.py` has a safety-only, single-pass `--apply` mode:

1. Confirm the newly installed OIDC gateway responds **403** anonymously on **127.0.0.1:18762 only**, and check existing production `/health/build` is signed v1.2.190.
2. Resolve independent new DNS `judun-oidc.142-93-91-214.sslip.io` to the expected VPS IP. Identify exactly **one** running Docker Caddy with host networking and root-owned, writable **bind-mounted** `/etc/caddy/Caddyfile`. Stop if topology is ambiguous or if a conflicting OIDC hostname already exists.
3. Preserve the original Caddyfile in `/root/judun-oidc-health-caddy-backups` as mode 0600; **append one independent TLS site** that only proxies GET paths `/__jd_stage_health/v1/health/build`, `.../health/artifact?deep=true`, `.../health/ready` to `127.0.0.1:18762`. All other paths return 403. No changes inside the existing production `judun.142-93-91-214.sslip.io` site block, payment or other existing vhosts.
4. Validate the **actual container Caddyfile**, reload the same container through Caddy's own supported reload, and confirm the new **public HTTPS certificate + anonymous 403** and unchanged production identity. If any validation/HTTPS/identity check fails, restore the old Caddyfile and reload, or stop safely without changing it if an administrator changed the config concurrently.
5. Only after this exact-host HTTPS ingress passes, trigger **one** protected-main `ops/oidc-verify-request.json` change (approved PR, no signed payload change). The original `Verify JUDUN signed release and production` workflow then automatically performs real GitHub OIDC staging claims, same release/tree/98/ready/payment-mode initial check and **>=60 second second check**, uploading final evidence only after both passes.

The new host may need Caddy to issue a fresh public TLS certificate; this is allowed to settle for a bounded period without affecting the existing site. If it cannot be obtained/validated, the script restores the prior Caddy config. The flow requires no SIWC Sites owner token and does not change the original Ed25519 signer or VPS production deploy agent. **If current Caddy layout differs** (non-host Docker network, no persistent bind mount, non-root config), the script returns an actionable STOP instead of guessing or resetting the shared TLS router.

## Controlled activation sequence; stop safely on any fault

1. Confirm current VPS isolated staging service is ready, source file SHA pinned to protected merged main, `python3-cryptography` available. Install the unmodified `ops/stage_health_oidc_gateway.py` into root-owned `/srv/judun-stage-health-oidc/` and systemd unit, then locally test refusal with no JWT. Verify `ss -lntp` listener on **127.0.0.1:18762 only**; keep original stage/prod untouched.
2. Invoke the pinned one-shot Docker Caddy dedicated-host configurator; verify Caddy validate/reload and public HTTPS anonymous **403** with unchanged production identity. Any failure must restore the original Caddyfile and reload the previous configuration.
3. Use one protected-main `ops/oidc-verify-request.json` update (or authorized `workflow_dispatch`) of original `Verify JUDUN signed release and production` to get a real GitHub Actions JWT. Require exact v190 build/tree/98 of both live and isolated stage, correct `ecpay_live` / `test_unlock`, initial and **60-second recheck** with a genuine final artifact. Do not treat offline tests as this proof.
4. Before next signed v191+ PR, verify the protected trusted `judun/release-gate` confirms the **same candidate SHA** on stage; invalid OIDC, older stage, wrong issuer/ref/workflow, mismatch of artifact/build/payment all must block release before merge. Then original authorized signer, original VPS agent and rollback need separately demonstrated E2E.
5. If any service/proxy test fails, restore the backed-up proxy config and disable only `judun-stage-health-oidc.service`. Do not roll back the existing production application for this read-only integration.

The service needs the Debian `python3-cryptography` package and outbound TLS access to the fixed GitHub JWKS host. No persistent token, GitHub Repository Secret, Sites owner credential or private Ed25519/CMS key is required.

References: GitHub official OIDC docs https://docs.github.com/en/actions/reference/security/oidc ; project record https://github.com/momopuke/judun-deploy/issues/22 .
