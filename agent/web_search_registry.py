"""Web Search Provider Registry.

Populated by plugins via :meth:`PluginContext.register_web_search_provider`;
consumed by the ``web_search`` / ``web_extract`` wrappers in :mod:`tools.web_tools`.

Active selection, in precedence order (the ``supports_search`` /
``supports_extract`` capability filter applies at every step, so a search-only
provider configured as ``web.extract_backend`` falls through):

1. ``web.search_backend`` / ``web.extract_backend``, then ``web.backend``.
2. The single capability-eligible provider that is registered AND available.
3. The preferred bundled provider (``_PREFERENCE``) when it is eligible.
4. ``None`` — the tool points the user at ``hermes tools``.
"""

from __future__ import annotations

import logging
from typing import Optional

from agent.provider_registry import ProviderRegistry, is_available_safe
from agent.web_search_provider import WebSearchProvider

logger = logging.getLogger(__name__)


_registry: ProviderRegistry[WebSearchProvider] = ProviderRegistry(
    label="Web", provider_cls=WebSearchProvider, logger=logger,
)
_registry.export(globals())

_PREFERENCE = ("searxng", "ddgs")


def _read_config_key(*path: str) -> Optional[str]:
    """Resolve a dotted config key from ``config.yaml``. Returns None on miss."""
    try:
        from hermes_cli.config import load_config_readonly

        cur = load_config_readonly()
        for segment in path:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(segment)
        if isinstance(cur, str) and cur.strip():
            return cur.strip()
    except Exception as exc:
        logger.debug("Could not read config %s: %s", ".".join(path), exc)
    return None


def _configured_backend(capability: str) -> Optional[str]:
    """``web.<capability>_backend`` (preferred) or ``web.backend`` (shared fallback)."""
    return _read_config_key("web", f"{capability}_backend") or _read_config_key("web", "backend")


def _resolve(configured: Optional[str], *, capability: str) -> Optional[WebSearchProvider]:
    """Resolve the active provider for a capability ("search" | "extract").

    An explicit, capable config wins even when ``is_available()`` is False, so the
    dispatcher surfaces the provider's precise error instead of silently switching.
    """
    snapshot = _registry.merged()

    def _capable(p: WebSearchProvider) -> bool:
        return bool(
            p.supports_search() if capability == "search"
            else p.supports_extract() if capability == "extract" else False
        )

    def _available(p: WebSearchProvider) -> bool:
        return is_available_safe(p, logger, "provider %s.is_available() raised %s")

    if configured:
        provider = snapshot.get(configured)
        if provider is not None and _capable(provider):
            return provider
        if provider is None:
            logger.debug("web backend '%s' configured but not registered; falling back", configured)
        else:
            logger.debug(
                "web backend '%s' configured but does not support '%s'; falling back", configured, capability
            )

    eligible = [p for p in snapshot.values() if _capable(p) and _available(p)]
    if len(eligible) == 1:
        return eligible[0]

    for preferred in _PREFERENCE:
        provider = snapshot.get(preferred)
        if provider is not None and provider in eligible:
            return provider
    return None


def _disabled_web_plugin_for(configured: Optional[str] = None, *, capability: Optional[str] = None) -> Optional[str]:
    """Plugin key of a *disabled* web plugin that would have provided the configured backend
    (``web.<capability>_backend`` → ``web.backend``), or None.

    Lets the dispatcher say "re-enable web-<vendor>" instead of "No web extract provider
    configured": a disabled provider never registers, so it is resolved from config.yaml.
    Web plugins live under ``web/<vendor>`` with the provider name differing only by
    hyphen/underscore, so both are normalized.
    """
    def _norm(s: str) -> str:
        return s.strip().lower().replace("-", "_")

    if not configured and capability in ("search", "extract"):
        configured = _configured_backend(capability)
    if not configured:
        return None

    want = _norm(configured)
    try:
        from hermes_cli.plugins import get_plugin_manager

        pm = get_plugin_manager()
        for key, loaded in pm._plugins.items():
            if (
                isinstance(key, str) and key.startswith("web/") and not loaded.enabled
                and loaded.error == "disabled via config" and _norm(key.split("/", 1)[1]) == want
            ):
                return key
    except Exception as exc:
        logger.debug("disabled-web-plugin lookup failed: %s", exc)
    return None


def get_active_search_provider() -> Optional[WebSearchProvider]:
    """Resolve the currently-active web search provider."""
    return _resolve(_configured_backend("search"), capability="search")


def get_active_extract_provider() -> Optional[WebSearchProvider]:
    """Resolve the currently-active web extract provider."""
    return _resolve(_configured_backend("extract"), capability="extract")
