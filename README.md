# JUDUN signed deployment channel

This repository contains deployment metadata and encrypted payloads only. The VPS accepts a release only when the channel manifest passes its pinned Ed25519 signature check, the live base artifact matches, the encrypted payload SHA256 matches, and post-deploy health/deep-SHA checks pass.

Do not place the payload decryption private key or the release signing private key in this repository.
