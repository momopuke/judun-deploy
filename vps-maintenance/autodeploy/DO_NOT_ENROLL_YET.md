# Historical unsafe bootstrap hold — current signed read-only enrollment

**Do not run legacy installers** pinned to the initial `autodeploy/pull_agent.py` blob `f92be0a246fc56b763f166097e5b0d0fb85d2480` or bootstrap blob `c4ebe79f94ea7e0bd4c266ecbe75bbf8e946e347`. The initial agent could remove a watchdog's source on an ambiguous operation timeout.

## Current single reviewed candidate
- Official agent immutable commit: `53430996dd856643f3f68c5686afb8b1470114ae`; Git blob `3a7710c85f39f200e4eb03ba3d0df3e25e3894ec`.
- Official one-time bootstrap immutable commit: `ee3693e9913337ae58dc947181e75eb231a3466c`; Git blob `1fbc40b970299eaaffc67bb587fdb3ece7f2a09f`.
- Live signed channel: sequence 1, **operation=status**. First-run `apply` is explicitly refused by the agent. A read-only status runs from a temporary signed source and does not install a new rescue script.
- The bootstrap checks pinned SHA256 values, systemd syntax and first-run signed result; **only after a successful read-only status** does it enable the new timer. The service timeout is 900 seconds to cover the bounded worst-case execution path.
- The agent refuses unsigned/tampered payloads, unsafe symlink parents, an unresolved previous attempt, duplicate releases and unknown operations; it writes a durable in-progress fence before any later signed `apply` release.

## Evidence and scope
- Official agent 24 tests + signed channel 4 tests: five local rounds, **140/140 PASS**.
- The signed v10 memory-safety suite and new regression suite have also passed five local rounds.
- A GitHub Actions offline QA workflow has been published, including an independent check of the **official** pinned agent. This does not prove cloud CI ran or that VPS execution succeeded.
- **New agent NOT YET CONFIRMED ENROLLED ON VPS 142.93.91.214.** The existing `sc-vps-maintenance.timer` supports only `status` and `browser_limit` and cannot self-install the new agent. Current DigitalOcean-connected tools do not provide root shell execution.

## Critical deployment boundary
One authorized VPS-side bootstrap invocation remains necessary. It must use the immutable reviewed bootstrap above and never ask for the root password or signing private key in ChatGPT. After real VPS `status=applied`/`code_installed=false` and timer-active evidence, future `sequence>=2` signed `apply` releases can be published from ChatGPT and automatically fetched by the server.

A green `status` is NOT v10 `--apply` success, proof of actual recordings, Stripchat moderation, FFmpeg health or sustained CPU pressure reduction. Never reset, rebuild, reboot, resize, stop protected production services, or delete video to satisfy enrollment.
