"""Channel directory -- cached map of reachable channels/contacts per platform.

Built on gateway startup, refreshed every 5 min, saved to ``<HERMES_HOME>/channel_directory.json``.
send_message reads it for action="list" and to resolve friendly channel names to IDs.
"""

import asyncio
import contextlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from hermes_cli.config import get_hermes_home
from utils import atomic_json_write

logger = logging.getLogger(__name__)

# Paths resolve lazily: a multiplexed gateway serves several profile homes from one
# process, so an import-time constant would pin every profile to whichever home imported
# first. These globals are explicit overrides (tests patch them); None = current home.
DIRECTORY_PATH: Optional[Path] = None
# User-maintained friendly-name overlay {"<platform>": {"<chat_id>": "<friendly name>"}},
# re-applied on every build AND load (hand-edits to the regenerated
# channel_directory.json don't survive); also lets a chat be pre-named before first traffic.
CHANNEL_ALIASES_PATH: Optional[Path] = None

# Platforms whose historical session origins must never become send targets.
_SKIP_SESSION_DISCOVERY = frozenset({"local", "api_server", "webhook"})


def _directory_path() -> Path:
    return DIRECTORY_PATH or get_hermes_home() / "channel_directory.json"


def _aliases_path() -> Path:
    return CHANNEL_ALIASES_PATH or get_hermes_home() / "channel_aliases.json"


def _read_json(path: Path) -> Any:
    # utf-8-sig: Windows editors may leave a BOM that plain utf-8 json.load rejects (pm-era fix).
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _load_json_dict(path: Path) -> dict[str, Any]:
    """Read a JSON object from *path*; {} when missing, unreadable, or not a dict."""
    if not path.exists():
        return {}
    try:
        data = _read_json(path)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _apply_channel_aliases(platforms: dict[str, Any]) -> None:
    """Overlay friendly names onto directory entries by chat_id, in place.

    An aliased id not yet discovered gets a placeholder entry so a freshly-created
    group is addressable by name before its first message.
    """
    for plat_name, id_map in _load_json_dict(_aliases_path()).items():
        if not isinstance(id_map, dict):
            continue
        entries = platforms.setdefault(plat_name, [])
        if not isinstance(entries, list):
            continue
        for chat_id, friendly in id_map.items():
            if not isinstance(friendly, str) or not friendly.strip():
                continue
            chat_id, friendly = str(chat_id), friendly.strip()
            matches = [e for e in entries if isinstance(e, dict) and e.get("id") == chat_id]
            for e in matches:
                e["name"] = friendly
            if not matches:
                entries.append({"id": chat_id, "name": friendly, "thread_id": None,
                                "type": "group" if chat_id.endswith("@g.us") else "dm"})


def _normalize_channel_query(value: str) -> str:
    return value.lstrip("#").strip().lower()


def _channel_target_name(platform_name: str, channel: dict[str, Any]) -> str:
    """Human-facing target label for a channel entry."""
    name = channel["name"]
    return f"{name} ({channel['type']})" if channel.get("type") else name


def _session_entry_id(origin: dict[str, Any]) -> Optional[str]:
    chat_id = origin.get("chat_id")
    if not chat_id:
        return None
    return f"{chat_id}:{thread_id}" if (thread_id := origin.get("thread_id")) else str(chat_id)


def _session_entry_name(origin: dict[str, Any]) -> str:
    base_name = origin.get("chat_name") or origin.get("user_name") or str(origin.get("chat_id"))
    if not (thread_id := origin.get("thread_id")):
        return base_name
    return f"{base_name} / {origin.get('chat_topic') or f'topic {thread_id}'}"


# --- Build / refresh -------------------------------------------------------

async def build_channel_directory(adapters: dict[Any, Any]) -> dict[str, Any]:
    """Build the directory from connected adapters + session data and persist it."""
    from gateway.config import Platform
    platforms: dict[str, list[dict[str, str]]] = {}
    for platform, adapter in adapters.items():
        try:
            list_channels = getattr(adapter, "list_channels", None)
            if callable(list_channels):
                platform_channels = await list_channels()
                if platform_channels is not None:
                    platforms[platform.value] = _normalize_adapter_channels(platform_channels)
        except Exception as e:
            logger.warning("Channel directory: failed to build %s: %s", platform.value, e)
    # Platforms without channel enumeration get session-based discovery, but only when
    # connected in THIS gateway process: origins for disabled or decommissioned
    # platforms must not resurface as stale send targets.
    adapter_platform_names = {getattr(p, "value", str(p)) for p in adapters}
    async def _discover(plat_name: str) -> None:
        if plat_name in _SKIP_SESSION_DISCOVERY or plat_name in platforms or plat_name not in adapter_platform_names:
            return
        platforms[plat_name] = await asyncio.to_thread(_build_from_sessions, plat_name)
    for plat in Platform:
        await _discover(plat.value)
    # Plugin platforms are dynamic enum members missing from Platform.__members__. Only connected
    # adapters are discovered, so loaded entries suffice (never import an unused adapter here).
    with contextlib.suppress(Exception):
        from gateway.platform_registry import platform_registry
        for entry in platform_registry.loaded_entries():
            await _discover(entry.name)
    _merge_configured_channels(adapters, platforms)
    _apply_channel_aliases(platforms)
    directory = {"updated_at": datetime.now().isoformat(), "platforms": platforms}
    try:
        await asyncio.to_thread(atomic_json_write, _directory_path(), directory)
    except Exception as e:
        logger.warning("Channel directory: failed to write: %s", e)
    return directory


