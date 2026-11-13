"""
Tests for send_image_file() on Telegram,
and MEDIA: .png extraction/routing in the base platform adapter.

Covers: local image file sending, file-not-found handling, fallback on error,
        MEDIA: tag extraction for image extensions, and routing to send_image_file.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.config import PlatformConfig
from gateway.platforms.base import BasePlatformAdapter


def _run(coro):
    """Run a coroutine in a fresh event loop for sync-style tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# MEDIA: extraction tests for image files
# ---------------------------------------------------------------------------


class TestExtractMediaImages:
    """Test that MEDIA: tags with image extensions are correctly extracted."""

    def test_png_image_extracted(self):
        content = "Here is the screenshot:\nMEDIA:/home/user/.hermes/browser_screenshots/shot.png"
        media, cleaned = BasePlatformAdapter.extract_media(content)
        assert len(media) == 1
        assert media[0][0] == "/home/user/.hermes/browser_screenshots/shot.png"
        assert "MEDIA:" not in cleaned
        assert "Here is the screenshot" in cleaned


# ---------------------------------------------------------------------------
# Telegram send_image_file tests
# ---------------------------------------------------------------------------
from plugins.platforms.telegram.adapter import TelegramAdapter


class TestTelegramSendImageFile:
    @pytest.fixture
    def adapter(self):
        config = PlatformConfig(enabled=True, token="fake-token")
        a = TelegramAdapter(config)
        a._bot = MagicMock()
        return a

    def test_sends_local_image_as_photo(self, adapter, tmp_path):
        """send_image_file should call bot.send_photo with the opened file."""
        img = tmp_path / "screenshot.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)  # Minimal PNG-like

        mock_msg = MagicMock()
        mock_msg.message_id = 42
        adapter._bot.send_photo = AsyncMock(return_value=mock_msg)

        result = _run(
            adapter.send_image_file(chat_id="12345", image_path=str(img))
        )
        assert result.success
        assert result.message_id == "42"
        adapter._bot.send_photo.assert_awaited_once()

        # Verify photo arg was a file object (opened in rb mode)
        call_kwargs = adapter._bot.send_photo.call_args
        assert call_kwargs.kwargs["chat_id"] == 12345


    def test_returns_error_when_not_connected(self, adapter):
        """send_image_file should return error when bot is None."""
        adapter._bot = None
        result = _run(
            adapter.send_image_file(chat_id="12345", image_path="/tmp/img.png")
        )
        assert not result.success
        assert "Not connected" in result.error
