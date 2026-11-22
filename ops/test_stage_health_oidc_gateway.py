"""No network or real credentials; disposable RSA OIDC and local health fixtures."""
import base64
import importlib.util
import json
from pathlib import Path
import time
import unittest
from unittest import mock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stage_gateway", ROOT / "stage_health_oidc_gateway.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def enc(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class GatewayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = cls.key.public_key().public_numbers()
        cls.jwks = [{
            "kid": "synthetic-rsa-1", "kty": "RSA", "use": "sig", "alg": "RS256",
            "n": enc(numbers.n.to_bytes(256, "big")),
            "e": enc(numbers.e.to_bytes(3, "big")),
        }]

    def issue(self, **update):
        now = 1700000100
        payload = {
            "iss": gate.ISS, "aud": gate.AUD,
            "repository": gate.REPO, "repository_id": gate.REPO_ID,
            "repository_owner_id": gate.OWNER_ID,
            "ref": gate.BRANCH,
            "workflow_ref": gate.REPO + "/.github/workflows/verify-v1286-live.yml@" + gate.BRANCH,
            "event_name": "push", "sha": "a" * 40,
            "run_id": "45035964370", "run_attempt": "1",
            "iat": now - 60, "exp": now + 240,
        }
        payload.update(update)
        head = enc(json.dumps({"alg": "RS256", "kid": "synthetic-rsa-1"}).encode())
        body = enc(json.dumps(payload).encode())
        signing = (head + "." + body).encode("ascii")
        signature = self.key.sign(signing, padding.PKCS1v15(), hashes.SHA256())
        return (signing + b"." + enc(signature).encode()).decode()

    def test_valid_signed_push_token(self):
        self.assertTrue(gate.check_token(self.issue(), self.jwks, now=1700000100))

    def test_valid_signed_pr_target_token(self):
        pr = gate.REPO + "/.github/workflows/release-pr-gate.yml@" + gate.BRANCH
        self.assertTrue(gate.check_token(
            self.issue(workflow_ref=pr, event_name="pull_request_target"),
            self.jwks, now=1700000100))

    def test_expired_wrong_repo_wrong_workflow_and_audience_rejected(self):
        bad = [
            {"exp": 1700000099}, {"aud": "another-service"},
            {"repository_id": "111"}, {"repository_owner_id": "222"},
            {"repository": "stranger/repo"}, {"ref": "refs/heads/testing"},
            {"workflow_ref": "stranger/repo/.github/workflows/attack.yml@refs/heads/main"},
            {"event_name": "pull_request"}, {"sha": "invalid"},
            {"run_id": "0"}, {"iat": 1700001000},
        ]
        for wrong in bad:
            with self.subTest(wrong=wrong), self.assertRaises(gate.Blocked):
                gate.check_token(self.issue(**wrong), self.jwks, now=1700000100)

    def test_wrong_key_or_corrupt_signature_rejected(self):
        wrong = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nums = wrong.public_key().public_numbers()
        others = [{"kid": "synthetic-rsa-1", "kty": "RSA", "use": "sig",
                   "n": enc(nums.n.to_bytes(256, "big")),
                   "e": enc(nums.e.to_bytes(3, "big"))}]
        with self.assertRaises(gate.Blocked):
            gate.check_token(self.issue(), others, now=1700000100)
        corrupt = self.issue()[:-1] + ("A" if self.issue()[-1] != "A" else "B")
        with self.assertRaises(gate.Blocked):
            gate.check_token(corrupt, self.jwks, now=1700000100)

    def test_only_three_paths_and_no_production(self):
        self.assertEqual(len(gate.PATHS), 3)
        for path in ("/", "/admin", "/payment", "//example.test",
                     "/health/artifact?deep=false", "/health/build?extra=1"):
            with self.subTest(path=path), self.assertRaises(gate.Blocked):
                gate.health_get(path)
        self.assertEqual(gate.STAGE, "http://127.0.0.1:8011")

    def test_sanitized_upstream_no_personal_fields(self):
        class Response:
            status = 200
            def __init__(self, url):
                self.url = url
            def geturl(self):
                return self.url
            def read(self, n):
                data = {k: (98 if k == "files_verified" else
                            98 if k == "manifest_file_count" else
                            0 if k == "mismatch_count" else
                            True if k == "deep_verified" else "ok")
                        for k in gate.PATHS["/health/artifact?deep=true"]}
                data["customer_email"] = "never@print.invalid"
                data["gateway_secret"] = "not-for-ci"
                return json.dumps(data).encode()
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        class Getter:
            def open(self, request, timeout):
                self.url = request.full_url
                self.method = request.get_method()
                return Response(request.full_url)
        getter = Getter()
        result = gate.health_get("/health/artifact?deep=true", getter=getter)
        self.assertNotIn("customer_email", result)
        self.assertNotIn("gateway_secret", result)
        self.assertEqual(result["files_verified"], 98)
        self.assertEqual(getter.method, "GET")
        self.assertEqual(getter.url, gate.STAGE + "/health/artifact?deep=true")

    def test_duplicate_json_is_rejected(self):
        with self.assertRaises(gate.Blocked):
            gate.json_bytes(b'{"iss":"valid","iss":"spoof"}')

    def test_not_public_bind(self):
        with self.assertRaises(gate.Blocked):
            gate.Gateway(("0.0.0.0", 18762))

    def test_invalid_raw_jwt(self):
        for value in ("", "wrong", "a.b.c.d", " " * 20):
            with self.subTest(token=value), self.assertRaises(gate.Blocked):
                gate.check_token(value, self.jwks, now=1700000100)


if __name__ == "__main__":
    unittest.main()
