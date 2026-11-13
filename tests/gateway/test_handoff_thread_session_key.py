"""Regression: a CLI→Telegram handoff binds the session key the adapter uses for replies in the
handoff topic, so the next reply continues the handed-off session instead of opening a new one."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gateway.config import GatewayConfig, HomeChannel, Platform, PlatformConfig
from gateway.run import GatewayRunner
from gateway.session import SessionSource, build_session_key


def _handoff_destination(platform: Platform, channel_id: str, thread_id: str, scope_id, adapter):
    """Run the real handoff destination/key path against a configured home channel."""
    config = GatewayConfig(platforms={platform: PlatformConfig(enabled=True, token="test")})
    config.platforms[platform].home_channel = HomeChannel(
        platform=platform, chat_id=channel_id, name="home", scope_id=scope_id)
    adapter.create_handoff_thread = AsyncMock(return_value=thread_id)
    runner = object.__new__(GatewayRunner)
    runner.config = config
    runner.adapters = {platform: adapter}
    runner.session_store = None
    with patch("gateway.delivery.resolve_delivery_transport",
               lambda *_a: SimpleNamespace(adapter=adapter, send=AsyncMock())):
        dest = asyncio.run(runner._handoff_resolve_destination(
            {"id": "cli-session", "title": "work", "handoff_platform": platform.value}, profile_name=None))
    return dest, runner._handoff_session_key(dest, profile_name=None)


def test_telegram_forum_handoff_key_matches_the_topic_reply_key():
    """The Telegram adapter keys forum-topic replies ``group:<chat>:<topic>``; the handoff must
    bind the same slot, not ``thread``."""
    _dest, handoff = _handoff_destination(Platform.TELEGRAM, "-1001234567", "77", None, SimpleNamespace())
    assert handoff == build_session_key(SessionSource(
        platform=Platform.TELEGRAM, chat_id="-1001234567", chat_type="group", user_id="42",
        thread_id="77"), thread_sessions_per_user=False)
    assert handoff == "agent:main:telegram:group:-1001234567:77"
