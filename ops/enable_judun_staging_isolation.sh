#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

root=/srv/judun-staging
previous=judun-staging.service
isolated=judun-staging-isolated.service
marker="$root/isolated.enabled"
script_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
launcher="$root/staging_release.py"
unit_dir=/etc/systemd/system

[[ $(id -u) == 0 ]]
[[ -f "$launcher" && ! -L "$launcher" ]]
[[ -x "$root/venv/bin/python" ]]
[[ -f /var/lib/judun-stage-deploy/staging.env ]]
[[ -L "$root/current" ]]
[[ $(stat -c '%u:%a' -- "$root") == 0:755 ]]

[[ ! -L "$root/.lock" ]]
exec 9>>"$root/.lock"
flock -x 9
python3 -I -B "$launcher" status
if [[ -f "$marker" ]] && systemctl is-active --quiet "$isolated"; then
    python3 -I -B "$launcher" probe
    exit 0
fi
[[ ! -e "$marker" && ! -L "$marker" ]]
systemctl is-active --quiet "$previous"
if systemctl is-active --quiet "$isolated" || systemctl is-enabled --quiet "$isolated"; then
    echo 'Unexpected active or enabled isolated service. Preserve it and inspect its configuration.' >&2
    exit 1
fi

install_new_control_file() {
    local src=$1 dest=$2
    if [[ -e "$dest" || -L "$dest" ]]; then
        [[ -f "$dest" && ! -L "$dest" ]] && cmp -s -- "$src" "$dest"
    else
        install -D -o root -g root -m 0644 -- "$src" "$dest"
    fi
}

systemd-analyze verify "$script_dir/$isolated"
install_new_control_file "$script_dir/$isolated" "$unit_dir/$isolated"
install_new_control_file "$script_dir/judun-staging-legacy-guard.conf" "$unit_dir/$previous.d/90-isolated-stage.conf"
systemctl daemon-reload

before=$(systemctl show advisor.service --property=MainPID --property=InvocationID)
armed=0
finish() {
    local status=$?
    trap - EXIT INT TERM
    if (( armed && status != 0 )); then
        systemctl disable --now "$isolated" || true
        rm -f -- "$marker"
        systemctl start "$previous" || true
        echo 'Independent staging cutover failed. Legacy staging restoration attempted.' >&2
    fi
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

armed=1
systemctl enable "$isolated"
install -o root -g root -m 0644 -- /dev/null "$marker"
systemctl stop "$previous"
systemctl start "$isolated"
python3 -I -B "$launcher" probe
[[ "$before" == "$(systemctl show advisor.service --property=MainPID --property=InvocationID)" ]]
armed=0
printf '%s\n' JUDUN_STAGING_ISOLATED_CUTOVER_VERIFIED
