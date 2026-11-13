"""Platform admins answer another member's approval under the ``approvals.approvers: []`` opt-in.

Relay prompt answers honour ``allow_admin_from`` / ``group_allow_admin_from``
the same way the text ``/approve`` does, without ``require_admin_for_exec_approval`` turned on.
"""

from types import SimpleNamespace

import pytest

from gateway.config import GatewayConfig, Platform, PlatformConfig
from gateway.platforms.event import MessageEvent, MessageType
from gateway.session import SessionSource
from tests.gateway.test_approval_requester_binding import pending_from, write_approvers


@pytest.fixture(autouse=True)
def _clean_queues():
    from tools import approval as approval_mod

    approval_mod._gateway_queues.clear()
    yield
    approval_mod._gateway_queues.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize(("clicker", "allowed"), [("bob", True), ("carol", False)])
async def test_relay_admin_answers_like_the_text_approve(clicker, allowed, monkeypatch):
    import gateway.run as gateway_run
    from gateway.relay.adapter import RelayAdapter
    from tests.gateway.relay.stub_connector import StubConnector
    from tests.gateway.relay.test_relay_interactive import make_desc

    runner = SimpleNamespace(config=GatewayConfig(platforms={Platform.TELEGRAM: PlatformConfig(
        enabled=True, extra={"group_allow_admin_from": ["bob"]})}))
    monkeypatch.setattr(gateway_run, "_gateway_runner_ref", lambda: runner)
    write_approvers([])
    entry = pending_from("alice", "Alice", "sess-r")
    stub = StubConnector(make_desc())
    adapter = RelayAdapter(PlatformConfig(), make_desc(), transport=stub)
    await adapter.send_exec_approval("c1", "rm -rf build", "sess-r", request_id=entry.data["request_id"])
    event = MessageEvent(text="/once", message_type=MessageType.COMMAND, source=SessionSource(
        platform=Platform.TELEGRAM, chat_id="c1", chat_type="group", user_id=clicker),
        prompt_response={"prompt_id": stub.sent[-1]["prompt_id"], "option_id": "once"})

    assert await adapter._consume_prompt_response(event) is True

    assert entry.event.is_set() is allowed
