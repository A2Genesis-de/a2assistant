"""A native approval card answers only the request it was rendered for.

Two approvals can share one chat session: the first card's request ends (timeout,
``/approve`` from another client) while a newer request is queued behind it. A press on
the first card must not resolve the newer request, which the user has not seen yet.
"""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.config import PlatformConfig

from tools import approval
from tools.approval_gateway_wait import _ApprovalEntry

SESSION = "agent:main:test:dm:1"


@pytest.fixture
def newer_request_pending():
    """Request ``req-old`` already settled; ``req-new`` is the one still waiting."""
    entry = _ApprovalEntry({"command": "rm -rf build", "request_id": "req-new"})
    with approval._lock:
        approval._gateway_queues[SESSION] = [entry]
    yield entry
    with approval._lock:
        approval._gateway_queues.pop(SESSION, None)


async def _press_telegram_card(request_id):
    from plugins.platforms.telegram.adapter import TelegramAdapter
    adapter = TelegramAdapter(PlatformConfig(enabled=True, token="t"))
    adapter._bot, adapter._app = AsyncMock(), MagicMock()
    adapter._bot.send_message = AsyncMock(return_value=SimpleNamespace(message_id=42))
    await adapter.send_exec_approval(chat_id="1", command="rm -rf build", session_key=SESSION, request_id=request_id)
    query = AsyncMock()
    query.data = f"ea:once:{next(iter(adapter._approval_state))}"
    query.message = SimpleNamespace(chat_id=1, chat=SimpleNamespace(type="private"))
    query.from_user = SimpleNamespace(id=1, first_name="Alice")
    with patch.dict(os.environ, {"TELEGRAM_ALLOWED_USERS": "*"}):
        await adapter._handle_callback_query(SimpleNamespace(callback_query=query), MagicMock())


async def _press_relay_card(request_id):
    from gateway.platforms.event import MessageEvent, MessageType
    from gateway.relay.adapter import RelayAdapter
    from gateway.relay.descriptor import CONTRACT_VERSION, CapabilityDescriptor
    from gateway.session import SessionSource
    from tests.gateway.relay.stub_connector import StubConnector
    desc = CapabilityDescriptor(
        contract_version=CONTRACT_VERSION, platform="telegram", label="Telegram", max_message_length=4096,
        supports_draft_streaming=False, supports_edit=True, supports_threads=True, markdown_dialect="markdown_v2",
        len_unit="utf16", supported_ops=("send", "edit", "typing", "get_chat_info", "send_media", "prompt", "react"))
    stub = StubConnector(desc)
    adapter = RelayAdapter(PlatformConfig(), desc, transport=stub)
    await adapter.send_exec_approval("c1", "rm -rf build", SESSION, request_id=request_id)
    await adapter._consume_prompt_response(MessageEvent(
        text="/once", message_type=MessageType.COMMAND,
        source=SessionSource(platform="telegram", chat_id="c1", chat_type="dm", user_id="u1"),
        prompt_response={"prompt_id": stub.sent[-1]["prompt_id"], "option_id": "once"}))


_PRESSES = [_press_telegram_card, _press_relay_card]


@pytest.mark.asyncio
@pytest.mark.parametrize("press", _PRESSES)
async def test_settled_card_does_not_resolve_the_next_request(newer_request_pending, press):
    await press("req-old")

    assert not newer_request_pending.event.is_set()
    assert approval._gateway_queues[SESSION] == [newer_request_pending]


@pytest.mark.asyncio
@pytest.mark.parametrize("press", _PRESSES)
async def test_card_resolves_its_own_request(newer_request_pending, press):
    pressed = await press("req-new") or "once"

    assert newer_request_pending.event.is_set()
    assert newer_request_pending.result == pressed

