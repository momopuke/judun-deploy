# SC VPS signed auto-deploy — controlled read-only enrollment candidate

**Legacy bootstrap is prohibited:** Do NOT run `vps-maintenance/autodeploy/bootstrap.sh`. It pins the old agent, which can remove a watchdog's source on an ambiguous child timeout. This document remains intentionally named `DO_NOT_ENROLL_YET` to protect the legacy command.

## Audited candidate
- Agent: `vps-maintenance/autodeploy/review/pull_agent_v5.py`, immutable source commit `2e7b8ee9ab46b965adc634eb9ef74da4cd202096`.
- One-time installer: `vps-maintenance/autodeploy/review/bootstrap_v5.sh`, immutable installer commit `6406db25f73d3c22922c093297ff135a33e8b119`.
- New agent explicitly refuses an initial `apply` or `rollback`. The signed channel is currently sequence 1, **`status` only**.
- `status` executes the signed v10 status subcommand from a temporary location, without changing the installed v10 source or production systemd settings.
- The installer verifies pinned SHA256 values, runs the signed status first, checks state, and only then enables the timer. If the first read-only check fails, no timer is enabled.
- systemd `TimeoutStartSec` has been raised from 260s to 900s to cover the worst-case bounded download + five preflight rounds + child operation time.

## Safety regression evidence (local simulation only)
- Ed25519 signed channel verification: PASS; signed payload file SHA256 match: 7/7.
- v10 memory-safety tests: five rounds PASS.
- v5 first-run and rollback/timeout tests: 10 tests x five rounds PASS.
- Legacy simulation: 8/8 scenarios PASS after test-fixture corrections.
- `review/bootstrap_v5.sh` static safety and syntax tests PASS.
- GitHub Actions offline QA workflow is published. A GitHub commit is not proof of a VPS deployment.

## Deployment boundary
**The reviewed v5 candidate has NOT been installed on VPS 142.93.91.214.** The already installed `sc-vps-maintenance.timer` cannot execute new agents, and DigitalOcean connected API does not provide root-shell command execution. A one-time authorized VPS terminal invocation of the reviewed bootstrap is still required before subsequent signed releases can deploy automatically.

After read-only enrollment reports success on the VPS, a separate signed sequence 2 `apply` may be published; v10 will independently refuse unsafe persistence. Neither a successful service state nor GitHub QA can prove real Stripchat moderation, uninterrupted recording output or reduced long-term CPU pressure. Do not declare project complete before those host-level checks.

Never share root password, private signing key, streaming credentials, customer information or private logs in the public repository. Never reset, rebuild, resize, reboot or stop protected services merely to enroll.
