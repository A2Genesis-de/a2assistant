"""A per-capability web backend key must not reroute the other capability.

Regression for #113017: a lone ``web.extract_backend`` (with no ``web.backend``) must leave
``_get_search_backend()`` on the autodetected backend, even though ``selection_exists("web")``
counts per-capability keys as a stored selection.
"""
from __future__ import annotations


def _ladder_env(monkeypatch, raw_web):
    from tools import web_tools
    from tools import tool_backend_helpers as helpers

    monkeypatch.setattr(web_tools, "_load_web_config", lambda: dict(raw_web))
    monkeypatch.setattr(
        helpers, "_raw_section",
        lambda section: dict(raw_web) if section == "web" else None,
    )
    monkeypatch.setattr(web_tools, "_ddgs_package_importable", lambda: True)


def test_extract_only_config_does_not_reroute_search(monkeypatch):
    from tools import web_tools

    _ladder_env(monkeypatch, {"extract_backend": "example-extract"})
    assert web_tools._get_search_backend() == "ddgs"
    assert web_tools._get_extract_backend() == "example-extract"


def test_search_only_config_does_not_reroute_extract(monkeypatch):
    from tools import web_tools

    _ladder_env(monkeypatch, {"search_backend": "example-search"})
    assert web_tools._get_search_backend() == "example-search"
    assert web_tools._get_extract_backend() == "ddgs"
