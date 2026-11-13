"""Picker row highlighting for per-capability web backends.

``web_search``/``web_extract`` resolve ``web.search_backend`` / ``web.extract_backend``
first and only then fall back to the shared ``web.backend`` (tools/web_tools.py
``_get_search_backend`` / ``_get_extract_backend``).  The picker row's ``is_active``
must follow the same precedence, otherwise a vendor that is genuinely serving one
capability is displayed as inactive (#132511).
"""

import types

import pytest

from hermes_cli.tools_config_providers import _is_provider_active


def _row(backend: str, **extra) -> dict:
    return {"name": backend, "web_backend": backend, "env_vars": [], **extra}


@pytest.mark.parametrize("web,active,inactive", [
    ({"search_backend": "alpha", "extract_backend": "beta", "backend": "alpha"}, ["alpha", "beta"], ["ddgs"]),
    ({"search_backend": "gamma", "extract_backend": "beta", "backend": "alpha"}, ["gamma", "beta"], ["alpha"]),
    ({"search_backend": "", "extract_backend": None, "backend": "ddgs"}, ["ddgs"], ["alpha"]),
    ({"search_backend": " Alpha ", "backend": "beta"}, ["alpha", "beta"], []),
])
def test_row_active_iff_it_serves_a_capability(web, active, inactive):
    config = {"web": web}
    assert [b for b in active if not _is_provider_active(_row(b), config)] == []
    assert [b for b in inactive if _is_provider_active(_row(b), config)] == []


@pytest.mark.parametrize("available,status", [(False, "needs_auth"), (True, "ready")])
def test_keyless_row_readiness_follows_registry_availability(monkeypatch, available, status):
    """No-key rows must not read "ready" vacuously (#132526): readiness follows the registry provider."""
    from hermes_cli.tools_config_providers import _web_registry_readiness

    provider = types.SimpleNamespace(is_available=lambda: available)
    monkeypatch.setattr("agent.web_search_registry.get_provider", lambda name: provider)
    assert _web_registry_readiness(_row("example")) == status


def test_unregistered_row_backend_reads_ready(monkeypatch):
    from hermes_cli.tools_config_providers import _web_registry_readiness

    monkeypatch.setattr("agent.web_search_registry.get_provider", lambda name: None)
    assert _web_registry_readiness(_row("example")) == "ready"
