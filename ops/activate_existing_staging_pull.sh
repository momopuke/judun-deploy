#!/usr/bin/env bash
# Compatibility alias: the GitHub request bootstrap is now the only supported one.
set -Eeuo pipefail
exec bash "$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)/bootstrap_staging_github_pull.sh" "$@"
