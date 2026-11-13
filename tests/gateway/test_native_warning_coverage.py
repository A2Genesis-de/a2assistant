"""Native diagnostic producers keep captions, controls and truthful receipts.

No live platform connections: actual adapters run against recording transports.
"""
import json
from types import SimpleNamespace

import pytest

from gateway.config import PlatformConfig


@pytest.fixture(params=[None, False, True, "override"])
def policy(request, tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    setting = request.param
    if setting is not None:
        display = {"suppress_warning_notifications": setting is True}
        if setting == "override":
            display["platforms"] = {
                name: {"suppress_warning_notifications": True}
                for name in ("telegram",)
            }
        (tmp_path / "config.yaml").write_text(json.dumps({"display": display}))
    return setting is True or setting == "override"


@pytest.mark.asyncio
async def test_telegram_cache_warning_does_not_hide_inbound_context(policy):
    from plugins.platforms.telegram.adapter import TelegramAdapter

    adapter = TelegramAdapter(PlatformConfig())
    frames = []

    async def reply_text(text):
        frames.append(text)

    from gateway.platforms.event import MessageEvent
    event = MessageEvent(text="Requested content", source=adapter.build_source(chat_id="42", user_id="42"))
    await adapter._surface_media_cache_failure(SimpleNamespace(reply_text=reply_text), event, "photo", RuntimeError("fixture"))
    assert bool(frames) is (not policy)
    assert event.text.startswith("Requested content")
    assert "could not be downloaded" in event.text
    assert ("asked to retry" in event.text) is (not policy)
