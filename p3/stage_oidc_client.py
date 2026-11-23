"""Short-lived GitHub Actions OIDC client for private VPS staging health.

No ChatGPT Sites sign-in bypass token or stored GitHub Actions Secret.
Works only in a trusted GitHub Actions job with id-token: write.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlencode, urlsplit, parse_qsl, urlunsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from urllib.error import HTTPError, URLError

AUDIENCE = "judun-stage-health-v1"
GATEWAY = "https://judun-oidc.142-93-91-214.sslip.io"
PREFIX = "/__jd_stage_health/v1"
PATHS = frozenset(("/health/build", "/health/artifact?deep=true", "/health/ready"))


class Denied(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, url):
        return None


def fail(condition):
    if not condition:
        raise Denied("JUDUN_STAGE_OIDC_UNVERIFIED")


def open_client():
    return build_opener(NoRedirect())


def github_id_token(*, env=None, transport=None):
    env = env or os.environ
    origin = env.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    bootstrap = env.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    uri = urlsplit(origin)
    if not origin or not bootstrap:
        raise Denied("OIDC_RUNNER_BOOTSTRAP_MISSING")
    if not (uri.scheme == "https" and uri.hostname is not None
            and (uri.hostname == "actions.githubusercontent.com"
                 or uri.hostname.endswith(".actions.githubusercontent.com"))
            and uri.port in (None, 443) and not uri.username and not uri.password
            and uri.fragment == ""):
        raise Denied("OIDC_RUNNER_ORIGIN_REJECTED")
    if not isinstance(bootstrap, str) or len(bootstrap) > 4096:
        raise Denied("OIDC_RUNNER_BOOTSTRAP_SIZE_REJECTED")
    if not all(33 <= ord(c) <= 126 for c in bootstrap):
        raise Denied("OIDC_RUNNER_BOOTSTRAP_CHARACTERS_REJECTED")
    params = parse_qsl(uri.query, keep_blank_values=True, strict_parsing=True)
    fail(not any(k == "audience" for k, _ in params))
    token_url = urlunsplit((uri.scheme, uri.netloc, uri.path,
                            urlencode(params + [("audience", AUDIENCE)]), ""))
    req = Request(token_url, headers={"Authorization": "bearer " + bootstrap,
                                      "Cache-Control": "no-store"}, method="GET")
    with (transport or open_client()).open(req, timeout=8) as res:
        fail(res.status == 200 and res.geturl() == token_url)
        raw = res.read(15001)
    fail(0 < len(raw) <= 15000)
    obj = json.loads(raw)
    fail(isinstance(obj, dict) and isinstance(obj.get("value"), str)
         and 100 < len(obj["value"]) <= 12288
         and obj["value"].count(".") == 2)
    return obj["value"]


def fetch_health(path, token, *, transport=None):
    fail(path in PATHS and isinstance(token, str)
         and 100 < len(token) <= 12288
         and token.count(".") == 2 and "\n" not in token and "\r" not in token)
    url = GATEWAY + PREFIX + path
    req = Request(url, headers={"Authorization": "Bearer " + token,
                                "Accept": "application/json",
                                "Cache-Control": "no-store"},
                  method="GET")
    with (transport or open_client()).open(req, timeout=8) as res:
        fail(res.status == 200 and res.geturl() == url)
        raw = res.read(32769)
    fail(0 < len(raw) <= 32768)
    obj = json.loads(raw)
    fail(isinstance(obj, dict))
    return obj


def verify_candidate(target, *, transport=None, env=None):
    """Reuse original strict signed target identity & payment-mode checks."""
    import direct_deploy_publish as original
    identity = github_id_token(env=env, transport=transport)
    return original.verify_target_live(
        target,
        getter=lambda path: fetch_health(path, identity, transport=transport),
        payment_mode="test_unlock",
        attempts=1,
    )
