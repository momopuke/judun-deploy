"""Offline OIDC client fault injection; no GitHub or VPS network."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("stage_oidc_client",
                                              ROOT / "stage_oidc_client.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class Response:
    status = 200
    def __init__(self, url, payload):
        self.url, self.payload = url, payload
    def geturl(self):
        return self.url
    def read(self, count):
        return json.dumps(self.payload).encode()[:count]
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class Transport:
    def __init__(self):
        self.calls = []
    def open(self, req, timeout):
        self.calls.append(req)
        if req.full_url.startswith("https://pipelines.actions.githubusercontent.com/"):
            return Response(req.full_url, {"value": "a" * 100 + "." + "b" * 100 + "." + "c" * 100})
        if req.full_url.startswith(cli.GATEWAY + cli.PREFIX):
            return Response(req.full_url, {"status": "ok"})
        raise AssertionError("unexpected URL " + req.full_url)


ENV = {
    "ACTIONS_ID_TOKEN_REQUEST_URL": "https://pipelines.actions.githubusercontent.com/abcd/idtoken?api-version=2",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "github-oidc-request-synthetic",
}


class StageOidcClientTests(unittest.TestCase):
    def test_oidc_mint_custom_audience_without_leaking_bootstrap(self):
        transport = Transport()
        value = cli.github_id_token(env=ENV, transport=transport)
        self.assertEqual(value.count("."), 2)
        request = transport.calls[0]
        self.assertIn("audience=judun-stage-health-v1", request.full_url)
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("Authorization"),
                         "bearer github-oidc-request-synthetic")
        self.assertNotIn(ENV["ACTIONS_ID_TOKEN_REQUEST_TOKEN"], request.full_url)

    def test_bootstrap_accepts_larger_github_request_token_with_bound(self):
        for size in (4096, 4097, 8192, 16384):
            with self.subTest(size=size):
                transport = Transport()
                token = "a" * size
                cli.github_id_token(env={**ENV, "ACTIONS_ID_TOKEN_REQUEST_TOKEN": token},
                                    transport=transport)
                self.assertEqual(transport.calls[0].get_header("Authorization"), "bearer " + token)
        for token in ("a" * 16385, "a" * 4097 + "\r\n"):
            transport = Transport()
            with self.assertRaises(cli.Denied):
                cli.github_id_token(env={**ENV, "ACTIONS_ID_TOKEN_REQUEST_TOKEN": token},
                                    transport=transport)
            self.assertEqual(transport.calls, [])

    def test_no_untrusted_token_origin(self):
        for url in ("http://pipelines.actions.githubusercontent.com/oidc",
                    "https://example.net/oidc",
                    "https://pipelines.actions.githubusercontent.com.evil.net/oidc",
                    "https://owner:pass@pipelines.actions.githubusercontent.com/oidc"):
            with self.subTest(url=url), self.assertRaises(cli.Denied):
                cli.github_id_token(
                    env={**ENV, "ACTIONS_ID_TOKEN_REQUEST_URL": url},
                    transport=Transport())

    def test_dedicated_oidc_domain_never_production_host(self):
        self.assertEqual(cli.GATEWAY, "https://judun-oidc.142-93-91-214.sslip.io")
        self.assertNotEqual(cli.GATEWAY, "https://judun.142-93-91-214.sslip.io")

    def test_stage_health_exact_paths_only(self):
        transport = Transport()
        token = "a" * 100 + "." + "b" * 100 + "." + "c" * 100
        for path in cli.PATHS:
            self.assertEqual(cli.fetch_health(path, token, transport=transport), {"status": "ok"})
        for path in ("/admin", "/payment", "//bad.test", "/health/build?debug=1", "/"):
            with self.subTest(path=path), self.assertRaises(cli.Denied):
                cli.fetch_health(path, token, transport=transport)
        self.assertEqual(len(transport.calls), 3)
        self.assertTrue(all(x.get_method() == "GET" for x in transport.calls))

    def test_no_siwc_or_static_github_secret_used(self):
        client = (ROOT / "stage_oidc_client.py").read_text()
        self.assertNotIn("OAI-Sites-Authorization", client)
        self.assertNotIn("JUDUN_STAGE_AUTH_TOKEN", client)
        self.assertNotIn("GITHUB_TOKEN", client)

    def test_wrong_token_shape_blocked(self):
        for token in ("", "123", "a.b", "evil\r\nHeader:x"):
            with self.subTest(token=token), self.assertRaises(cli.Denied):
                cli.fetch_health("/health/ready", token, transport=Transport())


    def test_native_qa_missing_pending_and_valid(self):
        pending = cli.native_qa_summary({}, 98)
        self.assertEqual(pending["native_qa_status"], "PENDING")
        self.assertEqual(cli.native_qa_summary(pending, 98), pending)
        proof = {"native_qa_status": "PASS", "native_qa_receipt_sha256": "a"*64,
                 "native_qa_file_count": 98}
        self.assertEqual(cli.native_qa_summary({**proof, "secret": "not exported"}, 98), proof)

    def test_native_qa_malformed_receipts_denied(self):
        proof = {"native_qa_status": "PASS", "native_qa_receipt_sha256": "a"*64,
                 "native_qa_file_count": 98}
        for invalid in ({"native_qa_status": "PASS"},
                        {**proof, "native_qa_receipt_sha256": "A"*64},
                        {**proof, "native_qa_receipt_sha256": ""},
                        {**proof, "native_qa_file_count": 97},
                        {**proof, "native_qa_file_count": True},
                        {**proof, "native_qa_status": "FAIL"},
                        {**proof, "native_qa_status": "PENDING"}):
            with self.subTest(invalid=invalid), self.assertRaises(cli.Denied):
                cli.native_qa_summary(invalid, 98)

if __name__ == "__main__":
    unittest.main()
