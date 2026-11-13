"""A fresh native input from an adapter that does not declare ``authorization_is_upstream``
is still default-denied without a principal allowlist (#139199)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from gateway.config import GatewayConfig, Platform
from gateway.platforms.event import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session_envelope import snapshot_native
from hermes_state_runtime import RuntimeStoreError


def _clear_authz_env(monkeypatch) -> None:
    for key in (
        "TELEGRAM_ALLOWED_USERS",
        "GATEWAY_ALLOWED_USERS",
        "GATEWAY_ALLOW_ALL_USERS",
    ):
        monkeypatch.delenv(key, raising=False)


def _fresh_native_event(
    source, text="hello from a peer", message_id="m1"
) -> MessageEvent:
    return MessageEvent(
        text=text, message_type=MessageType.TEXT, message_id=message_id, source=source
    )


@pytest.mark.asyncio
async def test_non_upstream_adapter_still_default_denies_without_allowlist(
    tmp_path, monkeypatch
):
    from gateway.session import SessionSource

    _clear_authz_env(monkeypatch)
    runner = GatewayRunner(GatewayConfig(sessions_dir=tmp_path / "sessions"))
    runner.adapters = {
        Platform.TELEGRAM: SimpleNamespace(
            send=AsyncMock(),
            authorization_is_upstream=False,
            enforces_own_access_policy=False,
        )
    }
    source = SessionSource(
        platform=Platform.TELEGRAM,
        user_id="123",
        chat_id="456",
        user_name="someone",
        chat_type="dm",
    )
    with pytest.raises(RuntimeStoreError, match="permission_denied"):
        snapshot_native(runner, _fresh_native_event(source))
