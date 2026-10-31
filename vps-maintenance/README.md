# SC VPS maintenance (separate from JUDUN signed releases)

This branch is **not** consumed by the JUDUN signed release agent. The agent is enabled only after the server owner runs a **one-time pinned bootstrap** on VPS 142.93.91.214. Creating this branch does not install anything.

After enrollment the VPS polls \`vps-maintenance/commands.json\` every ~60 seconds using HTTPS. Only \`status\` and \`browser_limit\` are supported. No remote shell, no downloaded code execution after enrollment, no password or key in repository, no SSH firewall change, and no Docker/LINE/JUDUN modification. A command has an increasing sequence number and is applied once; results stay in the VPS journal and private state file.

Allowlisted browser_limit parameters: 10..40% CPUQuota and 1..100 CPUWeight, **never loosen stricter effective constraints**. Local agent refuses unknown instructions and unknown fields. It writes a managed drop-in and uses runtime systemd properties without restarting the browser, recorder or LINE Guard. Failure attempts rollback but cannot prove full recovery without observing live metrics and a real Stripchat mute/block test.

**Trust difference:** Unlike the independent JUDUN Ed25519+CMS release channel, this restricted maintenance channel trusts authorized GitHub push access. Anyone with push permission can request allowed CPU adjustments; it cannot execute shell commands. The installed agent source is Git-blob-digest pinned and never automatically replaces itself.

Disable: \`systemctl disable --now sc-vps-maintenance.timer\`. Inspect: \`journalctl -u sc-vps-maintenance.service -n 30 --no-pager\`. State: \`/var/lib/sc-vps-maintenance/state.json\`. No arbitrary user actions or other services are trusted.
