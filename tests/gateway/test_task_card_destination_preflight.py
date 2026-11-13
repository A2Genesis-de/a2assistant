"""Destination eligibility must precede transport failure and its text fallback."""

import queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gateway.config import PlatformConfig
from gateway.run_turn_runner import TurnRunner
from plugins.platforms.slack.adapter import SlackAdapter


def make_adapter(monkeypatch):
    adapter = SlackAdapter(PlatformConfig(extra={"reply_in_thread": False}))
    client = SimpleNamespace(
        api_call=AsyncMock(side_effect=lambda *a, **kw: {"ts": "900.1"}),
        chat_postMessage=AsyncMock(return_value={"ts": "900.2"}),
        chat_update=AsyncMock(return_value={"ts": "900.2"}),
    )
    monkeypatch.setattr(adapter, "_get_client", Mock(return_value=client))
    adapter._app = None
    return adapter, client


async def run_progress(adapter, metadata, reply_to, after_first=None):
    class Events(queue.Queue):
        def get_nowait(self):
            event = super().get_nowait()
            if event["type"] == "tool.completed" and after_first:
                after_first()
            return event

    events = Events()
    for event_type in ("tool.started", "tool.completed", "tool.completed"):
        events.put({"type": event_type, "tool_call_id": "call-1", "tool_name": "terminal"})
    ctx = SimpleNamespace(
        source=SimpleNamespace(chat_id="D1"), _progress_reply_to=reply_to,
        _progress_metadata=metadata, _cleanup_progress=False, progress_queue=events,
        tool_progress_enabled=False,  # Slack tier default: no text lane was asked for
        _run_still_current=lambda: not events.empty(), agent_holder=[None],
    )
    await TurnRunner(None, ctx)._send_native_task_card_progress(adapter)


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata,reply_to,eligible", [
    ({}, None, False),
    ({"thread_id": "100.1"}, "100.1", False),
    ({"thread_id": "100.1"}, "100.2", True),
    ({"thread_ts": "100.1"}, None, True),
])
async def test_destination_preflight_survives_transport_recovery(
    monkeypatch, metadata, reply_to, eligible,
):
    adapter, io = make_adapter(monkeypatch)
    original_metadata = dict(metadata)
    stop = AsyncMock(wraps=adapter.stop_native_task_card_progress)
    monkeypatch.setattr(adapter, "stop_native_task_card_progress", stop)

    await run_progress(adapter, metadata, reply_to, lambda: setattr(adapter, "_app", object()))

    stop.assert_awaited_once_with("D1", reply_to=reply_to, metadata=metadata)
    assert metadata == original_metadata
    assert bool(io.chat_postMessage.await_count) is eligible
    assert bool(io.chat_update.await_count) is eligible
    io.api_call.assert_not_awaited()  # Disconnected first attempt stays on fallback.

    # Suppression belongs to this turn, not the adapter: the same chat can host
    # a later real thread, which still gets native publication and finalization.
    if not eligible:
        await run_progress(adapter, {"thread_id": "200.1"}, "200.2")
        methods = [call.args[0] for call in io.api_call.await_args_list]
        assert methods == ["chat.startStream", "chat.appendStream", "chat.appendStream",
                           "chat.appendStream", "chat.stopStream"]
        assert not adapter._native_task_card_streams


