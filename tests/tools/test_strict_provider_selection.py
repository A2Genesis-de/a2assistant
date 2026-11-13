"""Strict tool-provider selection: the `hermes tools` choice always wins.

Policy (owner decision): the provider string stored in config.yaml is what
runs at call time. A vendor name → that vendor direct with the user's own
credentials; no key ever written → today's credential autodetect. Credential
presence must NEVER select or reroute; a selected-but-broken provider produces
an honest error naming the selection and pointing at `hermes tools`.
"""

from unittest.mock import patch

import pytest

from tools import tool_backend_helpers as tbh


# ---------------------------------------------------------------------------
# read_selection — the shared helper
# ---------------------------------------------------------------------------


class TestReadSelection:
    def _with_raw(self, raw):
        return patch(
            "hermes_cli.config.read_raw_config_readonly",
            return_value=raw,
        )

    def test_never_configured_returns_none(self):
        with self._with_raw({}):
            assert tbh.read_selection("image_gen") is None

    def test_vendor_provider_returned(self):
        with self._with_raw({"image_gen": {"provider": "fal"}}):
            assert tbh.read_selection("image_gen") == "fal"

    def test_legacy_use_gateway_flag_is_ignored(self):
        with self._with_raw({"video_gen": {"provider": "fal", "use_gateway": True}}):
            assert tbh.read_selection("video_gen") == "fal"

    def test_empty_string_backend_is_no_selection(self):
        """DEFAULT_CONFIG's seeded empty strings are not selections."""
        with self._with_raw({"web": {"backend": ""}}):
            assert tbh.read_selection("web") is None

    def test_raw_stt_local_is_a_selection(self):
        """A raw config.yaml ``stt.provider: local`` is a genuine pick: the
        DEFAULT_CONFIG seed never reached disk (save_config strips schema
        defaults), and the picker's Local Whisper row writes exactly this shape."""
        with self._with_raw({"stt": {"provider": "local"}}):
            assert tbh.read_selection("stt") == "local"

    def test_browser_backend_key_is_not_the_cloud_selection(self):
        """browser.backend is the driver choice (browser-use CLI vs built-in
        tools), not the cloud provider selection."""
        with self._with_raw({"browser": {"backend": "browser-use"}}):
            assert tbh.read_selection("browser") is None

    def test_web_per_capability_keys_mark_configured(self):
        with self._with_raw({"web": {"search_backend": "searxng"}}):
            assert tbh.read_selection("web") is None
            assert tbh.selection_exists("web") is True


# ---------------------------------------------------------------------------
# Image generation (FAL)
# ---------------------------------------------------------------------------


class TestImageFalStrictSelection:
    def test_fal_selection_missing_key_names_the_selection(self):
        from tools import image_generation_tool as it

        with patch.object(it, "read_selection", return_value="fal"), \
             patch.object(it, "fal_key_is_configured", return_value=False):
            with pytest.raises(ValueError) as exc:
                it._require_fal_backend()
        assert "FAL_KEY" in str(exc.value)
        assert "image_gen is configured to use fal" in str(exc.value)
        assert "hermes tools" in str(exc.value)

    def test_fal_selection_with_key_routes_direct(self):
        from tools import image_generation_tool as it

        with patch.object(it, "read_selection", return_value="fal"), \
             patch.object(it, "fal_key_is_configured", return_value=True):
            it._require_fal_backend()
            assert it.check_fal_api_key() is True

    def test_never_configured_without_key_reports_no_backend(self):
        from tools import image_generation_tool as it

        with patch.object(it, "read_selection", return_value=None), \
             patch.object(it, "fal_key_is_configured", return_value=False):
            with pytest.raises(ValueError) as exc:
                it._require_fal_backend()
            assert it.check_fal_api_key() is False
        assert "Image generation is unavailable" in str(exc.value)


# ---------------------------------------------------------------------------
# Video generation (FAL plugin)
# ---------------------------------------------------------------------------


