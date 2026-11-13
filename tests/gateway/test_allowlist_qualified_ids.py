"""Allowlist matching compares qualified user_ids, not bare '@' localparts.

A bare allowlist entry ``alice`` must never admit ``alice@<any domain>`` for an '@'-shaped
user_id — the domain is something the sender controls.
"""

import pytest

from gateway.config import Platform
from gateway.session import SessionSource


def _source(platform: Platform, user_id: str) -> SessionSource:
    return SessionSource(
        platform=platform,
        user_id=user_id,
        chat_id=user_id,
        user_name="tester",
        chat_type="dm",
    )


def _make_runner():
    from gateway.run import GatewayRunner

    runner = object.__new__(GatewayRunner)
    runner.pairing_store = None
    return runner


@pytest.mark.parametrize("env_var", ["TELEGRAM_ALLOWED_USERS", "GATEWAY_ALLOWED_USERS"])
def test_bare_localpart_entry_admits_no_foreign_domain(monkeypatch, env_var):
    monkeypatch.setenv(env_var, "alice,bob@corp.example")
    runner = _make_runner()

    assert runner._is_user_authorized(_source(Platform.TELEGRAM, "alice@evil.example")) is False
    assert runner._is_user_authorized(_source(Platform.TELEGRAM, "bob@evil.example")) is False
    assert runner._is_user_authorized(_source(Platform.TELEGRAM, "bob@corp.example")) is True
