"""Tests for agent.conversation_scope — ambient conversation and affinity scope."""

from __future__ import annotations

import contextvars

from agent.conversation_scope import (
    get_affinity_scope,
    get_conversation_context,
    reset_affinity_scope,
    reset_conversation_context,
    set_affinity_scope,
    set_conversation_context,
)


def test_ambient_context_set_none_clears():
    for empty in (None, ""):
        token = set_conversation_context(empty)
        try:
            assert get_conversation_context() is None
        finally:
            reset_conversation_context(token)


def test_ambient_context_isolated_between_contexts():
    def _in_conversation(cid):
        set_conversation_context(cid)
        return get_conversation_context()

    assert contextvars.copy_context().run(_in_conversation, "agent-a") == "agent-a"
    assert contextvars.copy_context().run(_in_conversation, "agent-b") == "agent-b"
    assert get_conversation_context() is None


def test_ambient_context_propagates_via_thread_context_helper():
    from concurrent.futures import ThreadPoolExecutor

    from tools.thread_context import propagate_context_to_thread

    token = set_conversation_context("root-session")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            seen = pool.submit(propagate_context_to_thread(get_conversation_context)).result()
    finally:
        reset_conversation_context(token)
    assert seen == "root-session"


def test_affinity_scope_round_trip():
    token = set_affinity_scope("declared-scope")
    try:
        assert get_affinity_scope() == "declared-scope"
    finally:
        reset_affinity_scope(token)
    assert get_affinity_scope() is None