class TestVideoFalStrictSelection:
    def test_fal_selection_missing_key_names_the_selection(self):
        from plugins.video_gen import fal as vf

        with patch("tools.tool_backend_helpers.read_selection", return_value="fal"), \
             patch("tools.tool_backend_helpers.fal_key_is_configured", return_value=False):
            with pytest.raises(ValueError) as exc:
                vf._fal_video_available()
        assert "video_gen is configured to use fal" in str(exc.value)
        assert "FAL_KEY" in str(exc.value)

    def test_never_configured_autodetect_unchanged(self):
        from plugins.video_gen import fal as vf

        with patch("tools.tool_backend_helpers.read_selection", return_value=None), \
             patch("tools.tool_backend_helpers.fal_key_is_configured", return_value=True):
            assert vf._fal_video_available() is True


# ---------------------------------------------------------------------------
# STT (OpenAI audio resolver)
# ---------------------------------------------------------------------------


class TestSttStrictSelection:
    def test_vendor_selection_missing_key_names_the_selection(self):
        from tools import transcription_tools as tt

        with patch.object(tt, "_load_stt_config", return_value={}), \
             patch("tools.tool_backend_helpers.read_selection", return_value="openai"), \
             patch("tools.tool_backend_helpers.resolve_openai_audio_api_key", return_value=""):
            with pytest.raises(ValueError) as exc:
                tt._resolve_openai_audio_client_config()
        assert "stt is configured to use openai" in str(exc.value)
        assert "hermes tools" in str(exc.value)

    def test_stored_nous_selection_reports_the_removed_gateway(self):
        from tools import transcription_tools as tt

        with patch.object(tt, "_load_stt_config", return_value={}), \
             patch("tools.tool_backend_helpers.read_selection", return_value="nous"), \
             patch("tools.tool_backend_helpers.resolve_openai_audio_api_key", return_value=""):
            with pytest.raises(ValueError) as exc:
                tt._resolve_openai_audio_client_config()
        assert "Nous Tool Gateway was removed" in str(exc.value)

    def test_never_configured_keeps_legacy_ladder(self):
        from tools import transcription_tools as tt

        with patch.object(tt, "_load_stt_config", return_value={}), \
             patch("tools.tool_backend_helpers.read_selection", return_value=None), \
             patch("tools.tool_backend_helpers.resolve_openai_audio_api_key", return_value="sk-env"):
            api_key, _base_url = tt._resolve_openai_audio_client_config()
        assert api_key == "sk-env"


# ---------------------------------------------------------------------------
# Browser Use provider
# ---------------------------------------------------------------------------


class TestBrowserUseStrictSelection:
    def _provider(self):
        from plugins.browser.browser_use.provider import BrowserUseBrowserProvider

        return BrowserUseBrowserProvider()

    def test_vendor_selection_missing_key_names_the_selection(self):
        provider = self._provider()
        with patch("plugins.browser.browser_use.provider.get_secret", return_value=""), \
             patch("tools.tool_backend_helpers.read_selection", return_value="browser-use"):
            with pytest.raises(ValueError) as exc:
                provider._get_config()
        assert "browser is configured to use browser-use" in str(exc.value)
        assert "BROWSER_USE_API_KEY" in str(exc.value)

    def test_key_routes_direct(self):
        provider = self._provider()
        with patch("plugins.browser.browser_use.provider.get_secret", return_value="bu-key"):
            config = provider._get_config()
        assert config["api_key"] == "bu-key"


# ---------------------------------------------------------------------------
# tools_config writers: one provider string per row
# ---------------------------------------------------------------------------


class TestWriteProviderConfig:
    def test_row_writes_vendor(self):
        from hermes_cli.tools_config import _write_provider_config

        config = {"web": {"backend": "nous"}}
        provider = {"name": "Keenable", "web_backend": "keenable"}
        _write_provider_config(provider, config)
        assert config["web"]["backend"] == "keenable"

    def test_stt_row_replaces_a_stored_nous_selection(self):
        from hermes_cli.tools_config import _write_provider_config

        config = {"stt": {"provider": "nous"}}
        provider = {"name": "Groq Whisper", "stt_provider": "groq"}
        _write_provider_config(provider, config)
        assert config["stt"]["provider"] == "groq"
