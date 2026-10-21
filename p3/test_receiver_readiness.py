"""Offline contract tests for read-only P3 receiver probe."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from receiver_readiness import RECEIVER, classify, assess, MAX_BYTES


class Response:
    def __init__(self, data=b"ok", code=200, url=RECEIVER + "/health"):
        self.status = code
        self.data = data
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.data[:size]

    def geturl(self):
        return self.url


class Opener:
    def __init__(self, response):
        self.response = response
        self.methods = []
        self.urls = []

    def open(self, req, timeout):
        self.methods.append(req.get_method())
        self.urls.append(req.full_url)
        assert 0 < timeout <= 12
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ReceiverProbeTests(unittest.TestCase):
    def test_only_exact_get_endpoints(self):
        for endpoint in ("/health", "/version"):
            opener = Opener(Response(url=RECEIVER + endpoint))
            self.assertEqual(classify(endpoint, opener)["state"], "HTTP_200")
            self.assertEqual(opener.methods, ["GET"])
            self.assertEqual(opener.urls, [RECEIVER + endpoint])
        with self.assertRaisesRegex(ValueError, "READ_ONLY_ENDPOINT_NOT_ALLOWED"):
            classify("/deploy", Opener(Response()))

    def test_hides_raw_receiver_response_and_rejects_redirect(self):
        secret = b"Never allow bearer token or server details into output"
        opener = Opener(Response(data=secret))
        self.assertNotIn("token", str(classify("/health", opener)).lower())
        response = classify("/health", Opener(Response(url="https://elsewhere.example/")))
        self.assertEqual(response["state"], "UNEXPECTED_DESTINATION")

    def test_http_failures_are_diagnostic_not_proof(self):
        for code, expected in [
            (302, "REDIRECT_NOT_FOLLOWED"),
            (401, "AUTH_REQUIRED"),
            (404, "NOT_FOUND"),
            (502, "UPSTREAM_UNAVAILABLE"),
        ]:
            error = HTTPError(RECEIVER + "/health", code, "ignored", {}, None)
            with self.subTest(code=code):
                self.assertEqual(classify("/health", Opener(error))["state"], expected)
        self.assertEqual(
            classify("/health", Opener(URLError("private details")))["state"],
            "TRANSPORT_NOT_VERIFIED",
        )
        self.assertEqual(
            classify("/health", Opener(Response(data=b"!" * (MAX_BYTES + 1))))["state"],
            "OVERSIZED_PUBLIC_RESPONSE",
        )

    def test_receiver_readiness_never_proves_agent_ready(self):
        self.assertEqual(
            assess({"/health": {"state": "HTTP_200"},
                    "/version": {"state": "HTTP_200", "receiver_v3_exact": True}}),
            "V3_RECEIVER_RESPONDS_AGENT_UNKNOWN",
        )
        self.assertEqual(
            assess({"/health": {"state": "HTTP_200"}, "/version": {"state": "HTTP_200"}}),
            "PUBLIC_RECEIVER_RESPONDS_PROTOCOL_UNVERIFIED",
        )
        probe = classify("/version", Opener(Response(data=b"v3", url=RECEIVER + "/version")))
        self.assertTrue(probe["receiver_v3_exact"])
        self.assertEqual(
            assess({"/health": {"state": "HTTP_200"}, "/version": {"state": "NOT_FOUND"}}),
            "RECEIVER_PARTIALLY_REACHABLE",
        )
        self.assertEqual(assess({}), "RECEIVER_NOT_PUBLICLY_VERIFIED")


if __name__ == "__main__":
    unittest.main()
