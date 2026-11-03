# SC VPS signed-auto-deploy: HOLD — do not enroll yet

**Status: STAGED ONLY.** Source code, an immutable v10 payload, and a signed manifest are available for audit, but this GitHub publication does NOT mean the server has installed or executed the new agent.

The initial pull-agent revision has a known safety defect: when a v10 operation fails with an uncertain rollback watchdog state, it can restore the downloaded Python source too early, leaving the independent watchdog without the expected source path. A locally tested correction exists, but its GitHub publication has not succeeded. Therefore **do not run the published autodeploy/bootstrap.sh** or represent this channel as production ready.

Existing, separately installed sc-vps-maintenance.timer only allows status/browser_limit. It is not an arbitrary deployment agent, and no current DigitalOcean connector action provides SSH or Console command execution.

Before enrollment: publish corrected and independently reviewed pull agent; pin bootstrap to that exact blob; run signature/integrity, rollback/watchdog and service-preservation tests; then authorize one single installation on VPS. Never manipulate JUDUN signed releases, recorder, Gateway, or LINE Guard.

No VPS configuration has been modified by this staged GitHub channel. The v10 host acceptance and real moderation remain unverified.
