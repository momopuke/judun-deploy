#!/usr/bin/env python3
"""Narrow-scoped VPS maintenance pull agent (v2). Never executes remote-supplied code."""
from __future__ import annotations
import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

CHANNEL = 'https://raw.githubusercontent.com/momopuke/judun-deploy/vps-maintenance/vps-maintenance/commands.json'
UNIT = 'stripchat-browser-desktop.service'
STATE = Path('/var/lib/sc-vps-maintenance/state.json')
DROPIN = Path('/etc/systemd/system/stripchat-browser-desktop.service.d/90-sc-vps-maintenance.conf')
HEADER = '# SC-VPS-MAINTENANCE-MANAGED v1\n'

class Blocked(Exception):
    pass

def proc(*args: str) -> str:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=16, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked(f'COMMAND_UNAVAILABLE {args[0]}') from exc
    if p.returncode != 0:
        raise Blocked(f'COMMAND_FAILED {args[0]} rc={p.returncode}')
    return p.stdout.strip()

def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    if path.is_symlink() or path.stat().st_size > 8192:
        raise Blocked('STATE_UNSAFE')
    obj = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(obj, dict):
        raise Blocked('STATE_FORMAT')
    return obj

def atomic_bytes(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    if path.is_symlink():
        raise Blocked('SYMLINK_TARGET')
    fd, temp = tempfile.mkstemp(prefix='.scmaint-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as fp:
            os.fchmod(fp.fileno(), mode)
            fp.write(data)
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def fetch() -> dict:
    request = Request(CHANNEL, headers={'User-Agent': 'SC-VPS-Maintenance/1', 'Cache-Control':'no-cache'})
    with urlopen(request, timeout=20) as res:
        if res.status != 200:
            raise Blocked('CHANNEL_HTTP')
        raw = res.read(4097)
    if len(raw) > 4096 or len(raw) < 10:
        raise Blocked('CHANNEL_LENGTH')
    try:
        doc = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise Blocked('CHANNEL_INVALID_JSON') from exc
    if type(doc) is not dict or doc.get('schema') != 'sc-vps-ops/v1':
        raise Blocked('CHANNEL_SCHEMA')
    if set(doc) != {'schema', 'seq', 'operation', 'quota_percent', 'cpu_weight', 'note'}:
        raise Blocked('CHANNEL_FIELDS')
    if type(doc['seq']) is not int or not (1 <= doc['seq'] <= 1000000):
        raise Blocked('CHANNEL_SEQUENCE')
    if doc['operation'] not in ('status', 'browser_limit'):
        raise Blocked('OP_NOT_ALLOWED')
    if type(doc['quota_percent']) is not int or not (10 <= doc['quota_percent'] <= 40):
        raise Blocked('QUOTA_RANGE')
    if type(doc['cpu_weight']) is not int or not (1 <= doc['cpu_weight'] <= 100):
        raise Blocked('WEIGHT_RANGE')
    if type(doc['note']) is not str or len(doc['note']) > 140:
        raise Blocked('NOTE_INVALID')
    return doc

def cpu_percent(s: str) -> float:
    s = s.strip().lower()
    if s in ('infinity', 'max', ''):
        return math.inf
    m = re.fullmatch(r'(\d+(?:\.\d+)?)(us|ms|s|min)', s)
    if not m:
        raise Blocked('UNKNOWN_SYSTEMD_CPU_QUOTA')
    ms = float(m[1]) * {'us': .001, 'ms': 1, 's': 1000, 'min': 60000}[m[2]]
    return round(ms / 10, 4)

def get_unit() -> dict:
    if proc('systemctl', 'show', UNIT, '-p', 'LoadState', '--value') != 'loaded':
        raise Blocked('BROWSER_UNIT_NOT_LOADED')
    active = proc('systemctl', 'is-active', UNIT) if proc('systemctl', 'show', UNIT, '-p', 'ActiveState', '--value') == 'active' else 'inactive'
    return {
        'active': active,
        'quota': proc('systemctl', 'show', UNIT, '-p', 'CPUQuotaPerSecUSec', '--value'),
        'weight': proc('systemctl', 'show', UNIT, '-p', 'CPUWeight', '--value'),
    }

def cpu_psi() -> str:
    try:
        line = next(s for s in Path('/proc/pressure/cpu').read_text().splitlines() if s.startswith('some '))
        return re.search(r'avg10=([0-9.]+)', line).group(1)
    except (OSError, StopIteration, AttributeError):
        return 'unknown'

def apply_limit(doc: dict) -> dict:
    before = get_unit()
    if before['active'] != 'active':
        raise Blocked('BROWSER_NOT_ACTIVE_NO_MUTATION')
    if DROPIN.exists():
        if DROPIN.is_symlink():
            raise Blocked('DROPIN_SYMLINK')
        existing = DROPIN.read_bytes()
        if not existing.startswith(HEADER.encode()):
            raise Blocked('DROPIN_NOT_OWNED')
    else:
        existing = None
    previous_quota = before['quota']
    previous_weight = before['weight']
    quota = min(cpu_percent(previous_quota), doc['quota_percent'])
    if not math.isfinite(quota):
        quota = doc['quota_percent']
    # systemd's unset CPUWeight uses the cgroup-v2 kernel default (100).
    # `systemctl show` can return 'unset' or '[not set]', not an integer.
    previous_weight_clean = previous_weight.strip().lower()
    if previous_weight_clean in ('unset', '[not set]', ''):
        old_weight = 100
        rollback_weight = '100'
    else:
        try:
            old_weight = int(previous_weight_clean)
        except ValueError as exc:
            raise Blocked('WEIGHT_NOT_NUMERIC') from exc
        if not (1 <= old_weight <= 10000):
            raise Blocked('WEIGHT_OUT_OF_RANGE')
        rollback_weight = previous_weight
    weight = min(old_weight, doc['cpu_weight'])
    config = f'{HEADER}[Service]\nCPUQuota={quota:g}%\nCPUWeight={weight}\n'.encode()
    if existing == config:
        return {'effect': 'already_set', 'before': before, 'after': get_unit(), 'psi10': cpu_psi()}
    changed = False
    try:
        atomic_bytes(DROPIN, config, mode=0o644)
        changed = True
        proc('systemctl', 'daemon-reload')
        proc('systemctl', 'set-property', '--runtime', UNIT, f'CPUQuota={quota:g}%', f'CPUWeight={weight}')
        after = get_unit()
        if after['active'] != 'active':
            raise Blocked('BROWSER_LOST_ACTIVE_STATE')
        if cpu_percent(after['quota']) > quota + 0.01:
            raise Blocked('QUOTA_NOT_EFFECTIVE')
        try:
            if int(after['weight']) > weight:
                raise Blocked('WEIGHT_NOT_EFFECTIVE')
        except ValueError as exc:
            raise Blocked('WEIGHT_AFTER_INVALID') from exc
    except Exception:
        if changed:
            try:
                if existing is None:
                    DROPIN.unlink(missing_ok=True)
                else:
                    atomic_bytes(DROPIN, existing, mode=0o644)
                proc('systemctl', 'daemon-reload')
                proc('systemctl', 'set-property', '--runtime', UNIT,
                     f'CPUQuota={"infinity" if math.isinf(cpu_percent(previous_quota)) else str(cpu_percent(previous_quota)) + "%"}', f'CPUWeight={rollback_weight}')
            except Exception:
                print('ROLLBACK_NOT_VERIFIED', flush=True)
        raise
    return {'effect':'applied', 'before':before, 'after':after, 'psi10':cpu_psi()}

def run_once() -> int:
    if os.geteuid() != 0:
        print('BLOCKED_NOT_ROOT')
        return 6
    try:
        doc = fetch()
        state = read_json(STATE)
        if doc['seq'] <= int(state.get('last_seq', 0)):
            print(f"NOOP_ALREADY_HANDLED seq={doc['seq']} last={state.get('last_seq')}")
            return 0
        result = ({'effect':'status', 'unit':get_unit(), 'psi10':cpu_psi()}
                  if doc['operation'] == 'status' else apply_limit(doc))
        out = {'last_seq':doc['seq'], 'operation':doc['operation'], 'result':result, 'status':'applied'}
        atomic_bytes(STATE, json.dumps(out, ensure_ascii=False, sort_keys=True).encode())
        print('SC_VPS_OPS_APPLIED', json.dumps(out, ensure_ascii=False, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        message = str(exc) if isinstance(exc, Blocked) else exc.__class__.__name__
        print(f'SC_VPS_OPS_BLOCKED {message}', flush=True)
        return 5

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if args.check:
        assert CHANNEL.startswith('https://raw.githubusercontent.com/momopuke/judun-deploy/vps-maintenance/')
        assert UNIT == 'stripchat-browser-desktop.service'
        print('SC_VPS_AGENT_STATIC_CHECK_PASS')
        sys.exit(0)
    sys.exit(run_once())
