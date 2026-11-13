"""Availability gate and session keys for connector tools."""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

__all__ = [
    "MAX_CALLS_PER_DISPATCH",
    "connectors_available",
    "operation_session_key",
]

# Context cap, not a wire limit; the gateway batch cap is deliberately unreachable.
MAX_CALLS_PER_DISPATCH = 10

def connectors_available(*_args, **_kwargs) -> bool:
    """Hosted connector accounts need a Nous identity, which A2Assistant does not use: the hosted
    surface is always off. Local MCP servers do not go through this gate."""
    return False


def operation_session_key(session_id: Optional[str]) -> str:
    """The key an operation is registered under: the gateway session key the RPCs look up by
    (``HERMES_SESSION_KEY``), falling back to the agent's session id where no gateway bound one.
    The agent id alone is wrong on the desktop: compaction rotates it mid-turn while the gateway
    key stays, and a card keyed by the old id can no longer be driven."""
    from gateway.session_context import get_session_env

    return get_session_env("HERMES_SESSION_KEY", "") or str(session_id or "")


def session_platform() -> str:
    from gateway.session_context import get_session_env

    platform = get_session_env("HERMES_SESSION_PLATFORM", "") or get_session_env("HERMES_SESSION_SOURCE", "")
    return str(platform or "").strip().lower()
