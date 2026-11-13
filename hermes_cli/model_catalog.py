"""Refresh cadence of the live provider model lists behind the ``/model`` picker.

The curated model lists ship with the code (``hermes_cli.models``); nothing here fetches a
remote catalog manifest.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TTL_MINUTES = 20


def _ttl_minutes() -> float:
    """``model_catalog.ttl_minutes`` (legacy ``ttl_hours`` honoured while the minutes stay default)."""
    try:
        from hermes_cli.config import load_config
        raw = (load_config() or {}).get("model_catalog")
    except Exception:
        raw = None
    raw = raw if isinstance(raw, dict) else {}
    try:
        minutes = float(raw.get("ttl_minutes") or DEFAULT_TTL_MINUTES)
    except (TypeError, ValueError):
        minutes = DEFAULT_TTL_MINUTES
    if minutes == DEFAULT_TTL_MINUTES and raw.get("ttl_hours"):
        try:
            minutes = float(raw["ttl_hours"]) * 60.0
        except (TypeError, ValueError):
            pass
    return minutes if minutes > 0 else DEFAULT_TTL_MINUTES


def refresh_interval_seconds() -> float:
    """The live provider lists' TTL in seconds (the gateway poll cadence)."""
    return max(60.0, _ttl_minutes() * 60.0)


def refresh_catalogs() -> bool:
    """Force-refresh the live provider lists the picker reads (OpenRouter, and the Nous Portal
    recommendations for a Nous account), writing each disk cache so the next ``/model`` open in
    ANY process sees them. Blocking; run it off the event loop."""
    try:
        from agent.secret_scope import get_secret
        from hermes_cli.anon_auth import current_nous_state, is_guest_state
        from hermes_cli.auth import read_credential_pool
        from hermes_cli.models import _resolve_nous_portal_url, fetch_nous_recommended_models, fetch_openrouter_models

        fetch_openrouter_models(force_refresh=True)
        logins = [current_nous_state(), *read_credential_pool("nous")]
        if any(e and not is_guest_state(e) for e in logins) or get_secret("NOUS_API_KEY"):
            fetch_nous_recommended_models(_resolve_nous_portal_url(), force_refresh=True)
    except Exception:
        logger.debug("provider catalog refresh failed", exc_info=True)
        return False
    return True


def seed_cache_from_checkout(project_root: Path | str) -> bool:
    """Kept for updaters that call it from the new tree after the checkout swap: the curated
    lists ship with the code, so there is no catalog cache to seed."""
    return False
