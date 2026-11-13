import json
import os
from datetime import datetime, timedelta, UTC
from unittest.mock import patch

from tools import managed_gateway_auth


def test_read_nous_access_token_refreshes_expiring_cached_token(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    expires_at = (datetime.now(UTC) + timedelta(seconds=30)).isoformat()
    (tmp_path / "auth.json").write_text(json.dumps({
        "providers": {
            "nous": {
                "access_token": "stale-token",
                "refresh_token": "refresh-token",
                "expires_at": expires_at,
            }
        }
    }))
    monkeypatch.setattr(
        "hermes_cli.auth.resolve_nous_access_token",
        lambda refresh_skew_seconds=120: "fresh-token",
    )

    assert managed_gateway_auth.read_nous_access_token() == "fresh-token"


def test_connector_gateway_origin_pins_the_deployed_connectors_host():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CONNECTOR_GATEWAY_URL", None)
        assert managed_gateway_auth.connector_gateway_origin() == "https://connector-gateway.nousresearch.com"


def test_connector_gateway_origin_honors_its_own_override():
    with patch.dict(os.environ, {"CONNECTOR_GATEWAY_URL": "http://127.0.0.1:3009/"}, clear=False):
        assert managed_gateway_auth.connector_gateway_origin() == "http://127.0.0.1:3009"
        assert managed_gateway_auth.is_connector_gateway_url("http://127.0.0.1:3009/v1/connectors/search")


def test_default_bearer_gate_accepts_the_deployed_connector_host_only():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("CONNECTOR_GATEWAY_URL", None)
        assert managed_gateway_auth.is_connector_gateway_url(
            "https://connector-gateway.nousresearch.com/v1/connectors/execute")
        for untrusted in (
            "https://tool-gateway.nousresearch.com/api/vendorx/generations",
            "https://tools.nousresearch.com/v1/connectors/execute",
            "https://evil-connector-gateway.nousresearch.com.attacker.dev/v1/connectors",
            "https://connector-gateway.nousresearch.com.attacker.dev/v1/connectors",
            "http://connector-gateway.nousresearch.com/v1/connectors",
        ):
            assert not managed_gateway_auth.is_connector_gateway_url(untrusted)
            assert managed_gateway_auth.managed_gateway_auth_headers(untrusted, token_reader=lambda: "tok") == {}


def test_read_nous_provider_state_falls_back_to_global_root_for_share_auth_profiles(tmp_path, monkeypatch):
    root = tmp_path / ".hermes"
    profile = root / "profiles" / "work"
    profile.mkdir(parents=True)
    (root / "auth.json").write_text(json.dumps({
        "version": 1,
        "providers": {"nous": {"auth_method": "anonymous", "access_token": "tok"}},
    }))
    monkeypatch.setenv("HERMES_HOME", str(profile))
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    import hermes_constants
    from hermes_cli import auth as auth_mod

    monkeypatch.setattr(hermes_constants, "get_default_hermes_root", lambda: root)
    monkeypatch.setattr(auth_mod, "get_hermes_home", lambda: profile)
    monkeypatch.setattr(auth_mod, "_global_auth_store_cache", None)
    monkeypatch.setattr(auth_mod, "_auth_file_path", lambda: profile / "auth.json")

    state = managed_gateway_auth._read_nous_provider_state()

    assert state is not None
    assert state["auth_method"] == "anonymous"
