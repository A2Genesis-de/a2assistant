"""``approvals.approvers: []`` binds an approval to the member who asked, also in a Telegram observe-mode
group (whose session route has no user), never to the first of two members whose texts one turn merged,
and never to "anyone" when no requester could be recorded.
"""


import pytest

from gateway.config import GatewayConfig
from gateway.platforms.event import MessageType
from gateway.session import build_session_context, build_session_key
from gateway.session_context import _UNSET, _VAR_MAP
from tests.gateway.test_approval_requester_binding import DEFAULT, write_approvers
from tests.gateway.test_telegram_group_gating import _group_message, _make_adapter, _mention_entity


@pytest.fixture(autouse=True)
def _clean_state():
    from tools import approval as approval_mod

    approval_mod._gateway_queues.clear()
    yield
    approval_mod._gateway_queues.clear()
    for var in _VAR_MAP.values():
        var.set(_UNSET)


def _observed_event(adapter, uid, name, body):
    text = f"@hermes_bot {body}"
    msg = _group_message(text, from_user_id=uid, from_user_name=name, entities=[_mention_entity(text)])
    return adapter._apply_telegram_group_observe_attribution(adapter._build_message_event(msg, MessageType.TEXT))


def _approval_raised_in(event):
    """The approval the agent raises inside *event*'s turn, through the gateway's real session binding."""
    from gateway.run import GatewayRunner
    from tools import approval as approval_mod
    from tools.approval_gateway_wait import _ApprovalEntry

    key = build_session_key(event.source)
    runner = object.__new__(GatewayRunner)
    tokens = runner._set_session_env(build_session_context(event.source, GatewayConfig(), event=event))
    try:
        entry = _ApprovalEntry({"command": "rm -rf notes"})
    finally:
        runner._clear_session_env(tokens)
    approval_mod._gateway_queues.setdefault(key, []).append(entry)
    return key


def _observe_adapter():
    return _make_adapter(require_mention=True, allowed_chats=["-100"], group_allowed_chats=["-100"],
                         observe_unmentioned_group_messages=True)


@pytest.mark.asyncio
async def test_an_observed_group_approval_belongs_to_the_member_who_asked():
    from gateway.approval_actor import approval_refusal
    from tests.gateway.test_approval_requester_binding import _runner

    write_approvers([])
    adapter = _observe_adapter()
    key = _approval_raised_in(_observed_event(adapter, 111, "Alice Example", "delete my notes"))

    assert approval_refusal(key, "222") == "Alice Example"
    # A bare "yes" is a sender-less observed text turn, routed to /approve (run_busy): Bob's is
    # refused, Alice's answers.
    runner = _runner()
    bob, alice = _observed_event(adapter, 222, "Bob", "yes"), _observed_event(adapter, 111, "Alice Example", "yes")
    bob.text = alice.text = "/approve"
    assert await runner._handle_approve_command(bob) == "Only Alice Example can answer this approval."
    await runner._handle_approve_command(alice)
    from tools import approval as approval_mod
    assert not approval_mod._gateway_queues.get(key)


def test_an_approval_with_no_requester_is_answered_only_by_approvers_and_admins():
    """No requester recorded (a turn merged from two members) fails closed: never "anyone"."""
    from gateway.approval_actor import approval_refusal, refusal_text
    from gateway.platforms.base import merge_pending_message_event

    adapter = _observe_adapter()
    pending = {}
    merge_pending_message_event(pending, "k", _observed_event(adapter, 111, "Alice Example", "save my notes"))
    merge_pending_message_event(pending, "k", _observed_event(adapter, 222, "Bob", "delete my notes"), merge_text=True)
    write_approvers([])
    key = _approval_raised_in(pending["k"])

    for member in ("111", "222", "333"):
        refusal = approval_refusal(key, member)
        assert refusal and refusal_text(refusal) == "Only an admin or a listed approver can answer this approval."
    assert approval_refusal(key, "444", extra={"group_allow_admin_from": ["444"]}) is None
    from tools import approval as approval_mod
    for approvers, member in ((["333"], "333"), (DEFAULT, "222")):  # a listed approver; legacy: anyone
        approval_mod._gateway_queues.clear()
        write_approvers(approvers)
        assert approval_refusal(_approval_raised_in(pending["k"]), member) is None

    # One member's own follow-ups still merge into a turn bound to that member.
    same = {}
    merge_pending_message_event(same, "k", _observed_event(adapter, 111, "Alice Example", "save my notes"))
    merge_pending_message_event(same, "k", _observed_event(adapter, 111, "Alice Example", "and delete"), merge_text=True)
    approval_mod._gateway_queues.clear()
    write_approvers([])
    key = _approval_raised_in(same["k"])
    assert approval_refusal(key, "222") == "Alice Example" and approval_refusal(key, "111") is None
