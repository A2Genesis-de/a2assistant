"""Plugin-side tests for the bundled web search provider and the registry resolution rules.

Uses real imports from the plugin modules (no mocking of provider classes) so drift in the ABC
interface, the registry, and the plugin glue layer is caught together.
"""
from __future__ import annotations

import pytest


def _ensure_plugins_loaded() -> None:
    from hermes_cli.plugins import _ensure_plugins_discovered

    _ensure_plugins_discovered()


def _fake_provider(name: str, *, available: bool, search: bool = True, extract: bool = False):
    from agent.web_search_provider import WebSearchProvider

    class FakeProvider(WebSearchProvider):
        @property
        def name(self):
            return name

        def is_available(self):
            return available

        def supports_search(self):
            return search

        def supports_extract(self):
            return extract

    return FakeProvider()


@pytest.fixture
def ddgs_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from plugins.web.ddgs.provider import DDGSWebSearchProvider

    monkeypatch.setattr(DDGSWebSearchProvider, "is_available", lambda self: False)


class TestBundledDDGS:
    def test_ddgs_registers_as_search_only(self) -> None:
        _ensure_plugins_loaded()
        from agent.web_search_registry import get_provider

        provider = get_provider("ddgs")
        assert provider is not None
        assert provider.supports_search() is True
        assert provider.supports_extract() is False

    def test_ddgs_setup_schema_installs_the_package(self) -> None:
        from plugins.web.ddgs.provider import DDGSWebSearchProvider

        schema = DDGSWebSearchProvider().get_setup_schema()
        assert schema["post_setup"] == "ddgs"
        assert schema["env_vars"] == []


class TestRegistryResolution:
    def test_explicit_configured_provider_returned_even_when_unavailable(self, ddgs_missing) -> None:
        _ensure_plugins_loaded()
        from agent.web_search_registry import _resolve

        result = _resolve("ddgs", capability="search")
        assert result is not None
        assert result.name == "ddgs"
        assert result.is_available() is False

    def test_unknown_configured_name_falls_back_to_available_provider(self, ddgs_missing) -> None:
        _ensure_plugins_loaded()
        from agent.web_search_registry import _providers, _resolve, register_provider

        register_provider(_fake_provider("fake-available", available=True))
        try:
            result = _resolve("not-a-real-provider", capability="search")
        finally:
            _providers.pop("fake-available", None)
        assert result is not None
        assert result.name == "fake-available"

    def test_no_config_no_available_provider_returns_none(self, ddgs_missing) -> None:
        _ensure_plugins_loaded()
        from agent.web_search_registry import _resolve

        assert _resolve(None, capability="search") is None

    def test_no_extract_capable_provider_resolves_none(self) -> None:
        _ensure_plugins_loaded()
        from agent.web_search_registry import _resolve

        assert _resolve("ddgs", capability="extract") is None