def _merge_configured_channels(adapters: dict[Any, Any], platforms: dict[str, list[dict[str, Any]]]) -> None:
    """Add the targets an adapter's own config declares (``configured_channels()``, e.g. Telegram
    ``extra.dm_topics``) after discovery: session history alone drops them once their sessions are
    pruned (#52629). Discovered entries win on an id collision; label clashes are id-qualified."""
    for platform, adapter in adapters.items():
        configured = getattr(adapter, "configured_channels", None)
        if not callable(configured):
            continue
        try:
            entries = _normalize_adapter_channels(configured())
        except Exception as e:
            logger.warning("Channel directory: configured channels for %s failed: %s", platform.value, e, exc_info=True)
            continue
        known = platforms.setdefault(platform.value, [])
        seen = {entry.get("id") for entry in known}
        added = [entry for entry in entries if entry["id"] not in seen]
        known.extend(added)
        _qualify_label_clashes(platform.value, known, {id(entry) for entry in added})


def _qualify_label_clashes(platform_name: str, entries: list[dict[str, Any]], added: set[int]) -> None:
    """Prefix the id onto every entry whose label resolves (``resolve_channel_name`` step 1) like a
    different target's, when one of them is a just-merged configured entry: the bare name then
    resolves to nothing rather than to whichever chat was listed first. Discovered-only clashes keep
    their labels."""
    by_key: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        labels = {_normalize_channel_query(entry["name"]), _normalize_channel_query(_channel_target_name(platform_name, entry))}
        for key in labels:
            by_key.setdefault(key, []).append(entry)
    clashing = {id(e): e for group in by_key.values()
                if len({e["id"] for e in group}) > 1 and any(id(e) in added for e in group) for e in group}
    for entry in clashing.values():
        entry["name"] = f"{entry['id']} / {entry['name']}"


def _normalize_adapter_channels(raw_channels: Any) -> list[dict[str, Any]]:
    """Validate and dedupe entries returned by an adapter's ``list_channels()`` hook."""
    channels: list[dict[str, Any]] = []
    seen_ids = set()
    for raw in raw_channels if isinstance(raw_channels, list) else ():
        if not isinstance(raw, dict):
            continue
        channel_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or channel_id).strip()
        if not channel_id or not name or channel_id in seen_ids:
            continue
        entry: dict[str, Any] = {"id": channel_id, "name": name, "type": str(raw.get("type") or "dm")}
        entry.update({key: str(raw[key]) for key in ("thread_id", "guild") if raw.get(key)})
        channels.append(entry)
        seen_ids.add(channel_id)
    return channels


def _build_from_sessions(platform_name: str) -> list[dict[str, str]]:
    """Known channels/contacts from session origins: state.db first, sessions.json fallback (pre-migration).

    state.db is the primary source (#9006): gateway session rows persist origin_json.
    """
    return _build_from_sessions_db(platform_name) or _build_from_sessions_json(platform_name)


def _entries_from_origins(platform_name: str, source: str, origins_fn) -> list[dict[str, Any]]:
    """Deduped entries for the (origin, chat_type) pairs from ``origins_fn()``; a mid-iteration
    failure keeps entries read so far."""
    entries: list[dict[str, Any]] = []
    try:
        seen_ids = set()
        for origin, chat_type in origins_fn():
            entry_id = _session_entry_id(origin)
            if not entry_id or entry_id in seen_ids:
                continue
            seen_ids.add(entry_id)
            entries.append({
                "id": entry_id, "name": _session_entry_name(origin),
                "type": chat_type, "thread_id": origin.get("thread_id"),
            })
    except Exception as e:
        logger.debug("Channel directory: %s for %s: %s", source, platform_name, e)
    return entries


