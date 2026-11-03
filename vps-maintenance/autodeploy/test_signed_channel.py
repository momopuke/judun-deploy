"""Offline verification of the published public channel, no private signing key."""
import hashlib
import json
from pathlib import Path
import re
import unittest
import pull_agent as agent

BASE = Path(__file__).resolve().parent

class SignedChannel(unittest.TestCase):
    def signed(self):
        return agent.verify((BASE/'channel.json').read_bytes(),
                            (BASE/'channel.sig.b64').read_bytes(),
                            BASE/'release-signing-public.pem')

    def test_signed_read_only_seq2_recovery(self):
        doc = self.signed()
        self.assertEqual(doc['sequence'], 2)
        self.assertEqual(doc['operation'], 'status')
        self.assertRegex(doc['git_commit'], r'^[a-f0-9]{40}$')
        self.assertEqual(doc['version'], 10)

    def test_all_signed_release_file_digests(self):
        doc = self.signed()
        payload = BASE/'releases'/doc['release_id']
        if not payload.is_dir():
            payload = BASE/'releases'/'v10'  # local isolated staging equivalent
        self.assertTrue(payload.is_dir())
        for relative, hexdigest in doc['files'].items():
            src = payload/relative
            self.assertTrue(src.is_file(), str(src))
            self.assertEqual(hashlib.sha256(src.read_bytes()).hexdigest(), hexdigest, relative)

    def test_reject_unsigned_manifest_change(self):
        raw = (BASE/'channel.json').read_bytes()
        self.assertIn(b'"operation": "status"', raw)
        mutated = raw.replace(b'"operation": "status"', b'"operation": "apply"')
        with self.assertRaises(agent.Rejected):
            agent.verify(mutated, (BASE/'channel.sig.b64').read_bytes(),
                         BASE/'release-signing-public.pem')

    def test_bootstrap_pins_reviewed_agent_and_timeout(self):
        s = (BASE/'bootstrap.sh').read_text()
        self.assertIn("COMMIT='53430996dd856643f3f68c5686afb8b1470114ae'", s)
        self.assertIn("AGENT_SHA256='9113ce881789bad728cb8015f4f94d3cb685a1245d4b6bec8f271ebae5ff7c89'", s)
        self.assertIn('TimeoutStartSec=900s', s)
        self.assertLess(s.index('systemctl start sc-vps-autodeploy.service'),
                        s.index('systemctl enable --now sc-vps-autodeploy.timer'))
        digest = hashlib.sha256((BASE/'pull_agent.py').read_bytes().rstrip(b'\n')).hexdigest()
        self.assertEqual(digest, '9113ce881789bad728cb8015f4f94d3cb685a1245d4b6bec8f271ebae5ff7c89')

if __name__ == '__main__': unittest.main()