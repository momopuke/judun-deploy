"""Offline, no-network tests for automation bridge's fail-closed behavior."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import automation_bridge as bridge

class Response:
    status = 200
    def __init__(self, raw, url=bridge.REQUEST):
        self.raw, self.url = raw, url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, n): return self.raw[:n]
    def geturl(self): return self.url

class Opener:
    def __init__(self, response): self.response = response
    def open(self, request, timeout):
        assert request.full_url == bridge.REQUEST and timeout == 8
        assert request.get_header('Oai-sites-authorization').startswith('Bearer ')
        return self.response

class BridgeTest(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.token = self.root / 'token'
        self.token.write_text('credential-not-real-1234')
        self.token.chmod(0o600)

    def as_root(self, path):
        info = path.lstat()
        return patch.object(Path, 'lstat', return_value=SimpleNamespace(
            st_uid=0, st_mode=info.st_mode, st_size=info.st_size))

    def test_private_token_permissions_rejected(self):
        self.token.chmod(0o644)
        self.assertFalse(bridge.regular_root_file(self.token, secret=True))

    def test_symlink_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.token)
        self.assertFalse(bridge.regular_root_file(alias, secret=True))

    def test_zero_byte_stage_marker_is_valid(self):
        marker = self.root / 'isolated.enabled'
        marker.touch()
        marker.chmod(0o644)
        with self.as_root(marker):
            self.assertTrue(bridge.root_marker(marker))

    def test_pinned_public_key_rejects_drift(self):
        self.assertFalse(bridge.regular_root_file(self.token, pin='0'*64))

    def test_authenticated_request_valid_null(self):
        r = Opener(Response(b'{"candidate_commit":null}'))
        with self.as_root(self.token):
            self.assertTrue(bridge.request_auth_ok(self.token, r))

    def test_authenticated_request_rejects_duplicate_and_redirect(self):
        for raw in (b'{"candidate_commit":null,"candidate_commit":null}',
                    b'{"candidate_commit":"abc"}', b'{}'):
            self.assertFalse(bridge.request_auth_ok(self.token, Opener(Response(raw))))
        self.assertFalse(bridge.request_auth_ok(self.token, Opener(Response(
            b'{"candidate_commit":null}', 'https://elsewhere.invalid'))))

    def test_bridge_does_not_claim_signer_or_release_pass(self):
        r = bridge.check(self.root, self.root, lambda *args: True,
                         lambda *args: True)
        self.assertEqual(r['bridge'], 'BLOCKED')
        self.assertEqual(r['full_release_gate0'], 'NOT_VERIFIED')
        self.assertIn('private_signer_real_self_test', r['not_proven'])

    def test_checks_are_sanitized(self):
        r = bridge.check(self.root, self.root, lambda *args: False,
                         lambda *args: False)
        self.assertNotIn('credential-not-real', json.dumps(r))
        self.assertTrue(all(v == 'FAIL' for v in r['checks'].values()))

if __name__ == '__main__':
    unittest.main()
