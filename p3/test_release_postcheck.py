"""Offline fault-injection for strict signed dual-site release re-verification."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('release_postcheck', HERE / 'release_postcheck.py')
rp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rp)

TARGET = {'release_id': 'v1.2.190-singlepass-20261118'}
BASE = dict(artifact_id='art', build_instance_id='build', version='v1.2.190',
            source_tree_sha256='a'*64, managed_files=98)


def fake_live(target, attempts):
    assert attempts == 1
    return dict(BASE, payment_mode='ecpay_live')


def fake_stage(target, token, attempts):
    assert token == 'sensitive-not-to-log' and attempts == 1
    return dict(BASE, payment_mode='test_unlock')


class PostreleaseTest(unittest.TestCase):
    def good(self):
        return rp.collect(TARGET, 'sensitive-not-to-log', live=fake_live, stage=fake_stage)

    def sample(self, t):
        return {'schema': rp.SCHEMA, 'signed_manifest_sha256': 'b'*64,
                'release_id': TARGET['release_id'], 'checked_at_epoch': t,
                'sites': self.good()}

    def test_dual_signed_identity(self):
        self.assertEqual(self.good()['production']['managed_files'], 98)
        self.assertTrue(rp.validate_pair(self.sample(100), self.sample(160)))

    def test_token_missing_fails_closed(self):
        with self.assertRaisesRegex(rp.AttestationError, 'STAGING_AUTH_MISSING'):
            rp.collect(TARGET, '', live=fake_live, stage=fake_stage)

    def test_staging_drift_fails_closed(self):
        def broken(target, token, attempts):
            return dict(BASE, payment_mode='test_unlock', source_tree_sha256='c'*64)
        with self.assertRaisesRegex(rp.AttestationError, 'SITE_IDENTITY_MISMATCH'):
            rp.collect(TARGET, 'sensitive-not-to-log', live=fake_live, stage=broken)

    def test_payment_mode_fails_closed(self):
        def unsafe(target, token, attempts):
            return dict(BASE, payment_mode='ecpay_live')
        with self.assertRaisesRegex(rp.AttestationError, 'STAGING_PAYMENT_MODE'):
            rp.collect(TARGET, 'sensitive-not-to-log', live=fake_live, stage=unsafe)

    def test_early_second_check_refused(self):
        with self.assertRaisesRegex(rp.AttestationError, 'ONE_MINUTE_NOT_ELAPSED'):
            rp.validate_pair(self.sample(100), self.sample(159.9))

    def test_release_change_refused(self):
        second = self.sample(161)
        second['release_id'] = 'v1.2.191-a'
        with self.assertRaisesRegex(rp.AttestationError, 'ONE_MINUTE_DRIFT'):
            rp.validate_pair(self.sample(100), second)

    def test_staging_change_after_minute_refused(self):
        second = self.sample(161)
        second['sites']['staging']['source_tree_sha256'] = 'd'*64
        with self.assertRaisesRegex(rp.AttestationError, 'ONE_MINUTE_DRIFT'):
            rp.validate_pair(self.sample(100), second)

    def test_secure_receipt_and_duplicate_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'evidence.json'
            rp.write_receipt(p, self.sample(100))
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(rp.read_receipt(p)['release_id'], TARGET['release_id'])
            with self.assertRaises(FileExistsError):
                rp.write_receipt(p, self.sample(100))
            p.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaisesRegex(rp.AttestationError, 'RECEIPT_DUPLICATE_KEY'):
                rp.read_receipt(p)

    def test_link_and_world_readable_receipt_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'evidence.json'
            rp.write_receipt(p, self.sample(100))
            p.chmod(0o644)
            with self.assertRaisesRegex(rp.AttestationError, 'RECEIPT_FILE_UNTRUSTED'):
                rp.read_receipt(p)
            alias = Path(d) / 'link'
            alias.symlink_to(p)
            with self.assertRaisesRegex(rp.AttestationError, 'RECEIPT_FILE_UNTRUSTED'):
                rp.read_receipt(alias)

    def test_unexpected_prod_change_during_read_refused(self):
        counter = [0]
        def changing(target, attempts):
            counter[0] += 1
            return dict(BASE, payment_mode='ecpay_live',
                        artifact_id='a' if counter[0] == 1 else 'b')
        with self.assertRaisesRegex(rp.AttestationError, 'PRODUCTION_CHANGED_DURING_CHECK'):
            rp.collect(TARGET, 'sensitive-not-to-log', live=changing, stage=fake_stage)

    def test_time_travel_and_oversize_gap_blocked(self):
        for t in (99, 3701):
            with self.assertRaisesRegex(rp.AttestationError, 'RECEIPT_TIME_OUT_OF_RANGE'):
                rp.validate_pair(self.sample(100), self.sample(t))


    def test_final_evidence_requires_60_seconds_and_two_matching_receipts(self):
        initial = self.sample(100)
        minute = self.sample(167)
        final = rp.final_evidence(initial, minute)
        self.assertEqual(final['result'], 'PASS')
        self.assertEqual(final['observed_seconds'], 67)
        self.assertEqual(final['release_id'], TARGET['release_id'])
        self.assertEqual(final['signed_manifest_sha256'], 'b' * 64)
        self.assertEqual(final['first'], initial)
        self.assertEqual(final['minute'], minute)
        with self.assertRaisesRegex(rp.AttestationError, 'ONE_MINUTE_NOT_ELAPSED'):
            rp.final_evidence(initial, self.sample(155))

    def test_final_evidence_does_not_accept_replaced_release(self):
        old = self.sample(100)
        new = self.sample(169)
        new['signed_manifest_sha256'] = 'c' * 64
        with self.assertRaisesRegex(rp.AttestationError, 'ONE_MINUTE_DRIFT'):
            rp.final_evidence(old, new)

    def test_final_evidence_survives_durable_round_trip_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            final_path = Path(d) / 'only-after-one-minute.json'
            bundle = rp.final_evidence(self.sample(100), self.sample(165))
            rp.write_receipt(final_path, bundle)
            self.assertEqual(rp.read_receipt(final_path), bundle)
            self.assertEqual(final_path.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                rp.write_receipt(final_path, bundle)

    def test_receipt_rejects_signed_channel_changing_during_collection(self):
        calls = [0]
        def sha():
            calls[0] += 1
            return 'a' * 64 if calls[0] == 1 else 'b' * 64
        from unittest.mock import patch
        with patch.object(rp, 'stable_hash', side_effect=sha):
            with self.assertRaisesRegex(rp.AttestationError,
                                        'CHANNEL_CHANGED_DURING_READ'):
                rp.receipt(TARGET, 'stage-token',
                           verifier=lambda: TARGET,
                           collector=lambda target, token: self.good(),
                           now=100)



if __name__ == '__main__':
    unittest.main()
