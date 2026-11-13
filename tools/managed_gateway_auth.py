"""Nous bearer for the hosted connector gateway: token reads and first-party URL trust."""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_DEFAULT_CONNECTOR_GATEWAY_ORIGIN = "https://connector-gateway.nousresearch.com"
_NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 120


def _clean(value: object) -> Optional[str]:
    """*value* stripped when it is a non-blank string, else None."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _read_nous_provider_state() -> Optional[dict]:
    """The profile's Nous state, or None. A free-tier identity counts only while guests are allowed:
    with ``nous.guest: false`` it is invisible here, so no cached or refreshed token of it is ever
    attached to a request. Resolves through the same profile-then-global-root fallback every other
    credential reader uses."""
    try:
        from hermes_cli.auth import get_provider_auth_state

        nous_provider = get_provider_auth_state("nous")
        if not isinstance(nous_provider, dict):
            return None
        from hermes_cli.anon_auth import guest_allowed, is_guest_state

        if is_guest_state(nous_provider) and not guest_allowed():
            return None
        return nous_provider
    except Exception:
        return None


def peek_nous_access_token() -> Optional[str]:
    """Cheap token probe: cached auth-store token, no expiry check and no network — availability
    scans must stay off the synchronous OAuth refresh path (:func:`read_nous_access_token`)."""
    from hermes_cli.anon_auth import held_connectors_token

    return _clean(held_connectors_token(_read_nous_provider_state()))


def read_nous_access_token() -> Optional[str]:
    """Read a Nous OAuth access token from the auth store, refreshing it when it is about to expire.

    A read: with no Nous identity there is no bearer and the answer is None. A retired free-tier
    credential IS replaced here, once: that is the explicit dead-credential rule, shared with inference.
    """
    nous_provider = _read_nous_provider_state() or {}
    if not nous_provider:
        return None
    from hermes_cli.anon_auth import held_connectors_token

    if fresh_token := _clean(held_connectors_token(nous_provider, skew_seconds=_NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS)):
        return fresh_token
    cached_token = peek_nous_access_token()
    try:
        from hermes_cli.auth import resolve_nous_access_token

        if refreshed_token := _clean(resolve_nous_access_token(refresh_skew_seconds=_NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS)):
            return refreshed_token
    except Exception as exc:
        from hermes_cli.anon_auth import AnonCredentialDead

        if isinstance(exc, AnonCredentialDead):
            return _replace_dead_guest_token(nous_provider, str(exc.code or "anon_credential_dead"))
        logger.debug("Nous access token refresh failed: %s", exc)
    return cached_token


def _replace_dead_guest_token(dead_state: dict, code: str = "anon_credential_dead") -> Optional[str]:
    from hermes_cli.anon_auth import ANON_ACCOUNT_LOCKED, clear_dead_guest, ensure_portal_identity
    from hermes_cli.auth import resolve_nous_access_token

    clear_dead_guest(code, dead_token=dead_state.get("anon_token"))
    if code == ANON_ACCOUNT_LOCKED:
        return None
    try:
        if ensure_portal_identity(explicit=True) is None:
            return None
        return _clean(resolve_nous_access_token(refresh_skew_seconds=_NOUS_ACCESS_TOKEN_REFRESH_SKEW_SECONDS))
    except Exception as exc:
        logger.debug("Nous free tier replacement after a retired credential failed: %s", exc)
        return None


def connector_gateway_origin() -> str:
    """Connector deployment origin; honors CONNECTOR_GATEWAY_URL."""
    return os.getenv("CONNECTOR_GATEWAY_URL", "").strip().rstrip("/") or _DEFAULT_CONNECTOR_GATEWAY_ORIGIN


def is_connector_gateway_url(url: object, origin_builder: Optional[Callable[[], str]] = None) -> bool:
    """True when ``url`` is on the connector gateway origin, compared as an exact ``(scheme, netloc)``
    pair — never as a name or a domain suffix — so look-alike hosts and an ``http`` downgrade stay
    outside. Anything granting a URL our bearer must gate on this."""
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        expected = urlsplit((origin_builder or connector_gateway_origin)())[:2]
        actual = urlsplit(url.strip())
    except ValueError:
        return False
    return bool(actual.scheme) and (actual.scheme, actual.netloc) == expected


def managed_gateway_auth_headers(
    url: object,
    origin_builder: Optional[Callable[[], str]] = None,
    token_reader: Optional[Callable[[], Optional[str]]] = None,
) -> dict:
    """Live auth headers for a connector gateway URL, or ``{}`` for any other URL or without a token.

    Read fresh on every call: a Nous access token expires within the hour, and a long session would
    otherwise keep presenting a dead bearer."""
    if not is_connector_gateway_url(url, origin_builder):
        return {}
    try:
        token = (token_reader or read_nous_access_token)()
    except Exception as exc:  # pragma: no cover — defensive
        logger.debug("Connector gateway token read failed for %s: %s", url, exc)
        return {}
    if not isinstance(token, str) or not token.strip():
        return {}

    from tools.managed_gateway_identity import user_agent

    return {"Authorization": f"Bearer {token.strip()}", "User-Agent": user_agent()}
