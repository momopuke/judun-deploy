"""Offline tests for sanitized, duplicate-resistant release failure logging."""
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('release_failure_report',
                                              HERE / 'release_failure_report.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SHA = 'a' * 40
RUN = '45000000000'
RESULTS = dict(original_signed_production='success',
               release_change_classification='success',
               offline_guard='success',
               dual_site_minute_recheck='failure')


class FailureReportTest(unittest.TestCase):
    def test_build_sanitized_failure(self):
        marker, body = module.build_failure(RUN, '1', SHA, RESULTS)
        self.assertIn('45000000000', body)
        self.assertIn(marker, body)
        self.assertIn('BLOCKED', body)
        self.assertNotIn('JUDUN_STAGE_AUTH_TOKEN', body)
        self.assertNotIn('GITHUB_TOKEN', body)

    def test_success_or_skip_means_no_failure(self):
        self.assertIsNone(module.build_failure(
            RUN, '1', SHA, dict(RESULTS, dual_site_minute_recheck='skipped')))
        self.assertIsNone(module.build_failure(
            RUN, '1', SHA, dict(RESULTS, dual_site_minute_recheck='success')))

    def test_status_or_run_injection_fails(self):
        bad = [
            ('badid', '1', SHA, RESULTS),
            (RUN, '1;evil', SHA, RESULTS),
            (RUN, '1', 'a' * 39, RESULTS),
            (RUN, '1', SHA, dict(RESULTS, dual_site_minute_recheck='token-value')),
        ]
        for args in bad:
            with self.subTest(args=args[:3]), self.assertRaises(module.ReportError):
                module.build_failure(*args)

    def test_idempotent_retry_uses_bot_identity(self):
        marker, body = module.build_failure(RUN, '1', SHA, RESULTS)
        calls = []
        def request(method, endpoint, token, data=None):
            calls.append((method, endpoint))
            if endpoint == '/issues/22':
                return {'comments': 183}
            if method == 'GET':
                return [{'body': '<!-- ' + marker + ' -->',
                         'user': {'login': 'github-actions[bot]'}}]
            raise AssertionError('unexpected post')
        self.assertEqual(
            module.submit_failure(RUN, '1', SHA, RESULTS, 'not-a-secret-12345',
                                  request=request),
            'ALREADY_RECORDED')
        self.assertEqual(len(calls), 2)

    def test_spoofed_public_comment_does_not_suppress_receipt(self):
        marker, _ = module.build_failure(RUN, '1', SHA, RESULTS)
        posts = []
        def request(method, endpoint, token, data=None):
            if endpoint == '/issues/22':
                return {'comments': 182}
            if method == 'GET':
                return [{'body': marker, 'user': {'login': 'spoof-account'}}]
            posts.append(data)
            return {'id': 1}
        result = module.submit_failure(RUN, '1', SHA, RESULTS,
                                       'not-a-secret-12345', request=request)
        self.assertEqual(result, 'CREATED')
        self.assertEqual(len(posts), 1)
        self.assertIn('BLOCKED', posts[0]['body'])

    def test_missing_comment_count_fails_closed(self):
        def request(method, endpoint, token, data=None):
            return {'comments': 'not-integer'}
        with self.assertRaisesRegex(module.ReportError, 'COMMENT_COUNT_UNKNOWN'):
            module.submit_failure(RUN, '1', SHA, RESULTS,
                                  'not-a-secret-12345', request=request)

    def test_other_issue_endpoint_disallowed(self):
        with self.assertRaisesRegex(module.ReportError, 'OUT_OF_SCOPE_ENDPOINT'):
            module.api_call('POST', '/issues/32/comments', 'not-a-secret-12345',
                            {'body': 'example'})

    def test_canceled_is_failure_but_skipped_is_not(self):
        r = dict(RESULTS, dual_site_minute_recheck='cancelled')
        self.assertIn('cancelled', module.build_failure(RUN, '2', SHA, r)[1])


if __name__ == '__main__':
    unittest.main()
