"""Caller-level fallback suppression — the branches that actually stop the leak.

Review round 3 deleted BOTH production branches these cover and every existing
test still passed (36 and 38 respectively). The suites exercised
`_approval_send_outcome` and `RelayAdapter` but never drove the real callers,
so nothing observed whether a text send followed a decline — which is the
entire security property.

Every case here pairs a DECLINE with an ordinary-FAILURE control. Without the
control a test cannot distinguish "suppressed the fallback" from "never had a
fallback": a caller that always stays silent would pass the decline case.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from gateway.platforms.base import SendResult
from gateway.relay.egress import EGRESS_DECLINE_CODE

CODE_ONLY_DECLINE: dict[str, Any] = {"success": False, "code": EGRESS_DECLINE_CODE}


# ── exec approval ───────────────────────────────────────────────────────────


class _Adapter:
    """Records every plain text send the caller attempts."""

    typed_command_prefix = "/"

    def __init__(self, approval_result: SendResult) -> None:
        self._approval_result = approval_result
        self.text_sends: list[str] = []

    def pause_typing_for_chat(self, chat_id: str) -> None:
        return None

    def resume_typing_for_chat(self, chat_id: str) -> None:
        return None

    async def send_exec_approval(self, *a: Any, **k: Any) -> SendResult:
        return self._approval_result

    async def send(self, chat_id: str, message: str, **k: Any) -> SendResult:
        self.text_sends.append(message)
        return SendResult(success=True, message_id="m1")


def _runner(adapter: _Adapter):
    """A TurnRunner driven through its real _approval_notify_sync."""
    from gateway.run_turn_runner import TurnRunner

    ctx = SimpleNamespace(
        _status_adapter=adapter,
        _status_chat_id="C1",
        _status_thread_metadata={},
        _session_key="sk1",
        session_key="sk1",
        source=SimpleNamespace(chat_id="C1", platform="discord", session_key="sk1"),
    )
    runner = TurnRunner(SimpleNamespace(), ctx)

    class _Fut:
        def __init__(self, result): self._r = result
        def result(self, timeout=None): return self._r

    runner._schedule = lambda coro, _label: _Fut(asyncio.run(coro))
    runner._close_native_stream_boundary = lambda _why: None
    return runner


APPROVAL = {"command": "rm -rf /", "description": "danger", "pattern_key": "k"}


def test_exec_approval_decline_does_not_send_the_text_fallback():
    from gateway.run_turn_runner import _ExecApprovalDeclined

    adapter = _Adapter(
        SendResult(success=False, error="declined", raw_response=CODE_ONLY_DECLINE)
    )
    runner = _runner(adapter)

    # Raises (not returns) so `_await_gateway_decision`'s notify-failure path
    # drops the CENTRAL approval entry and unblocks the waiting tool.
    with pytest.raises(_ExecApprovalDeclined):
        runner._approval_notify_sync(dict(APPROVAL))

    assert adapter.text_sends == []


def test_exec_approval_ORDINARY_failure_still_falls_back_to_text():
    """The control. An ordinary failure MUST still reach the user."""
    adapter = _Adapter(SendResult(success=False, error="slack 500"))
    runner = _runner(adapter)

    runner._approval_notify_sync(dict(APPROVAL))

    assert len(adapter.text_sends) == 1
    assert "rm -rf /" in adapter.text_sends[0]


# ── slash confirm ───────────────────────────────────────────────────────────


class _ConfirmAdapter:
    def __init__(self, result: SendResult) -> None:
        self._result = result

    async def send_slash_confirm(self, **k: Any) -> SendResult:
        return self._result


def _busy(adapter: _ConfirmAdapter):
    from gateway.run_busy import GatewayBusySessionMixin

    busy = object.__new__(GatewayBusySessionMixin)
    busy._delivery_adapter_for = lambda _s: adapter
    busy._thread_metadata_for_source = lambda _s, _a: {}
    busy._reply_anchor_for_event = lambda _e: None
    busy._session_key_for_source = lambda _s: "sk1"
    return busy


def _event():
    return SimpleNamespace(
        source=SimpleNamespace(chat_id="C1", platform="discord", user_id="u1")
    )


def _run_confirm(busy) -> Optional[str]:
    return asyncio.run(
        busy._request_slash_confirm(
            event=_event(),
            command="/wipe",
            title="Confirm",
            message="really wipe?",
            handler=lambda choice: "done",
        )
    )


def test_slash_confirm_decline_returns_none_and_clears_state():
    from tools import slash_confirm as mod

    adapter = _ConfirmAdapter(
        SendResult(success=False, error="declined", raw_response=CODE_ONLY_DECLINE)
    )
    reply = _run_confirm(_busy(adapter))

    # None = "no text ack": returning the message would post the prompt as
    # plain text into the chat the connector just refused.
    assert reply is None
    # And the registration must not survive a card that never rendered.
    assert mod.get_pending("sk1") in (None, {}, [])


def test_slash_confirm_ORDINARY_failure_returns_the_text_fallback():
    """The control. A broken card lane must still ask the user."""
    adapter = _ConfirmAdapter(SendResult(success=False, error="discord 500"))
    reply = _run_confirm(_busy(adapter))

    assert reply == "really wipe?"


# ── the edit lane (round 6): one dropped raw_response, three leaks ──────────


class _EditAdapter:
    """Records every op; the edit is refused with a code-only decline."""

    def __init__(self) -> None:
        self.ops: list[str] = []

    @staticmethod
    def extract_media(text):
        return [], text

    async def edit_message(self, **k: Any) -> SendResult:
        self.ops.append("edit")
        return SendResult(
            success=False, error="declined", raw_response=CODE_ONLY_DECLINE
        )

    async def send(self, *a: Any, **k: Any) -> SendResult:
        self.ops.append("send")
        return SendResult(success=True, message_id="m1")


def test_queued_reconcile_decline_does_not_fall_back_to_a_send():
    """R6-3: `_deliver_queued_first_response` re-sent the WHOLE response.

    Its reconcile-by-edit falls through to `adapter.send` on any failure, so a
    refused edit delivered the full text to the refused chat. Measured:
    [('edit', 'SECRET'), ('send', 'SECRET')].
    """
    from gateway.run_notifications import GatewayNotificationsMixin

    adapter = _EditAdapter()
    mixin = object.__new__(GatewayNotificationsMixin)
    source = SimpleNamespace(chat_id="C1", platform="discord")
    consumer = SimpleNamespace(message_id="m0", _turn_split_delivery=False)

    asyncio.run(
        mixin._deliver_queued_first_response(
            "SECRET", source, adapter, stream_consumer=consumer, deliver_media=False
        )
    )

    assert adapter.ops == ["edit"]


def test_queued_reconcile_ORDINARY_edit_failure_still_sends():
    """Control: a genuinely un-editable message must still be delivered."""
    from gateway.run_notifications import GatewayNotificationsMixin

    class _Ordinary(_EditAdapter):
        async def edit_message(self, **k: Any) -> SendResult:
            self.ops.append("edit")
            return SendResult(success=False, error="message too old")

    adapter = _Ordinary()
    mixin = object.__new__(GatewayNotificationsMixin)
    source = SimpleNamespace(chat_id="C1", platform="discord")
    consumer = SimpleNamespace(message_id="m0", _turn_split_delivery=False)

    asyncio.run(
        mixin._deliver_queued_first_response(
            "SECRET", source, adapter, stream_consumer=consumer, deliver_media=False
        )
    )

    assert adapter.ops == ["edit", "send"]
