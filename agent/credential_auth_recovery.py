"""Credential-pool recovery for an auth failure (401/403) on the dispatched credential.

The entry that supplied the failing key is refreshed; same-entry refreshes are capped so a
single-entry pool falls through to fallback. An entitlement 403 fails fast.
"""

from __future__ import annotations

import time
from typing import Any, Optional

_MAX_AUTH_REFRESH_ATTEMPTS = 2
_EPISODE_IDLE_S = 120.0


def _ra():
    import run_agent
    return run_agent


def _episode(agent: Any, provider: str, entry_id: Optional[str]) -> dict[str, Any]:
    """Per-turn auth-failure state for one pool entry (the turn loop resets the map)."""
    if getattr(agent, "_auth_pool_refresh_counts", None) is None:
        agent._auth_pool_refresh_counts = {}
    now = time.monotonic()
    episode = agent._auth_pool_refresh_counts.get((provider, entry_id))
    if episode is None or now - episode["last"] > _EPISODE_IDLE_S:
        episode = agent._auth_pool_refresh_counts[(provider, entry_id)] = {"refreshes": 0, "waits": 0}
    episode["last"] = now
    return episode


def recover_auth_failure(agent, pool, *, status_code, has_retried_429, error_context, api_key_hint,
                         credential_id, rotate_and_swap):
    from agent.agent_runtime_helpers import _is_entitlement_403
    log = _ra().logger
    if _is_entitlement_403(agent, status_code, error_context):
        log.info(
            "Credential %s — entitlement-shaped 403 from %s; "
            "skipping pool refresh (account lacks subscription, "
            "not a transient auth failure).", status_code if status_code is not None else "auth",
            agent.provider or "provider",
        )
        return False, has_retried_429
    provider = agent.provider
    # Refresh the entry that supplied the failing key, not current(): refreshing a healthy entry
    # burns its single-use refresh token for a failure it never had.
    refresh_kwargs = {"api_key_hint": api_key_hint}
    if credential_id:
        refresh_kwargs["credential_id"] = credential_id
    refreshed = pool.try_refresh_matching(**refresh_kwargs)
    if refreshed is None:
        # Refresh failed; rotate (the failed entry is already marked exhausted).
        return (True, False) if rotate_and_swap(401, "auth refresh failed") else (False, has_retried_429)
    refreshed_id = getattr(refreshed, "id", None)
    if refreshed_id is not None:
        # try_refresh_matching() reports success even when upstream keeps rejecting; cap same-entry
        # refreshes so a single-entry pool falls through to fallback.
        state = _episode(agent, provider, refreshed_id)
        state["refreshes"] += 1
        if state["refreshes"] > _MAX_AUTH_REFRESH_ATTEMPTS:
            log.warning(
                "Credential auth failure persists after %s refreshes for "
                "pool entry %s — treating as unrecoverable and allowing "
                "fallback to activate.", state["refreshes"] - 1, refreshed_id,
            )
            return False, has_retried_429
    log.info("Credential auth failure — refreshed pool entry %s", refreshed_id or "?")
    if agent._swap_credential(refreshed) is False:
        return False, has_retried_429
    return True, has_retried_429
