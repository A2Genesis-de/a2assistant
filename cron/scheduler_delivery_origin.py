"""Discriminators a cron fire carries from its persisted job origin."""

from __future__ import annotations

from typing import Any


def stamp_origin_discriminators(t: Any, route_metadata: dict, media_metadata: dict) -> None:
    """Stamp an origin target's ``scope_id`` onto a live send's metadata. Fan-out targets get none
    (their recipient is not the origin's author); ``setdefault`` never overrides router or home stamping."""
    scope_id = t.origin.get("scope_id") if t.origin_target else None
    if scope_id:
        route_metadata.setdefault("scope_id", str(scope_id))
        media_metadata.setdefault("scope_id", str(scope_id))
