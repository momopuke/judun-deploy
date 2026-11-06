import datetime
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import SC_VPS_Rescue_v19 as diag


class CpuDiagnosisTests(unittest.TestCase):
    def test_process_stat_handles_closing_parentheses_and_spaces(self):
        fields = ['0'] * 20
        fields[0], fields[11], fields[12], fields[19] = 'R', '22', '15', '123'
        row = '42 (odd ) name) ' + ' '.join(fields)
        self.assertEqual(diag.process_stat(row), ((42, 123), 'odd___name', 37))

    def test_process_aggregation_drops_reused_pid(self):
        before = {(1, 8): ('ffmpeg', 1), (2, 9): ('ffmpeg', 1), (3, 10): ('old', 1)}
        after = {(1, 8): ('ffmpeg', 1 + diag.TICKS),
                 (2, 9): ('ffmpeg', 1 + diag.TICKS), (3, 11): ('new', 1000)}
        self.assertEqual(diag.top_processes(before, after, 5), [['ffmpeg', 40.0]])

    def test_docker_scope_resolves_at_container_root(self):
        identity = 'a' * 64
        for base in ('/system.slice/docker-' + identity + '.scope', '/docker/' + identity):
            result = diag.container_path('0::' + base + '/worker')
            self.assertEqual(result, (identity, pathlib.Path('/sys/fs/cgroup' + base)))
        self.assertIsNone(diag.container_path('0::/../docker/' + identity))

    def test_cpu_io_steal_and_cgroup_accounting(self):
        before = (100, 1000, [0] * 8, {}, {'a': 2500000, 'gone': 20})
        after = (105, 1005, [400, 0, 50, 10, 10, 0, 0, 30], {},
                 {'a': 5000000, 'new': 1000000})
        result = diag.interval(before, after)
        self.assertEqual((result['cpu'], result['io'], result['steal']), (90.0, 2.0, 6.0))
        self.assertEqual(result['c'], [('a', 50.0)])

    def test_window_and_cron_syntax(self):
        local = datetime.datetime(2026, 11, 8, 3, 21, tzinfo=diag.TZ)
        start, end = diag.window(local.timestamp())
        self.assertEqual(datetime.datetime.fromtimestamp(start, diag.TZ).strftime('%H:%M'), '03:20')
        self.assertEqual(end - start, 1800)
        cron = diag.CRON_TEXT.decode().splitlines()[1]
        self.assertEqual(cron.split(maxsplit=6)[:6], ['*/5', '*', '*', '*', '*', 'root'])
        command = cron.split(maxsplit=6)[6]
        self.assertNotIn('%', command.replace(r'\%', ''))
        subprocess.run(['/bin/sh', '-n', '-c', command.replace(r'\%', '%')], check=True)

    def test_log_correlation_uses_timestamp_and_does_not_return_raw_text(self):
        epoch = datetime.datetime(2026, 11, 8, 3, 35, tzinfo=diag.TZ).timestamp()
        rows = ['2026-11-08 03:34:30 MERGE video', '2026-11-08 03:35:14 UPLOAD video',
                '2026-11-08 03:36:10 RCLONE video', 'UPLOAD unrelated']
        self.assertEqual(diag.log_activity(rows, epoch, diag.TZ), [1, 1, 0])

    def test_install_only_changes_owned_cron_and_rolls_back_on_delivery_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / 'test.py'
            source.touch()
            cron = root / 'cron'
            state = root / 'state'
            with patch.multiple(diag, CRON=cron, ROOT=state, SOURCE=source), \
                    patch.object(diag.os, 'geteuid', return_value=0), \
                    patch.object(diag.telemetry, 'cmd', return_value='active'), \
                    patch.object(diag, 'deliver', side_effect=diag.telemetry.Refused('relay')):
                with self.assertRaises(diag.telemetry.Refused):
                    diag.install()
                self.assertFalse(cron.exists())
                cron.write_text('foreign')
                with self.assertRaisesRegex(diag.telemetry.Refused, 'foreign_cron'):
                    diag.install()
                self.assertEqual(cron.read_text(), 'foreign')

    def test_summary_distinguishes_one_sample_from_spike_count(self):
        rows = [{'ts': 10, 'cpu': 98, 'io': 0, 'steal': 0, 'sec': 5,
                 'p': [['ffmpeg', 90]], 'c': [('a' * 64, 91)]},
                {'ts': 15, 'cpu': 5, 'io': 0, 'steal': 0, 'sec': 5, 'p': [], 'c': []}]
        with patch.object(diag, 'upload_activity', return_value={'taipei': [1, 0, 0]}):
            result = diag.summarize(rows, 5, 1805, {'a' * 64: 'recorder'})
        self.assertEqual((result['n'], result['high'], result['peak'][4]), (2, 1, [['recorder', 91]]))
        with patch.object(diag.telemetry, 'PUBLIC_KEY', diag.PUBLIC_KEY):
            self.assertEqual(len(diag.telemetry.encrypt(result)), 684)


if __name__ == '__main__':
    unittest.main()
