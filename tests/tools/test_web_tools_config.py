"""Tests for web backend selection and the web_search / web_extract availability gates.

Coverage:
  _get_backend() / _get_search_backend() / _get_extract_backend() — config pins and autodetect.
  check_web_api_key() — web_search gate (bundled ddgs or a ready plugin provider).
  check_web_extract_available() — web_extract gate (only an extract-capable ready provider).
  web_search_tool() — limit clamping and error sanitization.
"""

import json
from unittest.mock import MagicMock, patch

import pytest


def _fake_provider(name="fake-plugin-prov", *, search=True, extract=True, available=True):
    from agent.web_search_provider import WebSearchProvider

    class FakePluginProvider(WebSearchProvider):
        @property
        def name(self):
            return name

        def is_available(self):
            return available

        def supports_search(self):
            return search

        def supports_extract(self):
            return extract

    return FakePluginProvider()


@pytest.fixture
def clean_registry():
    from agent.web_search_registry import _reset_for_tests

    _reset_for_tests()
    with patch("tools.web_tools._ensure_web_plugins_loaded"):
        yield
    _reset_for_tests()


class TestBackendSelection:
    def test_never_configured_with_ddgs_importable_is_ddgs(self):
        with patch("tools.web_tools._load_web_config", return_value={}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=True):
            from tools.web_tools import _get_backend
            assert _get_backend() == "ddgs"

    def test_never_configured_without_any_provider_defaults_to_ddgs(self, clean_registry):
        with patch("tools.web_tools._load_web_config", return_value={}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=False):
            from tools.web_tools import _get_backend
            assert _get_backend() == "ddgs"

    def test_stored_backend_is_returned_verbatim(self):
        with patch("tools.web_tools._load_web_config", return_value={"backend": "Firecrawl "}):
            from tools.web_tools import _get_backend
            assert _get_backend() == "firecrawl"

    def test_search_pin_wins_over_shared_backend(self):
        with patch("tools.web_tools._load_web_config",
                   return_value={"backend": "other", "search_backend": "ddgs"}):
            from tools.web_tools import _get_search_backend
            assert _get_search_backend() == "ddgs"

    def test_search_pin_does_not_reroute_extract(self):
        with patch("tools.web_tools._load_web_config", return_value={"search_backend": "ddgs"}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=True):
            from tools.web_tools import _get_extract_backend
            assert _get_extract_backend() == "ddgs"

    def test_null_backend_value_does_not_crash(self):
        with patch("tools.web_tools._load_web_config", return_value={"backend": None}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=True):
            from tools.web_tools import _get_backend
            assert _get_backend() == "ddgs"


class TestCheckWebApiKey:
    def test_ddgs_importable_lights_search_gate(self):
        with patch("tools.web_tools._load_web_config", return_value={"search_backend": "ddgs"}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=True):
            from tools.web_tools import check_web_api_key
            assert check_web_api_key() is True

    def test_nothing_available_keeps_search_gate_off(self, clean_registry):
        with patch("tools.web_tools._load_web_config", return_value={}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=False):
            from tools.web_tools import check_web_api_key
            assert check_web_api_key() is False

    def test_null_backend_value_does_not_crash(self, clean_registry):
        with patch("tools.web_tools._load_web_config", return_value={"backend": None}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=False):
            from tools.web_tools import check_web_api_key
            assert check_web_api_key() is False

    def test_removed_backend_value_falls_back_to_ddgs(self):
        with patch("tools.web_tools._load_web_config", return_value={"backend": "tavily"}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=True):
            from tools.web_tools import check_web_api_key
            assert check_web_api_key() is True

    def test_explicit_unavailable_active_provider_is_not_ready(self):
        unavailable = _fake_provider("custom-down", available=False)
        with patch("tools.web_tools._load_web_config", return_value={"backend": "custom-down"}), \
             patch("tools.web_tools._is_backend_available", return_value=False), \
             patch("tools.web_tools._ensure_web_plugins_loaded"), \
             patch("agent.web_search_registry.get_active_search_provider", return_value=unavailable):
            from tools.web_tools import _provider_is_ready, check_web_api_key
            assert _provider_is_ready(unavailable) is False
            assert check_web_api_key() is False

    def test_custom_plugin_provider_lights_search_gate(self, clean_registry):
        from agent.web_search_registry import register_provider

        register_provider(_fake_provider())
        with patch("tools.web_tools._load_web_config", return_value={}), \
             patch("tools.web_tools._ddgs_package_importable", return_value=False):
            from tools.web_tools import _get_backend, check_web_api_key
            assert check_web_api_key() is True
            assert _get_backend() == "fake-plugin-prov"


