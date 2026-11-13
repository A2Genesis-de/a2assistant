"""Browser provider registry: cloud browser backends registered by plugins via
:meth:`PluginContext.register_browser_provider`, consumed by ``tools.browser_config.get_cloud_provider``,
which resolves only the provider named by ``browser.cloud_provider`` (no auto-detect)."""

from __future__ import annotations

import logging

from agent.browser_provider import BrowserProvider
from agent.provider_registry import ProviderRegistry

logger = logging.getLogger(__name__)


_registry: ProviderRegistry[BrowserProvider] = ProviderRegistry(
    label="Browser", provider_cls=BrowserProvider, logger=logger,
)
_registry.export(globals())
