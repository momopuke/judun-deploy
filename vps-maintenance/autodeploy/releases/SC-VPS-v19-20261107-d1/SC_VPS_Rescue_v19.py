#!/usr/bin/env python3
"""Read-only overnight CPU attribution, with an encrypted summary."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import SC_VPS_Rescue_v15 as telemetry
from SC_VPS_Rescue_v17 import PUBLIC_KEY

TZ = ZoneInfo('Asia/Taipei')
ROOT = Path('/var/lib/sc-vps-cpu-diag-v19')
SOURCE = Path('/root/sc-vps-rescue-v19/SC_VPS_Rescue_v19.py')
CRON = Path('/etc/cron.d/sc-vps-cpu-diag-v19')
UNIT = 'sc-vps-cpu-diag-v19'
INTERVAL = 5
DURATION = 1800
TICKS = os.sysconf('SC_CLK_TCK')
DOCKER = re.compile(r'(?:^|/)(?:docker/|docker-)([0-9a-f]{64})(?:\.scope)?(?:/|$)')
NAME = re.compile(r'[^a-zA-Z0-9_.+@-]')
STAMP = re.compile(r'^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s')
ACTIVITY = re.compile(r'\b(MERGE|UPLOAD|RCLONE)\b', re.IGNORECASE)
RUN = [
    '/usr/bin/systemd-run', '--quiet', '--collect',
    '--property=CPUQuota=5%', '--property=MemoryMax=40M',
    '--property=RuntimeMaxSec=32min', '--property=Nice=19', '--property=UMask=0077',
    '/usr/bin/python3', '-B', str(SOURCE),
]
CRON_TEXT = (
    '# SC-VPS-CPU-DIAG-MANAGED-v19\n'
    r'*/5 * * * * root case "$(/usr/bin/env TZ=Asia/Taipei /bin/date +\%H\%M)" in '
    '0320|0420) /usr/bin/python3 -B ' + str(SOURCE) + ' --dispatch ;; esac\n'
).encode()


def process_stat(raw):
    before, end, after = raw.rpartition(')')
    pid, start, name = before.partition(' (')
    fields = after.split()
    if not end or not start or len(fields) < 20:
        raise ValueError('bad_proc_stat')
    return (int(pid), int(fields[19])), NAME.sub('_', name)[:24], int(fields[11]) + int(fields[12])


def container_path(raw):
    for line in raw.splitlines():
        hierarchy, separator, path = line.partition('::')
        if hierarchy == '0' and separator and path.startswith('/') and '..' not in path.split('/'):
            match = DOCKER.search(path)
            if match:
                scope_end = match.end(1)
                if path[scope_end:].startswith('.scope'):
                    scope_end += len('.scope')
                return match[1], Path('/sys/fs/cgroup' + path[:scope_end])
    return None


def container_counters(root=Path('/sys/fs/cgroup')):
    scopes = list((root / 'system.slice').glob('docker-*.scope'))
    docker_root = root / 'docker'
    if docker_root.is_dir():
        scopes.extend(docker_root.iterdir())
    counters = {}
    for scope in scopes:
        identity = DOCKER.search(str(scope))
        if identity:
            counters[identity[1]] = container_usage(scope)
    return counters


def container_usage(path):
    try:
        fields = dict(line.split() for line in (path / 'cpu.stat').read_text().splitlines())
        return int(fields['usage_usec'])
    except (OSError, ValueError, KeyError):
        return None


def snapshot():
    measured = time.monotonic()
    epoch = time.time()
    with open('/proc/stat', encoding='ascii') as handle:
        system = list(map(int, handle.readline().split()[1:9]))
    containers = container_counters()
    processes = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdecimal():
            continue
        try:
            identity, name, ticks = process_stat((entry / 'stat').read_text(errors='replace'))
            processes[identity] = (name, ticks)
            info = container_path((entry / 'cgroup').read_text())
            if info and info[0] not in containers:
                containers[info[0]] = container_usage(info[1])
        except (OSError, ValueError):
            continue
    return measured, epoch, system, processes, containers


def top_processes(before, after, seconds):
    totals = Counter()
    for identity, (name, ticks) in after.items():
        previous = before.get(identity)
        if previous and ticks > previous[1]:
            totals[name] += ticks - previous[1]
    return [[name, round(ticks * 100 / TICKS / seconds, 1)] for name, ticks in totals.most_common(3)]


def interval(before, after):
    elapsed = after[0] - before[0]
    counters = [new - old for old, new in zip(before[2], after[2])]
    total = sum(counters)
    if elapsed <= 0 or total <= 0 or min(counters) < 0:
        return None
    containers = {}
    for identity, value in after[4].items():
        old = before[4].get(identity)
        if value is not None and old is not None and value > old:
            containers[identity] = round((value - old) / elapsed / 10000, 1)
    return {
        'ts': int(after[1]), 'sec': round(elapsed, 2),
        'cpu': round(100 * (total - counters[3] - counters[4] - counters[7]) / total, 1),
        'io': round(100 * counters[4] / total, 1),
        'steal': round(100 * counters[7] / total, 1),
        'p': top_processes(before[3], after[3], elapsed),
        'c': sorted(containers.items(), key=lambda pair: -pair[1])[:3],
    }


def window(epoch):
    local = datetime.fromtimestamp(epoch, TZ)
    start = local.replace(hour=3, minute=20, second=0, microsecond=0)
    return start.timestamp(), (start + timedelta(seconds=DURATION)).timestamp()


def docker_names():
    try:
        output = telemetry.cmd('/usr/bin/docker', 'ps', '-a', '--no-trunc',
                               '--format', '{{.ID}} {{.Names}}', timeout=8)
    except telemetry.Refused:
        return {}
    names = {}
    for line in output.splitlines():
        identity, _, name = line.partition(' ')
        if re.fullmatch(r'[0-9a-f]{64}', identity) and name:
            names[identity] = NAME.sub('_', name)[:28]
    return names


def log_activity(lines, peak, timezone=None):
    counts = Counter()
    for line in lines:
        stamp = STAMP.match(line)
        action = ACTIVITY.search(line) if stamp else None
        if not action:
            continue
        try:
            timestamp = datetime.fromisoformat(stamp[1])
            if timezone is not None:
                timestamp = timestamp.replace(tzinfo=timezone)
            if abs(timestamp.timestamp() - peak) <= 60:
                counts[action[1].upper()] += 1
        except ValueError:
            continue
    return [counts[kind] for kind in ('MERGE', 'UPLOAD', 'RCLONE')]


def upload_activity(peak):
    path = Path('/tmp/auto_upload.log')
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0:
                return None
            handle.seek(max(0, info.st_size - 262144))
            lines = handle.read(262144).decode(errors='replace').splitlines()
    except OSError:
        return None
    if not any(STAMP.match(line) for line in lines):
        return None
    # Check VPS local time and Taipei time independently when the log zone is unknown.
    local = log_activity(lines, peak)
    taipei = log_activity(lines, peak, TZ)
    return {'local': local, 'taipei': taipei}


def summarize(samples, start, end, names):
    result = {'st': 'complete', 'start': int(start), 'end': int(end), 'n': len(samples)}
    if not samples:
        return result
    spikes = [row for row in samples if row['cpu'] >= 85]
    peak = max(samples, key=lambda row: row['cpu'])
    process_totals = Counter()
    container_totals = Counter()
    for row in spikes:
        process_totals.update(dict(row['p']))
        container_totals.update(dict(row['c']))
    result.update(
        high=len(spikes),
        peak=[peak['ts'], peak['cpu'], peak['io'], peak['p'],
              [[names.get(key, key[:12]), cpu] for key, cpu in peak['c']]],
        recurring=[process_totals.most_common(2), [
            [names.get(key, key[:12]), cpu] for key, cpu in container_totals.most_common(2)
        ]],
        upload=upload_activity(peak['ts']) if spikes else None,
        steal=peak['steal'],
        gaps=sum(row['sec'] > INTERVAL * 1.5 for row in samples),
    )
    return result


def deliver(data):
    telemetry.PUBLIC_KEY = PUBLIC_KEY
    payload = {'v': 19, 'k': 'cpu_diag', 'seq': 19, 'ts': int(time.time()), **data}
    try:
        packet = telemetry.encrypt(payload)
    except telemetry.Refused as error:
        if str(error) != 'report_payload_too_large' or 'recurring' not in payload:
            raise
        # Preserve the peak and activity evidence when process names are unusually long.
        payload.pop('recurring')
        packet = telemetry.encrypt(payload)
    for url in (telemetry.UPLINK.replace('https://ntfy.sh/', 'https://ntfy.envs.net/'), telemetry.UPLINK):
        request = urllib.request.Request(url, data=packet, method='POST', headers={
            'Content-Type': 'text/plain', 'Title': 'SC VPS encrypted CPU diagnosis v19',
            'Priority': '1', 'User-Agent': 'SCVPS-diagnostics-v19/1',
        })
        try:
            with urllib.request.urlopen(request, timeout=12) as response:
                if response.status in (200, 201):
                    return
        except (urllib.error.URLError, TimeoutError):
            continue
    raise telemetry.Refused('relay_unavailable')


def collect():
    entered = time.time()
    start, end = window(entered)
    if not start <= entered < start + 60:
        return
    with (ROOT / 'sample.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        day = datetime.fromtimestamp(start, TZ).strftime('%Y%m%d')
        samples_path = ROOT / (day + '.jsonl')
        if samples_path.exists():
            return
        with samples_path.open('x', encoding='ascii', buffering=1) as handle:
            rows = []
            previous = snapshot()
            limit = previous[0] + end - previous[1]
            deadline = previous[0] + INTERVAL
            while deadline <= limit + 0.1:
                time.sleep(max(0, deadline - time.monotonic()))
                current = snapshot()
                row = interval(previous, current)
                if row:
                    rows.append(row)
                    handle.write(json.dumps(row, separators=(',', ':')) + '\n')
                previous = current
                deadline += INTERVAL
                while deadline < current[0]:
                    deadline += INTERVAL
        summary = summarize(rows, start, end, docker_names())
        telemetry.safe_write(ROOT / 'latest.json', summary)
        for old in ROOT.glob('[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].jsonl'):
            if old.stat().st_mtime < start - 7 * 86400:
                old.unlink()
        deliver(summary)


def smoke():
    before = snapshot()
    time.sleep(0.5)
    after = snapshot()
    if not before[3] or not after[3] or interval(before, after) is None:
        raise telemetry.Refused('sample_smoke_failed')
    print('CPU_DIAG_SAMPLE_OK', flush=True)


def dispatch():
    now = time.time()
    start, _ = window(now)
    if start <= now < start + 60:
        telemetry.cmd(*RUN[:3], '--unit=' + UNIT, *RUN[3:], '--collect')
    if datetime.fromtimestamp(now, TZ).strftime('%H:%M') == '04:20':
        latest = telemetry.read_json(ROOT / 'latest.json')
        if latest.get('start') == int(start):
            telemetry.cmd(*RUN[:3], '--unit=' + UNIT + '-retry', *RUN[3:], '--retry')


def cron_content():
    if CRON.is_symlink():
        raise telemetry.Refused('cron_path_conflict')
    try:
        status = CRON.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(status.st_mode) or status.st_uid != 0 or status.st_mode & 0o022:
        raise telemetry.Refused('cron_path_conflict')
    return CRON.read_bytes()


def install():
    if os.geteuid() != 0 or SOURCE.is_symlink() or not SOURCE.is_file():
        raise telemetry.Refused('signed_root_source_required')
    old = cron_content()
    if old is not None and old != CRON_TEXT:
        raise telemetry.Refused('foreign_cron_conflict')
    if telemetry.cmd('/usr/bin/systemctl', 'is-active', 'cron.service') != 'active':
        raise telemetry.Refused('cron_inactive')
    telemetry.cmd(*RUN[:3], '--wait', '--unit=' + UNIT + '-smoke', *RUN[3:], '--smoke', timeout=20)
    ROOT.mkdir(mode=0o700, exist_ok=True)
    if ROOT.is_symlink() or ROOT.stat().st_uid != 0 or ROOT.stat().st_mode & 0o077:
        raise telemetry.Refused('state_path_conflict')
    created = False
    try:
        if old is None:
            fd, temporary = tempfile.mkstemp(prefix='.sc-vps-v19-', dir=CRON.parent)
            try:
                with os.fdopen(fd, 'wb') as handle:
                    os.fchmod(handle.fileno(), 0o644)
                    handle.write(CRON_TEXT)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.link(temporary, CRON)
                created = True
            finally:
                os.unlink(temporary)
        if cron_content() != CRON_TEXT:
            raise telemetry.Refused('cron_readback_failed')
        start, _ = window(time.time())
        if start < time.time():
            start = (datetime.fromtimestamp(start, TZ) + timedelta(days=1)).timestamp()
        result = {'st': 'installed', 'cron': True, 'smoke': True, 'next': int(start), 'step': INTERVAL}
        telemetry.safe_write(ROOT / 'installation.json', result)
        deliver(result)
    except Exception:
        if created and cron_content() == CRON_TEXT:
            CRON.unlink()
        raise
    print('SC_VPS_V19_CPU_DIAG_INSTALLED', flush=True)


def rollback():
    if os.geteuid() != 0:
        raise telemetry.Refused('root_required')
    body = cron_content()
    if body is not None:
        if body != CRON_TEXT:
            raise telemetry.Refused('foreign_cron_conflict')
        CRON.unlink()


def retry():
    latest = telemetry.read_json(ROOT / 'latest.json')
    if latest.get('start') == int(window(time.time())[0]):
        deliver(latest)


def main():
    actions = {
        'apply': install, 'collect': collect, 'dispatch': dispatch, 'smoke': smoke,
        'retry': retry, 'rollback': rollback,
        'status': lambda: print(json.dumps({'scheduled': cron_content() == CRON_TEXT,
                                            'latest': telemetry.read_json(ROOT / 'latest.json')})),
    }
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in actions:
        mode.add_argument('--' + name, action='store_const', const=name, dest='action')
    args = parser.parse_args()
    actions[args.action]()


if __name__ == '__main__':
    try:
        main()
    except (telemetry.Refused, OSError, ValueError) as error:
        print('SC_VPS_V19_SAFE_ABORT', type(error).__name__, str(error)[:90], flush=True)
        raise SystemExit(3)
