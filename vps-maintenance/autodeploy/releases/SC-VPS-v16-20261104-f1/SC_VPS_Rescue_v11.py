#!/usr/bin/env python3
"""SC VPS Rescue v11 - bounded second-stage browser cgroup memory.high trial.

Only touches *runtime* MemoryHigh for the existing Chromium service. Refuses to
change policy if v10 has committed or the V9 verified runtime baseline differs.
Never stops/restarts a service or container, reads streaming data or credentials,
or changes persistent systemd config. Independent systemd watchdog is armed before
any mutation. If there is no measurable benefit, restore the previous limit.
"""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import sys
import time

import SC_VPS_Base_ReadOnly as base
import SC_VPS_Rescue_v9 as v9
import SC_VPS_Rescue_v10 as v10

VERSION = '11.0.0'
ROOT = Path('/var/lib/sc-vps-rescue-v11')
SOURCE = Path('/root/sc-vps-rescue-v11/SC_VPS_Rescue_v11.py')
MiB = 1024 * 1024
TARGET_INCREMENT = 64 * MiB
MAX_TARGET = 672 * MiB
WINDOW_SECS = 12
POST_WINDOWS = 4
WATCHDOG_SECS = 160
BASELINE_HIGH = 546 * MiB

class SafetyError(RuntimeError): pass


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(path, state):
    base.write_json(path, state)


