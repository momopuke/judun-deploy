#!/usr/bin/env python3
"""Loopback-only GitHub OIDC verifier exposing three sanitized staging health GETs.

Not a deployment agent, SIWC bypass, signing service, or public TLS listener.
Requires an authorized HTTPS reverse proxy for the exact URL prefix.
"""
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import time
from urllib.request import Request, HTTPRedirectHandler, ProxyHandler, build_opener
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ISS = "https://token.actions.githubusercontent.com"
JWKS = ISS + "/.well-known/jwks"
AUD = "judun-stage-health-v1"
REPO = "momopuke/judun-deploy"
REPO_ID = "1404145305"
OWNER_ID = "126347129"
BRANCH = "refs/heads/main"
ALLOWED = {
    REPO + "/.github/workflows/verify-v1286-live.yml@" + BRANCH:
        {"push", "workflow_dispatch"},
    REPO + "/.github/workflows/release-pr-gate.yml@" + BRANCH:
        {"pull_request_target"},
}
PREFIX = "/__jd_stage_health/v1"
STAGE = "http://127.0.0.1:8011"
PATHS = {
    "/health/build": (
        "status", "manifest_status", "artifact_id", "build_instance_id",
        "display_version", "version", "source_tree_sha256", "payment_mode"),
    "/health/artifact?deep=true": (
        "status", "artifact_id", "build_instance_id", "version",
        "source_tree_sha256", "files_verified", "manifest_file_count",
        "mismatch_count", "deep_verified"),
    "/health/ready": ("status", "version"),
}
ROUTES = {PREFIX + p: p for p in PATHS}


class Blocked(ValueError):
    pass


def guard(ok):
    if not ok:
        raise Blocked("OIDC_HEALTH_DENIED")


def unique(pairs):
    obj = {}
    for key, value in pairs:
        guard(key not in obj)
        obj[key] = value
    return obj


def json_bytes(data):
    guard(isinstance(data, bytes) and 0 < len(data) <= 65536)
    return json.loads(data, object_pairs_hook=unique)


def unbase64(data):
    guard(isinstance(data, str) and 0 < len(data) <= 12000
          and re.fullmatch("[A-Za-z0-9_-]+", data) is not None)
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, url):
        return None


def opener():
    return build_opener(ProxyHandler({}), NoRedirect())


def fetch_jwks():
    req = Request(JWKS, headers={"Cache-Control": "no-cache"})
    with opener().open(req, timeout=4) as res:
        guard(res.status == 200 and res.geturl() == JWKS)
        raw = res.read(65537)
    guard(len(raw) <= 65536)
    data = json_bytes(raw)
    guard(isinstance(data, dict) and isinstance(data.get("keys"), list)
          and 0 < len(data["keys"]) <= 20)
    return data["keys"]


def check_token(token, keys, now=None):
    guard(isinstance(token, str) and len(token) <= 12288)
    parts = token.split(".")
    guard(len(parts) == 3)
    hdr, claims = json_bytes(unbase64(parts[0])), json_bytes(unbase64(parts[1]))
    guard(isinstance(hdr, dict) and hdr.get("alg") == "RS256"
          and isinstance(hdr.get("kid"), str))
    guard(isinstance(claims, dict) and isinstance(keys, list))
    matches = [k for k in keys if isinstance(k, dict)
               and k.get("kid") == hdr["kid"] and k.get("kty") == "RSA"
               and k.get("use", "sig") == "sig" and k.get("alg", "RS256") == "RS256"]
    guard(len(matches) == 1)
    key = matches[0]
    n = int.from_bytes(unbase64(key["n"]), "big")
    e = int.from_bytes(unbase64(key["e"]), "big")
    guard(2048 <= n.bit_length() <= 8192 and e in (3, 65537))
    try:
        rsa.RSAPublicNumbers(e, n).public_key().verify(
            unbase64(parts[2]), (parts[0] + "." + parts[1]).encode("ascii"),
            padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, ValueError, TypeError) as error:
        raise Blocked("OIDC_HEALTH_DENIED") from error
    now = time.time() if now is None else now
    iat, exp = claims.get("iat"), claims.get("exp")
    guard(type(iat) is int and type(exp) is int
          and now - 600 <= iat <= now + 30 and now < exp <= now + 900
          and 0 < exp - iat <= 900)
    if "nbf" in claims:
        guard(type(claims["nbf"]) is int and claims["nbf"] <= now + 30)
    guard(claims.get("iss") == ISS and claims.get("aud") == AUD)
    guard(claims.get("repository") == REPO
          and str(claims.get("repository_id")) == REPO_ID
          and str(claims.get("repository_owner_id")) == OWNER_ID)
    guard(claims.get("ref") == BRANCH)
    workflow = claims.get("workflow_ref")
    guard(isinstance(workflow, str) and workflow in ALLOWED
          and claims.get("event_name") in ALLOWED[workflow])
    guard(isinstance(claims.get("sha"), str)
          and re.fullmatch("[a-f0-9]{40}", claims["sha"]) is not None)
    guard(re.fullmatch("[1-9][0-9]{0,19}", str(claims.get("run_id"))) is not None)
    guard(re.fullmatch("[1-9][0-9]{0,5}", str(claims.get("run_attempt"))) is not None)
    return True


def health_get(path, getter=None):
    guard(path in PATHS)
    url = STAGE + path
    req = Request(url, headers={"Cache-Control": "no-store"}, method="GET")
    with (getter or opener()).open(req, timeout=3) as res:
        guard(res.status == 200 and res.geturl() == url)
        raw = res.read(32769)
    guard(0 < len(raw) <= 32768)
    obj = json_bytes(raw)
    guard(isinstance(obj, dict) and all(k in obj for k in PATHS[path]))
    result = {key: obj[key] for key in PATHS[path]}
    guard(all(type(v) in (str, int, bool) and
              (type(v) is not str or len(v) <= 256) for v in result.values()))
    return result


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Never log Authorization, JWTs or request line.

    def do_GET(self):
        try:
            guard(self.path in ROUTES)
            auth = self.headers.get("Authorization", "")
            guard(auth.startswith("Bearer ") and 7 < len(auth) <= 12300)
            if self.server.keys is None or time.monotonic() >= self.server.until:
                self.server.keys = fetch_jwks()
                self.server.until = time.monotonic() + 300
            check_token(auth[7:], self.server.keys)
            body = json.dumps(health_get(ROUTES[self.path]),
                              separators=(",", ":"), sort_keys=True).encode()
        except (Blocked, ValueError, TypeError, KeyError, OSError, OverflowError):
            self.send_response(403)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


class Gateway(HTTPServer):
    def __init__(self, bind=("127.0.0.1", 18762)):
        guard(bind[0] == "127.0.0.1")
        super().__init__(bind, Handler)
        self.keys, self.until = None, 0.0


if __name__ == "__main__":
    with Gateway() as server:
        print("JUDUN_STAGE_HEALTH_OIDC_LOOPBACK_READY", flush=True)
        server.serve_forever(poll_interval=0.5)
