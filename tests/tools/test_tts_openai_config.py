"""tts.openai.api_key / base_url from config.yaml drive the OpenAI audio client.

Regression coverage for issue #26175: the resolver was env-only
(VOICE_TOOLS_OPENAI_KEY / OPENAI_API_KEY) and always returned the default
OpenAI base URL, ignoring the tts.openai config block. Resolution order now
mirrors the STT resolver: config -> env (still honoring config base_url).
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools import tts_tool, tts_tool_openai


class TestResolveOpenaiAudioClientConfig:
    def test_prefers_tts_config_credentials_and_base_url(self):
        config = {
            "provider": "openai",
            "openai": {
                "api_key": "cfg-key",
                "base_url": "http://localhost:4003/v1",
            },
        }

        with patch.object(tts_tool, "_load_tts_config", return_value=config), \
             patch.object(tts_tool_openai, "read_selection", return_value="openai"), \
             patch.object(tts_tool_openai, "resolve_openai_audio_api_key", return_value="env-key"):
            assert tts_tool_openai._resolve_openai_audio_client_config() == (
                "cfg-key",
                "http://localhost:4003/v1",
            )

    def test_config_without_base_url_falls_back_to_default_openai_base(self):
        config = {"openai": {"api_key": "cfg-key"}}

        with patch.object(tts_tool, "_load_tts_config", return_value=config), \
             patch.object(tts_tool_openai, "read_selection", return_value=None):
            assert tts_tool_openai._resolve_openai_audio_client_config() == (
                "cfg-key",
                tts_tool_openai.DEFAULT_OPENAI_BASE_URL,
            )

    def test_vendor_selection_missing_key_raises_selection_error(self):
        """A stored vendor selection with no credentials errors by name."""
        with patch.object(tts_tool, "_load_tts_config", return_value={"provider": "openai"}), \
             patch.object(tts_tool_openai, "read_selection", return_value="openai"), \
             patch.object(tts_tool_openai, "resolve_openai_audio_api_key", return_value=""):
            with pytest.raises(ValueError) as exc:
                tts_tool_openai._resolve_openai_audio_client_config()
        assert "openai" in str(exc.value)

    def test_missing_config_and_env_raises_updated_error(self):
        with patch.object(tts_tool, "_load_tts_config", return_value={}), \
             patch.object(tts_tool_openai, "read_selection", return_value=None), \
             patch.object(tts_tool_openai, "resolve_openai_audio_api_key", return_value=""):
            with pytest.raises(ValueError) as exc:
                tts_tool_openai._resolve_openai_audio_client_config()

        assert "OPENAI_API_KEY" in str(exc.value)

    def test_config_api_key_counts_as_available_backend(self):
        config = {"openai": {"api_key": "cfg-key"}}
        with patch.object(tts_tool, "_load_tts_config", return_value=config):
            assert tts_tool_openai._has_openai_audio_backend() is True


@pytest.mark.parametrize("configured", ["tts-1-hd", "gpt-4o-mini-tts-2025-12-15", "kokoro"])
def test_configured_model_is_sent_unchanged(tmp_path, configured):
    """An OpenAI-compatible endpoint receives the configured speech model as-is."""
    created = []

    class _Client:
        def __init__(self, **_kwargs):
            self.audio = SimpleNamespace(speech=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            created.append(kwargs["model"])
            return SimpleNamespace(stream_to_file=lambda p: open(p, "wb").write(b"ID3"))

    with patch.object(tts_tool, "_import_openai_client", return_value=_Client), \
         patch.object(tts_tool_openai, "_resolve_openai_audio_client_config",
                      return_value=("key", "http://127.0.0.1:8000/v1")):
        tts_tool_openai._generate_openai_tts(
            "Hello", str(tmp_path / "out.mp3"), {"openai": {"model": configured}})
    assert created == [configured]
