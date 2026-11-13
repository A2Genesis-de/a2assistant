"""``/branch`` destination on thread-capable platforms (#66023).

On Telegram a plain ``/branch`` opens a NEW sibling thread for the
clone and leaves the current chat bound to the original session, so the user can keep both paths
alive. ``/branch --here`` keeps the legacy in-place switch; platforms without threads (and the CLI)
always branch in place. Pure helpers only — the handler lives in ``slash_commands_session.py``.
"""

from __future__ import annotations

import dataclasses
from typing import Optional

from gateway.config import Platform
from gateway.session import SessionSource

# Adapters that override ``BasePlatformAdapter.create_handoff_thread`` (the base returns None).
BRANCH_THREAD_PLATFORMS = frozenset({Platform.TELEGRAM})
BRANCH_HERE_FLAG = "--here"


def parse_branch_args(raw: str) -> tuple[bool, str]:
    """``(stay_here, title)`` from the text after ``/branch``.

    Only a leading ``--here`` is a flag; everything else is the optional title. The CLI strips the
    flag through the same parser so ``/branch --here` never becomes a session titled ``--here``.
    """
    text = (raw or "").strip()
    head, _, rest = text.partition(" ")
    if head.lower() == BRANCH_HERE_FLAG:
        return True, rest.strip()
    return False, text


def branch_thread_parent(source: SessionSource) -> Optional[str]:
    """Chat that can host a sibling thread for *source*, or None when nothing can."""
    if source.platform not in BRANCH_THREAD_PLATFORMS:
        return None
    return str(source.chat_id) if source.chat_id else None


def branch_dest_source(source: SessionSource, *, parent_id: str, thread_id: str, title: str) -> SessionSource:
    """The ``SessionSource`` a follow-up typed in the new thread will arrive on — the shape must
    match the adapter's inbound source or the clone is bound to a key nobody ever reads (the
    CLI→platform handoff in ``run_startup.py::_handoff_resolve_destination`` mirrors the same
    rules). Per-message fields are dropped; identity/scope fields travel with the copy. Telegram
    (``group:<chat>:<topic>``, private-chat topics stay ``dm``) keys a thread reply on the PARENT
    chat's type."""
    common = dict(thread_id=str(thread_id), message_id=None, prospective_thread_id=None,
                  auto_thread_created=False, auto_thread_initial_name=None)
    chat_type = "group" if source.chat_type == "thread" else source.chat_type
    return dataclasses.replace(source, chat_id=str(parent_id), chat_type=chat_type, **common)


def format_thread_ref(platform: Optional[Platform], thread_id: str) -> str:
    """Pointer to a thread for user-facing text."""
    return f"`{thread_id}`"