def _build_from_sessions_db(platform_name: str) -> list[dict[str, str]]:
    """Pull channels/contacts from state.db gateway session rows."""
    def _origins() -> Iterable[tuple[dict[str, Any], Any]]:
        from hermes_state_registry import acquire, release_or_close
        db = acquire()
        try:
            lister = getattr(db, "list_gateway_sessions", None)
            if not callable(lister):
                return
            rows = lister(platform=platform_name, active_only=False)
        finally:
            release_or_close(db)
        for row in rows:
            origin = None
            with contextlib.suppress(TypeError, ValueError):
                origin = json.loads(row["origin_json"]) if row.get("origin_json") else None
            if not isinstance(origin, dict) or not origin:
                origin = {"chat_id": row.get("chat_id"), "thread_id": row.get("thread_id"), "chat_name": row.get("display_name")}
            yield origin, row.get("chat_type") or "dm"
    return _entries_from_origins(platform_name, "state.db session read failed", _origins)


def _build_from_sessions_json(platform_name: str) -> list[dict[str, str]]:
    """Legacy fallback: pull channels/contacts from sessions.json origin data."""
    sessions_path = get_hermes_home() / "sessions" / "sessions.json"
    if not sessions_path.exists():
        return []
    def _origins() -> Iterable[tuple[dict[str, Any], Any]]:
        for _key, session in _read_json(sessions_path).items():
            # Keys starting with "_" (e.g. the gateway's "_README") are metadata sentinels.
            if str(_key).startswith("_") or not isinstance(session, dict):
                continue
            origin = session.get("origin") or {}
            if origin.get("platform") == platform_name:
                yield origin, session.get("chat_type", "dm")
    return _entries_from_origins(platform_name, "failed to read sessions", _origins)


# --- Read / resolve --------------------------------------------------------

def load_directory() -> dict[str, Any]:
    """Load the cached directory from disk, with aliases re-applied on read."""
    directory_path = _directory_path()
    if directory_path.exists():
        with contextlib.suppress(Exception):
            data = _read_json(directory_path)
            # Aliases apply on read too, so new names take effect between timed rebuilds.
            _apply_channel_aliases(data.setdefault("platforms", {}))
            return data
    base = {"updated_at": None, "platforms": {}}
    _apply_channel_aliases(base["platforms"])
    return base


def lookup_channel_type(platform_name: str, chat_id: str) -> Optional[str]:
    """Channel ``type`` string (e.g. ``"channel"``, ``"forum"``) for *chat_id*, or None if unknown."""
    channels = load_directory().get("platforms", {}).get(platform_name, [])
    return next((ch.get("type") for ch in channels if ch.get("id") == chat_id), None)


def resolve_channel_name(platform_name: str, name: str) -> Optional[str]:
    """Resolve a friendly channel name (e.g. "bot-home", "#bot-home", "GuildName/bot-home")
    to an ID; case-insensitive, first match wins."""
    channels = load_directory().get("platforms", {}).get(platform_name, [])
    if not channels:
        return None
    # 0. Exact ID match — case-sensitive, no normalization, so raw platform IDs work even when
    # _parse_target_ref's format guard didn't recognize them.
    raw = name.strip()
    for ch in channels:
        if ch.get("id") == raw:
            return ch["id"]
    query = _normalize_channel_query(name)
    # 1. Exact name match, including the display labels shown by send_message(action="list")
    for ch in channels:
        if query in (_normalize_channel_query(ch["name"]), _normalize_channel_query(_channel_target_name(platform_name, ch))):
            return ch["id"]
    # 2. Guild-qualified match ("GuildName/channel")
    if "/" in query:
        guild_part, ch_part = query.rsplit("/", 1)
        for ch in channels:
            guild = ch.get("guild", "").strip().lower()
            if guild == guild_part and _normalize_channel_query(ch["name"]) == ch_part:
                return ch["id"]
    # 3. Partial prefix match (only if unambiguous)
    matches = [ch for ch in channels if _normalize_channel_query(ch["name"]).startswith(query)]
    return matches[0]["id"] if len(matches) == 1 else None


def format_directory_for_display(platforms: Optional[dict[str, Any]] = None) -> str:
    """Format the channel directory as a human-readable list for the model.

    ``platforms`` overrides the on-disk directory (``hermes send --list`` merges in
    configured-but-undiscovered platforms); an empty channel list renders a "(no channels
    discovered yet)" hint because the platform is still a valid send target.
    """
    if platforms is None:
        platforms = load_directory().get("platforms", {})
    if not platforms:
        return "No messaging platforms connected or no channels discovered yet."
    lines = ["Available messaging targets:\n"]
    for plat_name, channels in sorted(platforms.items()):
        if not channels:
            lines.append(f"{plat_name.title()}:")
            lines.append(
                f"  (no channels discovered yet — send directly with "
                f"{plat_name}:<chat_id>, or bare '{plat_name}' for the home channel)"
            )
        else:
            lines.append(f"{plat_name.title()}:")
            lines.extend(f"  {plat_name}:{_channel_target_name(plat_name, ch)}" for ch in channels)
        lines.append("")
    lines.append('Use these as the "target" parameter when sending.')
    lines.append('Bare platform name (e.g. "telegram") sends to home channel.')
    return "\n".join(lines)
