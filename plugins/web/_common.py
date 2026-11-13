"""Shared plumbing for the bundled web-search provider plugins."""

from __future__ import annotations

from typing import Any

from agent.web_search_provider import WebSearchProvider


def provider_env(name: str) -> str:
    """Config-aware env lookup (os.environ, then ~/.hermes/.env)."""
    from agent.web_search_provider import get_provider_env
    return get_provider_env(name)


def search_ok(web_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"success": True, "data": {"web": web_results}}


def search_fail(error: str) -> dict[str, Any]:
    return {"success": False, "error": error}


def title_hit(title: str, url: str, description: str, position: int) -> dict[str, Any]:
    """Title-first search row; key order is part of the contract (it reaches the model as JSON)."""
    return {"title": title, "url": url, "description": description, "position": position}


class BaseWebSearchProvider(WebSearchProvider):
    """Subclasses set ``NAME`` / ``DISPLAY_NAME`` / ``KEY_ENV`` and flip ``EXTRACT``."""

    NAME: str = ""
    DISPLAY_NAME: str = ""
    KEY_ENV: str = ""
    EXTRACT: bool = False

    name = property(lambda self: self.NAME)
    display_name = property(lambda self: self.DISPLAY_NAME)

    def is_available(self) -> bool:
        return bool(provider_env(self.KEY_ENV))

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return self.EXTRACT


def setup_schema(name: str, badge: str, tag: str, key_env: str = "", prompt: str = "", url: str = "", **extra: Any) -> dict[str, Any]:
    """``hermes tools`` picker entry; ``env_vars`` is empty when ``key_env`` is blank."""
    env_vars = [{"key": key_env, "prompt": prompt, "url": url}] if key_env else []
    return {"name": name, "badge": badge, "tag": tag, "env_vars": env_vars, **extra}
