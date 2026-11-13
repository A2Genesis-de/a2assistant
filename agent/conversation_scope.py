"""Ambient conversation and affinity scope for provider routing and attribution.

The agent loop publishes the session-lineage root id at turn entry; providers with sticky
routing (OpenRouter ``session_id``, xAI ``x-grok-conv-id``, OpenCode affinity) read it here.
A host that mints one physical session per response publishes its declared conversation
scope as the affinity scope; unset means consumers fall back to the conversation id.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_conversation_id: ContextVar[Optional[str]] = ContextVar("hermes_conversation_id", default=None)
_affinity_scope: ContextVar[Optional[str]] = ContextVar("hermes_affinity_scope", default=None)


def _reset_var(var: ContextVar, token) -> None:
    try:
        var.reset(token)
    except Exception:
        var.set(None)


def set_affinity_scope(scope: Optional[str]):
    return _affinity_scope.set(scope or None)


def reset_affinity_scope(token) -> None:
    _reset_var(_affinity_scope, token)


def get_affinity_scope() -> Optional[str]:
    return _affinity_scope.get()


def set_conversation_context(conversation_id: Optional[str]):
    return _conversation_id.set(conversation_id or None)


def reset_conversation_context(token) -> None:
    _reset_var(_conversation_id, token)


def get_conversation_context() -> Optional[str]:
    return _conversation_id.get()
