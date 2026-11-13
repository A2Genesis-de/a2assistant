"""Unit tests for tools/tool_backend_helpers.py.

Tests cover:
- normalize_browser_cloud_provider() coercion
- coerce_modal_mode() / normalize_modal_mode() validation
- has_direct_modal_credentials() detection
- resolve_openai_audio_api_key() priority chain
- read_selection() / REMOVED_BACKENDS for the retired Nous Tool Gateway selection
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tools.tool_backend_helpers import (
    coerce_modal_mode,
    has_direct_modal_credentials,
    normalize_browser_cloud_provider,
    read_selection,
    removed_backend_note,
    resolve_openai_audio_api_key,
    selection_error,
)


# ---------------------------------------------------------------------------
# normalize_browser_cloud_provider
# ---------------------------------------------------------------------------
class TestNormalizeBrowserCloudProvider:
    """Coerce arbitrary input to a lowercase browser provider key."""

    def test_none_returns_default(self):
        assert normalize_browser_cloud_provider(None) == "local"




# ---------------------------------------------------------------------------
# coerce_modal_mode / normalize_modal_mode
# ---------------------------------------------------------------------------
class TestCoerceModalMode:
    """Validate and coerce the requested modal execution mode."""

    @pytest.mark.parametrize("value", ["auto", "direct"])
    def test_valid_modes_passthrough(self, value):
        assert coerce_modal_mode(value) == value

    def test_none_returns_auto(self):
        assert coerce_modal_mode(None) == "auto"


    def test_strips_whitespace(self):
        assert coerce_modal_mode("  direct  ") == "direct"

    def test_retired_managed_mode_falls_back_to_auto(self):
        assert coerce_modal_mode("managed") == "auto"




# ---------------------------------------------------------------------------
# has_direct_modal_credentials
# ---------------------------------------------------------------------------
class TestHasDirectModalCredentials:
    """Detect Modal credentials via env vars or config file."""

    def test_no_env_no_file(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
        monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
        with patch.object(Path, "home", return_value=tmp_path):
            assert has_direct_modal_credentials() is False


    def test_only_token_secret_not_enough(self, monkeypatch, tmp_path):
        monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
        monkeypatch.setenv("MODAL_TOKEN_SECRET", "sec-456")
        with patch.object(Path, "home", return_value=tmp_path):
            assert has_direct_modal_credentials() is False


    def test_env_vars_take_priority_over_file(self, monkeypatch, tmp_path):
        monkeypatch.setenv("MODAL_TOKEN_ID", "id-123")
        monkeypatch.setenv("MODAL_TOKEN_SECRET", "sec-456")
        (tmp_path / ".modal.toml").touch()
        with patch.object(Path, "home", return_value=tmp_path):
            assert has_direct_modal_credentials() is True

    def test_home_dir_permission_denied(self, monkeypatch):
        """PermissionError on Path.home() should not crash (issue #33525)."""
        monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
        monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
        with patch.object(Path, "home", side_effect=PermissionError("denied")):
            assert has_direct_modal_credentials() is False

    def test_home_dir_permission_denied_with_env_vars(self, monkeypatch):
        """PermissionError on Path.home() should not prevent env var detection."""
        monkeypatch.setenv("MODAL_TOKEN_ID", "id-123")
        monkeypatch.setenv("MODAL_TOKEN_SECRET", "sec-456")
        with patch.object(Path, "home", side_effect=PermissionError("denied")):
            assert has_direct_modal_credentials() is True


# ---------------------------------------------------------------------------
# Retired Nous Tool Gateway selection
# ---------------------------------------------------------------------------
class TestRetiredToolGatewaySelection:
    def test_legacy_use_gateway_flag_is_ignored(self, monkeypatch):
        monkeypatch.setattr(
            "hermes_cli.config.read_raw_config_readonly",
            lambda: {"web": {"use_gateway": True, "backend": "ddgs"}, "tts": {"use_gateway": True}},
        )
        assert read_selection("web") == "ddgs"
        assert read_selection("tts") is None

    @pytest.mark.parametrize("section", ["web", "browser", "tts", "stt", "video_gen"])
    def test_stored_nous_selection_names_the_removal(self, section):
        assert "Nous Tool Gateway was removed" in removed_backend_note(section, "nous")
        assert "Nous Tool Gateway was removed" in selection_error(section, "nous", "unavailable")


# ---------------------------------------------------------------------------
# resolve_openai_audio_api_key
# ---------------------------------------------------------------------------
class TestResolveOpenaiAudioApiKey:
    """Priority: VOICE_TOOLS_OPENAI_KEY > OPENAI_API_KEY."""

    def test_voice_key_preferred(self, monkeypatch):
        monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "voice-key")
        monkeypatch.setenv("OPENAI_API_KEY", "general-key")
        assert resolve_openai_audio_api_key() == "voice-key"


    def test_strips_whitespace(self, monkeypatch):
        monkeypatch.setenv("VOICE_TOOLS_OPENAI_KEY", "  voice-key  ")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert resolve_openai_audio_api_key() == "voice-key"


# ---------------------------------------------------------------------------
# resolve_openai_audio_api_key — profile secret scope
# ---------------------------------------------------------------------------
class TestResolveOpenaiAudioApiKeyIsProfileScoped:
    """The key this returns authenticates the TTS/STT client.

    In a multiplex gateway ``os.environ`` holds whichever profile's ``.env``
    loaded at boot, not the profile the current turn belongs to — so a raw
    read here would let one profile's voice reply or voice-note transcription
    run on (and be billed to) another profile's OpenAI account. Same contract
    ``agent/vertex_adapter`` and the WeChat send path already follow.
    """

    @pytest.fixture(autouse=True)
    def _reset_multiplex(self):
        from agent import secret_scope as ss

        ss.set_multiplex_active(False)
        yield
        ss.set_multiplex_active(False)

    def test_scope_wins_over_another_profiles_environ(self, monkeypatch):
        from agent import secret_scope as ss

        monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-other-profile")
        ss.set_multiplex_active(True)
        token = ss.set_secret_scope({"OPENAI_API_KEY": "sk-this-profile"})
        try:
            assert resolve_openai_audio_api_key() == "sk-this-profile", (
                "voice/STT authenticated with another profile's OpenAI key"
            )
        finally:
            ss.reset_secret_scope(token)


    def test_single_profile_still_reads_environ(self, monkeypatch):
        """Control: no multiplexing, no scope — unchanged behaviour."""
        monkeypatch.delenv("VOICE_TOOLS_OPENAI_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-plain")
        assert resolve_openai_audio_api_key() == "sk-plain"