class TestCheckWebExtractAvailable:
    def test_search_only_ddgs_hides_web_extract(self, clean_registry):
        from agent.web_search_registry import register_provider
        from plugins.web.ddgs.provider import DDGSWebSearchProvider

        register_provider(DDGSWebSearchProvider())
        with patch("tools.web_tools._load_web_config", return_value={"search_backend": "ddgs"}), \
             patch("agent.web_search_registry._read_config_key", return_value=None), \
             patch("tools.web_tools._ddgs_package_importable", return_value=True), \
             patch.object(DDGSWebSearchProvider, "is_available", return_value=True):
            from tools.web_tools import check_web_api_key, check_web_extract_available
            assert check_web_api_key() is True
            assert check_web_extract_available() is False

    def test_ready_extract_plugin_shows_web_extract(self, clean_registry):
        from agent.web_search_registry import register_provider

        register_provider(_fake_provider("fake-extract", search=False, extract=True))
        with patch("agent.web_search_registry._read_config_key", return_value=None):
            from tools.web_tools import check_web_extract_available
            assert check_web_extract_available() is True

    def test_unavailable_extract_plugin_keeps_web_extract_hidden(self, clean_registry):
        from agent.web_search_registry import register_provider

        register_provider(_fake_provider("fake-extract", search=False, extract=True, available=False))
        with patch("agent.web_search_registry._read_config_key", return_value="fake-extract"):
            from tools.web_tools import check_web_extract_available
            assert check_web_extract_available() is False

    def test_extract_dispatch_falls_through_search_only_shared_backend(self, clean_registry):
        from agent.web_search_registry import register_provider
        from tools.web_tools_extract import _resolve_extract_provider

        extractor = _fake_provider("fake-extract", search=False, extract=True)
        register_provider(_fake_provider("search-only", search=True, extract=False))
        register_provider(extractor)
        with patch("tools.web_tools._load_web_config", return_value={"backend": "search-only"}), \
             patch("agent.web_search_registry._read_config_key", return_value=None):
            provider, error = _resolve_extract_provider("search-only")
        assert error is None
        assert provider is extractor

    def test_search_only_extract_pin_is_a_typed_error(self, clean_registry):
        from agent.web_search_registry import register_provider
        from tools.web_tools_extract import _resolve_extract_provider

        register_provider(_fake_provider("search-only", search=True, extract=False))
        with patch("tools.web_tools._load_web_config", return_value={"extract_backend": "search-only"}):
            provider, error = _resolve_extract_provider("search-only")
        assert provider is None
        assert "search-only backend" in json.loads(error)["error"]


class TestWebSearchSchema:
    def test_web_search_clamps_limit_before_backend_call(self):
        import tools.web_tools

        fake_search = MagicMock(return_value={"success": True, "data": {"web": []}})
        fake_provider = MagicMock(supports_search=MagicMock(return_value=True))
        fake_provider.search = fake_search
        fake_provider.name = "fake"

        with patch("tools.web_tools._get_search_backend", return_value="fake"), \
             patch("tools.web_tools._ensure_web_plugins_loaded"), \
             patch("agent.web_search_registry.get_provider", return_value=fake_provider), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch.object(tools.web_tools._debug, "log_call"), \
             patch.object(tools.web_tools._debug, "save"):
            result = json.loads(tools.web_tools.web_search_tool("docs", limit=500))

        assert result == {"success": True, "data": {"web": []}}
        fake_search.assert_called_once_with("docs", 100)


class TestWebSearchErrorHandling:
    def test_search_error_response_does_not_expose_diagnostics(self):
        import tools.web_tools

        fake_provider = MagicMock(supports_search=MagicMock(return_value=True))
        fake_provider.search.side_effect = RuntimeError("boom")
        fake_provider.name = "fake"

        with patch("tools.web_tools._get_search_backend", return_value="fake"), \
             patch("tools.web_tools._ensure_web_plugins_loaded"), \
             patch("agent.web_search_registry.get_provider", return_value=fake_provider), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch.object(tools.web_tools._debug, "log_call") as mock_log_call, \
             patch.object(tools.web_tools._debug, "save"):
            result = json.loads(tools.web_tools.web_search_tool("test query", limit=3))

        assert result == {"error": "Error searching web: boom"}
        debug_payload = mock_log_call.call_args.args[1]
        assert debug_payload["error"] == "Error searching web: boom"
        for key in ("config", "exception_type", "exception_chain", "traceback"):
            assert key not in result

    def test_removed_backend_selection_names_the_removal(self, clean_registry):
        import tools.web_tools

        with patch("tools.web_tools._load_web_config", return_value={"backend": "firecrawl"}), \
             patch("tools.web_tools.selection_exists", return_value=True), \
             patch("tools.web_tools_extract._no_provider_error", side_effect=lambda cap, fallback: fallback), \
             patch("tools.interrupt.is_interrupted", return_value=False), \
             patch.object(tools.web_tools._debug, "log_call"), \
             patch.object(tools.web_tools._debug, "save"):
            result = json.loads(tools.web_tools.web_search_tool("q"))

        assert result["success"] is False
        assert "Firecrawl backend was removed" in result["error"]


def test_get_provider_env_unset_returns_empty(monkeypatch):
    monkeypatch.delenv("WSP_TEST_UNSET_KEY", raising=False)
    with patch("hermes_cli.config.get_env_value", return_value=None):
        from agent.web_search_provider import get_provider_env

        assert get_provider_env("WSP_TEST_UNSET_KEY") == ""
