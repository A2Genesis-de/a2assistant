"""#94558 — a non-JWT bearer must not be reported as "Auth provider unreachable".

Only a transport failure fetching the JWKS is "unreachable"; anything else (an opaque peer key, a
token that is not a JWT at all, a ``kid`` the reachable JWKS does not hold) means "not my token"
(``verify_session`` -> None -> 401 / next provider). Real ``SelfHostedOIDCProvider`` JWKS path
against a real local HTTP JWKS server.
"""
from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import jwt
import pytest

from hermes_cli.dashboard_auth import (
    InvalidCodeError,
    ProviderError,
    classify_jwks_lookup_error,
)

OPAQUE_PEER_KEY = "hk_live_opaque_peer_key_0123456789abcdef"



@contextmanager
def _serve_jwks(keys: list[dict]):
    """A reachable JWKS endpoint on loopback publishing ``keys``; yields its base URL."""

    class _H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"keys": keys}).encode())

        def log_message(self, *a):  # silence
            pass

    srv = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.fixture(scope="module")
def empty_jwks_server():
    """A reachable JWKS endpoint that knows no keys."""
    with _serve_jwks([]) as url:
        yield url


# ── classifier ────────────────────────────────────────────────────────────

def test_classifier_maps_transport_failure_to_provider_error():
    exc = jwt.PyJWKClientConnectionError("Fail to fetch data from the url")
    assert isinstance(classify_jwks_lookup_error(exc), ProviderError)


@pytest.mark.parametrize(
    "exc",
    [
        jwt.DecodeError("Not enough segments"),
        jwt.PyJWKSetError("The JWK Set did not contain any keys"),
        jwt.InvalidTokenError("bad"),
    ],
)
def test_classifier_maps_unverifiable_token_to_invalid_code(exc):
    assert isinstance(classify_jwks_lookup_error(exc), InvalidCodeError)


def test_classifier_keeps_bare_jwk_client_error_as_provider_fault():
    assert isinstance(classify_jwks_lookup_error(jwt.PyJWKClientError("weird JWKS shape")), ProviderError)


# ── self-hosted OIDC provider (sibling site of the same hunk) ──────────────

def test_self_hosted_provider_shares_the_classification(empty_jwks_server, monkeypatch):
    import plugins.dashboard_auth.self_hosted as sh

    provider = object.__new__(sh.SelfHostedOIDCProvider)
    provider._jwks_client = None
    provider._client_id = "hermes"
    monkeypatch.setattr(
        provider, "_get_discovery",
        lambda: {"jwks_uri": f"{empty_jwks_server}/jwks", "issuer": empty_jwks_server},
    )
    with pytest.raises(InvalidCodeError):
        provider._verify_id_token(OPAQUE_PEER_KEY)