def read_state(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 30000:
        raise SafetyError('state_file_invalid')
    x = json.loads(path.read_text(encoding='utf8'))
    if not isinstance(x, dict):
        raise SafetyError('state_not_mapping')
    return x


def v10_refusal_ok():
    runs = sorted((v10.ROOT / 'runs').glob('*/state.json'), reverse=True)
    if not runs: return False
    try:
        x = read_state(runs[0])
    except (OSError, ValueError, SafetyError):
        return False
    return (x.get('version') == v10.VERSION and
            x.get('status') == 'diagnosis_only' and
            x.get('reason') == 'memory_full_still_high' and
            x.get('changes') == [] and
            len(x.get('windows', [])) == 4)


def get_service_identity():
    u = base.unit_state(base.BROWSER)
    if u.get('ActiveState') != 'active' or u.get('MainPID') in ('', '0'):
        raise SafetyError('browser_not_active')
    return {'pid': u['MainPID'], 'active': u['ActiveState']}


def get_container_identities():
    out = {n: base.docker_state(n) for n in base.REQUIRED_CONTAINERS}
    if any(not x['running'] or not x['id'] for x in out.values()):
        raise SafetyError('recording_container_not_running')
    return {n: x['id'] for n, x in out.items()}


def identities_ok(p, browser, containers):
    try:
        return (str(v9.browser_group()) == str(p) and
                get_service_identity() == browser and
                get_container_identities() == containers)
    except (SafetyError, v9.SafetyError, OSError):
        return False


def measure(a, b):
    w = v9.interval(a, b)
    d = w['seconds']
    return {
        'seconds': d,
        'memory_full_pct': w['mem_full_pct'],
        'io_full_pct': w['io_full_pct'],
        'high_events_per_s': round(w['browser_high_events'] / d, 1) if d > 0 and w['browser_high_events'] is not None else None,
        'major_faults_per_s': round(w['browser_major_faults'] / d, 1) if d > 0 and w['browser_major_faults'] is not None else None,
        'oom_kill': w['browser_oom_kill'],
        'ram_available_mib': w['available_mib'],
        'swap_free_mib': w['swap_free_mib'],
        'memory_current_mib': w['used_mib'],
        'memory_high_mib': w['high_mib'],
    }


def baseline_reason(w, before, high):
    fields = ('memory_full_pct', 'io_full_pct', 'high_events_per_s', 'major_faults_per_s',
              'oom_kill', 'ram_available_mib', 'swap_free_mib')
    if any(w.get(k) is None for k in fields) or w.get('seconds', 0) < 9:
        return 'incomplete_live_counters'
    if w['memory_full_pct'] < 15:
        return 'global_memory_pressure_not_confirmed'
    if w['io_full_pct'] > 5:
        return 'host_io_pressure_too_high'
    if w['high_events_per_s'] < 100:
        return 'browser_high_throttle_not_confirmed'
    if w['major_faults_per_s'] > 250:
        return 'major_faults_too_high_before_trial'
    if w['oom_kill'] != 0:
        return 'browser_oom_before_trial'
    if w['ram_available_mib'] < 475 or w['swap_free_mib'] < 400:
        return 'reserve_too_low_before_trial'
    if before['current_bytes'] is None or before['high_bytes'] != high:
        return 'invalid_browser_current_or_high'
    if not high - 16 * MiB <= before['current_bytes'] <= high + 128 * MiB:
        return 'browser_usage_outside_expected_range'
    if before['max_bytes'] is not None and before['max_bytes'] <= high + TARGET_INCREMENT + 32 * MiB:
        return 'memory_max_too_close'
    return None


def unsafe_post(w):
    fields = ('memory_full_pct', 'io_full_pct', 'high_events_per_s', 'major_faults_per_s',
              'oom_kill', 'ram_available_mib', 'swap_free_mib')
    if any(w.get(k) is None for k in fields) or w.get('seconds', 0) < 9:
        return 'post_sample_incomplete'
    if w['oom_kill'] != 0 or w['ram_available_mib'] < 350 or w['swap_free_mib'] < 260:
        return 'post_memory_reserve_or_oom'
    if w['io_full_pct'] > 8 or w['memory_full_pct'] > 55:
        return 'post_pressure_unsafe'
    if w['major_faults_per_s'] > 250:
        return 'post_major_faults_unsafe'
    return None


def improved(baseline, windows):
    if len(windows) != POST_WINDOWS: return False
    good_pressure = sum(w['memory_full_pct'] <= max(5, baseline['memory_full_pct'] * .78) and
                        baseline['memory_full_pct'] - w['memory_full_pct'] >= 7 for w in windows)
    good_high = sum(w['high_events_per_s'] <= baseline['high_events_per_s'] * .5 for w in windows)
    good_fault = sum(w['major_faults_per_s'] <= max(150, baseline['major_faults_per_s'] * 2) for w in windows)
    return good_pressure >= 3 and good_high >= 3 and good_fault >= 3


def expected_limit(p, expected):
    actual = v9.asnum(v9.r(p / 'memory.high'))
    reported = v9.asnum(base.get_prop(base.BROWSER, 'MemoryHigh'))
    return actual == expected and reported == expected


def set_high(p, old, new):
    if not expected_limit(p, old): raise SafetyError('concurrent_memory_high_change')
    rc, _, _ = base.run('systemctl', 'set-property', '--runtime', base.BROWSER,
                        f'MemoryHigh={new}', timeout=25)
    if rc != 0: raise SafetyError('runtime_memory_high_write_failed')
    if not expected_limit(p, new): raise SafetyError('runtime_memory_high_verification_failed')


def path_ok(f):
    return (f.is_absolute() and ROOT in f.parents and f.name == 'state.json'
            and f.parent.parent.name == 'runs')


def watchdog(path):
    base.require_root()
    if not path_ok(path): raise SafetyError('invalid_watchdog_path')
    st = read_state(path)
    if st.get('version') != VERSION or st.get('status') not in ('trial_pending', 'trial_applied', 'trial_running', 'needs_review'):
        print('V11_WATCHDOG_NO_ACTION'); return 0
    p = v9.browser_group()
    if str(p) != st.get('browser_cgroup'):
        raise SafetyError('watchdog_browser_group_changed')
    old, new = st.get('old_high'), st.get('target_high')
    if not isinstance(old, int) or not isinstance(new, int) or old != BASELINE_HIGH or new != old + TARGET_INCREMENT:
        raise SafetyError('watchdog_invalid_limit_state')
    if expected_limit(p, new):
        set_high(p, new, old)
        st['status'] = 'watchdog_reverted'; st['watchdog_at'] = now(); save(path, st)
        print('V11_WATCHDOG_REVERTED_RUNTIME_ONLY'); return 0
    if expected_limit(p, old):
        st['status'] = 'watchdog_already_old'; st['watchdog_at'] = now(); save(path, st)
        print('V11_WATCHDOG_ALREADY_OLD'); return 0
    raise SafetyError('watchdog_external_limit_change_refusing_overwrite')


def start_watchdog(path):
    if not SOURCE.is_file(): raise SafetyError('watchdog_source_not_installed')
    timer = 'sc-vps-v11-revert-' + str(os.getpid()) + '.timer'
    unit = timer.removesuffix('.timer')
    rc, _, _ = base.run('systemd-run', '--quiet', '--unit=' + unit,
                         '--on-active=' + str(WATCHDOG_SECS) + 's',
                         '--timer-property=AccuracySec=1s', '/usr/bin/python3', str(SOURCE),
                         '--watchdog', str(path), timeout=20)
    if rc != 0: raise SafetyError('watchdog_setup_failed')
    rc, out, _ = base.run('systemctl', 'is-active', timer, timeout=10)
    if rc != 0 or out.strip() != 'active': raise SafetyError('watchdog_not_active')
    return timer


def stop_watchdog(timer):
    if not re.fullmatch(r'sc-vps-v11-revert-\d+\.timer', timer): return False
    rc, _, _ = base.run('systemctl', 'stop', timer, timeout=15)
    return rc == 0


def report(st, path, rc):
    save(path, st)
    print(f'SC VPS Rescue v{VERSION} | {st["status"]}')
    print('Decision:', st.get('reason'), '| return_code:', rc)
    print('Runtime-only browser high:', st.get('old_high'), '->', st.get('target_high'))
    print('Baseline:', st.get('baseline'))
    for i, w in enumerate(st.get('windows', []), 1):
        print('Post', i, w)
    print('Recorder / Gateway: no restart command issued; identity checked')
    print('Recording continuity and moderation function NOT proven by this tool')
    print('State:', path)
    return rc


def apply():
    base.require_root(); os.umask(0o077)
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(ROOT / 'lock', 'a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + str(os.getpid())
        folder = ROOT / 'runs' / run
        folder.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = folder / 'state.json'
        st = {'version': VERSION, 'utc': now(), 'status': 'diagnosis_only', 'reason': '',
              'changes': [], 'windows': [], 'browser_cgroup': None,
              'old_high': None, 'target_high': None}
        save(path, st)
        if not v10_refusal_ok():
            st['reason'] = 'v10_refusal_not_verified'; return report(st, path, 3)
        rec = v10.saved_v9()
        if not rec or rec.get('target_high') != BASELINE_HIGH or rec.get('old_high') != 450 * MiB:
            st['reason'] = 'v9_runtime_baseline_unrecognized'; return report(st, path, 3)
        p = v9.browser_group(); st['browser_cgroup'] = str(p)
        browser = get_service_identity(); containers = get_container_identities()
        new = BASELINE_HIGH + TARGET_INCREMENT
        st['old_high'] = BASELINE_HIGH; st['target_high'] = new
        if new > MAX_TARGET or not expected_limit(p, BASELINE_HIGH):
            st['reason'] = 'browser_high_not_at_verified_v9_baseline'; return report(st, path, 3)
        first = v9.inspect(p); time.sleep(WINDOW_SECS); second = v9.inspect(p)
        baseline = measure(first, second); st['baseline'] = baseline; save(path, st)
        failure = baseline_reason(baseline, second, BASELINE_HIGH)
        if not identities_ok(p, browser, containers): failure = 'service_identity_changed_before_trial'
        if not expected_limit(p, BASELINE_HIGH): failure = 'memory_high_changed_before_trial'
        if failure:
            st['reason'] = failure; return report(st, path, 3)
        timer = None; mutated = False
        try:
            st['status'] = 'trial_pending'; save(path, st)
            timer = start_watchdog(path); st['watchdog'] = timer; save(path, st)
            # Do not rely on a timer if it has already fired/been deactivated.
            rc, out, _ = base.run('systemctl', 'is-active', timer, timeout=10)
            if rc != 0 or out.strip() != 'active': raise SafetyError('watchdog_deactivated_pre_mutation')
            if not identities_ok(p, browser, containers): raise SafetyError('identity_changed_pre_mutation')
            set_high(p, BASELINE_HIGH, new)
            mutated = True; st['status'] = 'trial_applied'; st['changes'] = ['browser_MemoryHigh_runtime_trial']; save(path, st)
            a = v9.inspect(p)
            st['status'] = 'trial_running'; save(path, st)
            for _ in range(POST_WINDOWS):
                time.sleep(WINDOW_SECS)
                b = v9.inspect(p); w = measure(a, b)
                st['windows'].append(w); save(path, st)
                if not identities_ok(p, browser, containers) or not expected_limit(p, new):
                    raise SafetyError('service_identity_or_limit_changed_during_trial')
                if unsafe_post(w): raise SafetyError(unsafe_post(w))
                a = b
            if improved(baseline, st['windows']):
                if not identities_ok(p, browser, containers) or not expected_limit(p, new):
                    raise SafetyError('precommit_identity_or_limit_changed')
                # Durable success marker before disarming the independent timer.
                # If interrupted in between, timer will be a harmless no-op.
                st['status'] = 'runtime_verified'
                st['reason'] = 'pressure_high_events_and_faults_improved'
                st['changes'] = ['browser_MemoryHigh_runtime_610MiB']
                save(path, st)
                if not stop_watchdog(timer):
                    st['status'] = 'trial_running'
                    save(path, st)
                    raise SafetyError('watchdog_cancel_failed')
                st['watchdog_cancelled'] = True
                return report(st, path, 0)
            # No demonstrated benefit: restore promptly while watchdog stays armed.
            st['reason'] = 'insufficient_repeatable_memory_improvement'
            set_high(p, new, BASELINE_HIGH)
            mutated = False
            if not stop_watchdog(timer): raise SafetyError('watchdog_cancel_failed_after_restore')
            st['watchdog_cancelled'] = True
            st['status'] = 'diagnosis_only'; st['changes'] = []
            return report(st, path, 3)
        except (Exception, KeyboardInterrupt) as ex:
            st['reason'] = 'trial_error_' + type(ex).__name__ + ':' + str(ex)[:100]
            # Keep timer and source until its independent action is accounted for.
            if mutated:
                try:
                    if expected_limit(p, new):
                        set_high(p, new, BASELINE_HIGH)
                        mutated = False
                except Exception as rb:
                    st['rollback_error'] = type(rb).__name__ + ':' + str(rb)[:100]
            if not mutated and expected_limit(p, BASELINE_HIGH):
                if timer and stop_watchdog(timer):
                    st['watchdog_cancelled'] = True
                    st['status'] = 'diagnosis_only'; st['changes'] = []
                    return report(st, path, 3)
                if timer is None:
                    st['status'] = 'diagnosis_only'; st['changes'] = []
                    return report(st, path, 3)
            st['status'] = 'needs_review'
            return report(st, path, 2)


def status():
    base.require_root()
    p = v9.browser_group()
    print('SC VPS Rescue v11 read-only status')
    print('Browser memory.high:', v9.r(p / 'memory.high'))
    print('Browser memory.current:', v9.r(p / 'memory.current'))
    print('V10 safety refusal present:', v10_refusal_ok())
    runs = sorted((ROOT / 'runs').glob('*/state.json'), reverse=True)
    if runs:
        x = read_state(runs[0]); print('Last V11:', x.get('status'), x.get('reason'))
    print('Read-only check is not a recording continuity test')
    return 0


def rollback():
    base.require_root()
    runs = sorted((ROOT / 'runs').glob('*/state.json'), reverse=True)
    for path in runs:
        st = read_state(path)
        if st.get('version') != VERSION or st.get('status') != 'runtime_verified': continue
        p = v9.browser_group()
        if str(p) != st.get('browser_cgroup'): raise SafetyError('cgroup_changed_since_verified_trial')
        if not expected_limit(p, st['target_high']): raise SafetyError('memory_limit_changed_since_trial')
        set_high(p, st['target_high'], st['old_high'])
        st['status'] = 'manually_rolled_back'; st['reason'] = 'requested_rollback'; save(path, st)
        print('V11 runtime memory.high restored; no services restarted'); return 0
    print('No V11 verified runtime trial found'); return 3


def main():
    parser = argparse.ArgumentParser()
    x = parser.add_mutually_exclusive_group(required=True)
    x.add_argument('--apply', action='store_true')
    x.add_argument('--status', action='store_true')
    x.add_argument('--rollback', action='store_true')
    x.add_argument('--watchdog')
    args = parser.parse_args()
    if args.status: return status()
    if args.rollback: return rollback()
    if args.watchdog: return watchdog(Path(args.watchdog))
    return apply()


if __name__ == '__main__':
    try: sys.exit(main())
    except (SafetyError, v9.SafetyError, base.RescueError, OSError, ValueError,
            BlockingIOError) as ex:
        print('SC_VPS_V11_SAFE_ABORT:', type(ex).__name__, str(ex)[:150], file=sys.stderr)
        sys.exit(2)
