"""Which title stage is allowed to spend a platform rename.

Titling is two-stage: a derived slice of the user's own words lands inline, and
the model's version replaces it a moment later. A local sidebar wants both. A
Telegram topic wants only the second — renaming twice lands on the same name at
twice the cost.
"""

from __future__ import annotations

import types
import weakref

import pytest

from gateway.config import Platform
from gateway.session import SessionSource
from gateway.run import GatewayRunner
from gateway.run_turn_runner import TurnRunner


def _attach(lane):
    """Attach the title callback for *lane* and return (callback, renames)."""
    renames: list = []
    source = types.SimpleNamespace(platform=Platform.TELEGRAM, chat_id="chan-1")

    runner = types.SimpleNamespace(
        _is_telegram_topic_lane=lambda src: lane == "telegram",
        _schedule_telegram_topic_title_rename=(
            lambda src, sid, title: renames.append(title)
        ),
    )
    holder = types.SimpleNamespace(
        _runner=runner,
        _attach_session_title_callback=TurnRunner._attach_session_title_callback,
    )
    agent = types.SimpleNamespace(session_id="sess-1")
    holder._attach_session_title_callback(
        holder, agent, types.SimpleNamespace(source=source, session_key="key-1")
    )
    return agent._on_session_title, renames


@pytest.mark.parametrize("lane", ["telegram"])
def test_the_rename_waits_for_the_model_title(lane):
    callback, renames = _attach(lane)

    callback("fix the flaky auth test in log", "derived")
    assert renames == []

    callback("Fix flaky auth test", "llm")
    assert renames == ["Fix flaky auth test"]


def test_title_thread_copy_preserves_transport_adapter_ref(monkeypatch):
    """Multiplex-routed sources must keep their transport owner for side effects."""
    captured_sources = []

    class Adapter:
        pass

    adapter = Adapter()

    async def noop():
        return None

    def fake_schedule(coro, loop, logger=None, log_message=None):
        coro.close()

    monkeypatch.setattr("gateway.run.safe_schedule_threadsafe", fake_schedule)

    source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="thread-1",
        chat_type="thread",
        thread_id="thread-1",
        profile="runtime-profile",
    )
    source._transport_adapter_ref = weakref.ref(adapter)

    runner = types.SimpleNamespace(
        _gateway_loop=types.SimpleNamespace(is_closed=lambda: False),
        _schedule_rename_from_title_thread=GatewayRunner._schedule_rename_from_title_thread,
    )

    runner._schedule_rename_from_title_thread(
        runner,
        source,
        lambda copied: captured_sources.append(copied) or noop(),
        "Telegram topic rename",
    )

    assert len(captured_sources) == 1
    copied = captured_sources[0]
    assert copied is not source
    assert copied.profile == "runtime-profile"
    assert copied._transport_adapter_ref() is adapter
