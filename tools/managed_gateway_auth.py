"""Hosted connector gateway URL trust. A2Assistant holds no gateway bearer, so no request is authorized."""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_DEFAULT_CONNECTOR_GATEWAY_ORIGIN = "https://connector-gateway.nousresearch.com"


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
    """Auth headers for a connector gateway URL from ``token_reader``, or ``{}`` for any other URL,
    without a reader, or without a token."""
    if token_reader is None or not is_connector_gateway_url(url, origin_builder):
        return {}
    try:
        token = token_reader()
    except Exception as exc:
        logger.debug("Connector gateway token read failed for %s: %s", url, exc)
        return {}
    if not isinstance(token, str) or not token.strip():
        return {}

    from tools.managed_gateway_identity import user_agent

    return {"Authorization": f"Bearer {token.strip()}", "User-Agent": user_agent()}
