"""
Tests for ``send_multiple_images`` native batching across platforms.

Covers:
    - Base default loop (per-image fallback for platforms without native batching)
    - Telegram: ``bot.send_media_group`` with chunking at 10
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.base import BasePlatformAdapter


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Base default loop
# ---------------------------------------------------------------------------


class _StubAdapter(BasePlatformAdapter):
    """Minimal adapter that records per-image send calls."""

    name = "stub"

    def __init__(self):
        self.sent_images = []
        self.sent_animations = []
        self.sent_files = []

    async def connect(self, *, is_reconnect: bool = False):
        return True

    async def disconnect(self):
        return None

    async def send(self, chat_id, content, reply_to=None, **kwargs):
        from gateway.platforms.base import SendResult
        return SendResult(success=True)

    async def get_chat_info(self, chat_id):
        return {}

    async def send_image(self, chat_id, image_url, caption=None, **kwargs):
        from gateway.platforms.base import SendResult
        self.sent_images.append((chat_id, image_url, caption))
        return SendResult(success=True, message_id=str(len(self.sent_images)))

    async def send_animation(self, chat_id, animation_url, caption=None, **kwargs):
        from gateway.platforms.base import SendResult
        self.sent_animations.append((chat_id, animation_url, caption))
        return SendResult(success=True, message_id=str(len(self.sent_animations)))

    async def send_image_file(self, chat_id, image_path, caption=None, **kwargs):
        from gateway.platforms.base import SendResult
        self.sent_files.append((chat_id, image_path, caption))
        return SendResult(success=True, message_id=str(len(self.sent_files)))


class TestBaseDefaultLoop:
    def test_loops_per_image_by_default(self, tmp_path):
        local = tmp_path / "foo.png"
        a = _StubAdapter()
        images = [
            ("https://x.com/a.png", "alt 1"),
            ("https://x.com/b.png", "alt 2"),
            (local.as_uri(), "local"),
            ("https://x.com/c.gif", ""),
        ]
        _run(a.send_multiple_images("chat1", images))
        # 2 URL images + 1 animation + 1 local file
        assert len(a.sent_images) == 2
        assert len(a.sent_animations) == 1
        assert len(a.sent_files) == 1
        assert a.sent_files[0][1] == str(local)


from plugins.platforms.telegram.adapter import TelegramAdapter


class TestTelegramMultiImage:
    @pytest.fixture
    def adapter(self):
        config = PlatformConfig(enabled=True, token="fake-token")
        a = TelegramAdapter(config)
        a._bot = MagicMock()
        a._bot.send_media_group = AsyncMock(return_value=[MagicMock(message_id=1)])
        return a

    def test_single_batch_under_10_calls_send_media_group_once(self, adapter):
        """3 photos → one send_media_group call with 3 items."""
        import telegram
        images = [(f"https://x.com/{i}.png", f"alt{i}") for i in range(3)]
        # Make InputMediaPhoto a concrete class that records its args
        telegram.InputMediaPhoto = MagicMock(side_effect=lambda media, caption=None: {"media": media, "caption": caption})

        _run(adapter.send_multiple_images("12345", images))

        adapter._bot.send_media_group.assert_awaited_once()
        call_kwargs = adapter._bot.send_media_group.call_args.kwargs
        assert call_kwargs["chat_id"] == 12345
        assert len(call_kwargs["media"]) == 3

    def test_batch_over_10_chunks(self, adapter):
        """15 photos → two send_media_group calls (10 + 5)."""
        import telegram
        images = [(f"https://x.com/{i}.png", "") for i in range(15)]
        telegram.InputMediaPhoto = MagicMock(side_effect=lambda media, caption=None: {"media": media})

        _run(adapter.send_multiple_images("12345", images))

        assert adapter._bot.send_media_group.await_count == 2
        sizes = [len(c.kwargs["media"]) for c in adapter._bot.send_media_group.await_args_list]
        assert sizes == [10, 5]

    @pytest.mark.parametrize("body,sends,ambiguous", [("json", 2, None), ("html", 1, True)])
    def test_album_on_a_5xx_resends_only_telegrams_json_answer(self, adapter, body, sends, ambiguous):
        """Telegram's JSON 502 (PTB's unchained ``NetworkError('Bad Gateway')``) was not posted: the
        same sendMediaGroup goes again, as text does. A proxy's HTML 502 page (PTB's NetworkError
        chained to the failed body parse) may follow a posted album: one request, ambiguous."""
        import json
        import telegram
        from telegram.error import NetworkError, TelegramError
        telegram.InputMediaPhoto = MagicMock(side_effect=lambda media, caption=None: {"media": media})
        if body == "json":
            first = NetworkError("Bad Gateway")
        else:
            try:
                try:
                    json.loads("<html>")
                except ValueError as parse:
                    raise TelegramError("Invalid server response") from parse
            except TelegramError as invalid:
                first = NetworkError("Bad Gateway (502). Parsing the server response b'<html>' failed")
                first.__cause__ = invalid
        adapter._bot.send_media_group = AsyncMock(side_effect=[first, [MagicMock(message_id=1)]])
        adapter.send_image = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            result = _run(adapter.send_multiple_images("12345", [(f"https://x.com/{i}.png", "") for i in range(2)]))

        assert result.success is True
        assert adapter._bot.send_media_group.await_count == sends
        assert (result.raw_response or {}).get("ambiguous") is ambiguous
        adapter.send_image.assert_not_awaited()
