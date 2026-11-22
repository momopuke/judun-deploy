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
- Public HTTPS origin: `https://judun.142-93-91-214.sslip.io`; exact route prefix `/__jd_stage_health/v1`

## Server implementation and no-secrets boundary

- Existing isolated staging local HTTP process `http://127.0.0.1:8011` remains unchanged.
- `ops/stage_health_oidc_gateway.py` listens on **127.0.0.1:18762 only**, not `0.0.0.0`. It accepts only three exact read-only GETs:
  - `/__jd_stage_health/v1/health/build`
  - `/__jd_stage_health/v1/health/artifact?deep=true`
  - `/__jd_stage_health/v1/health/ready`
- JWT validation includes RS256 signature via pinned GitHub JWKS HTTPS (no redirect), exact issuer, audience, repository owner ID/repository ID/name, branch, workflow reference and event, issued/expiration times. Invalid JWTs and other paths FAIL closed. Upstream response JSON is filtered to the exact public health identity/verification fields; never forwards database/customer/PDF/email/secret fields. No JWT/header/request URI logging.
- `ops/judun-stage-health-oidc.service` uses a dynamic unprivileged systemd account, hardening, resource limits and restart. It does not change existing VPS production service, keys, agent or DB.
- GitHub existing release PR gate and 60-second final verification now obtain short-lived OIDC identity using `p3/stage_oidc_client.py`. Their jobs have scoped `id-token: write` and **no** `JUDUN_STAGE_AUTH_TOKEN` secret. Release PR must check exact staged candidate and paid-mode isolation before merge; post-release remains fail-closed.

## HTTPS reverse proxy integration (requires current VPS config review)

**Do not paste a generic config over existing production nginx/Caddy.** Before activation, inspect `nginx -T` or current Caddy route and the exact real TLS vhost. Back up the relevant existing config, stage a location prefix forwarding *only* `/__jd_stage_health/v1/` to `http://127.0.0.1:18762`. Preserve the `Authorization` header, original request URI and query string; disable cache/request body; configure short timeouts and TLS. Example *only if* this vhost uses nginx:

```nginx
location ^~ /__jd_stage_health/v1/ {
    proxy_pass http://127.0.0.1:18762;
    proxy_http_version 1.1;
    proxy_set_header Authorization $http_authorization;
    proxy_set_header Host 127.0.0.1;
    proxy_pass_request_body off;
    proxy_set_header Content-Length "";
    proxy_buffering off;
    proxy_read_timeout 8s;
    add_header Cache-Control "no-store" always;
}
```

This is **not** a public staging site: all OIDC JWTs are verified at the local gateway before any stage health read. All other requests are 403/405. Do not expose port 18762 on public interfaces or open private staging owner login.

## Controlled activation sequence; stop safely on any fault

1. Confirm current VPS isolated staging service is ready, source file SHA pinned to protected merged main, `python3-cryptography` available. Install the unmodified `ops/stage_health_oidc_gateway.py` into root-owned `/srv/judun-stage-health-oidc/` and systemd unit, then locally test refusal with no JWT. Verify `ss -lntp` listener on **127.0.0.1:18762 only**; keep original stage/prod untouched.
2. Safely add scoped HTTPS proxy route within existing vhost only after its actual config is read. Validate `nginx -t` (or Caddy equivalent) before reload. Unauthenticated HTTPS GET must return **403**, never public health data, and unrelated production routes must still pass.
3. Use an authorized `workflow_dispatch` of original `Verify JUDUN signed release and production` to get a real GitHub Actions JWT. Require exact v190 build/tree/98 of both live and isolated stage, correct `ecpay_live` / `test_unlock`, initial and **60-second recheck** with a genuine final artifact. Do not treat offline tests as this proof.
4. Before next signed v191+ PR, verify the protected trusted `judun/release-gate` confirms the **same candidate SHA** on stage; invalid OIDC, older stage, wrong issuer/ref/workflow, mismatch of artifact/build/payment all must block release before merge. Then original authorized signer, original VPS agent and rollback need separately demonstrated E2E.
5. If any service/proxy test fails, restore the backed-up proxy config and disable only `judun-stage-health-oidc.service`. Do not roll back the existing production application for this read-only integration.

The service needs the Debian `python3-cryptography` package and outbound TLS access to the fixed GitHub JWKS host. No persistent token, GitHub Repository Secret, Sites owner credential or private Ed25519/CMS key is required.

References: GitHub official OIDC docs https://docs.github.com/en/actions/reference/security/oidc ; project record https://github.com/momopuke/judun-deploy/issues/22 .
