"""A Deny-only approval request refuses any other choice in the backend, even when a tap is forged."""

import pytest

FENCED = "echo '```' " + "A" * 4000 + " && rm -rf ~ # TAIL"  # cannot be fenced verbatim -> Deny only


@pytest.fixture
def pending(monkeypatch):
    """A real queued approval for ``sk`` / ``r1`` in ``tools.approval``'s queue."""
    from tools import approval
    from tools.approval_gateway_wait import _ApprovalEntry

    entry = _ApprovalEntry({"request_id": "r1", "command": FENCED})
    monkeypatch.setitem(approval._gateway_queues, "sk", [entry])
    return entry


def test_a_forged_approve_tap_on_a_deny_only_request_resolves_nothing(pending):
    """Backend half: a card choice the card never offered (hand-added ✅ reaction, replayed callback data)
    cannot resolve a Deny-only request; Deny still can."""
    from tools.approval import resolve_gateway_approval_card, restrict_gateway_approval_card_to_deny

    restrict_gateway_approval_card_to_deny("sk", "r1")
    assert resolve_gateway_approval_card("sk", "once", "r1") == 0
    assert resolve_gateway_approval_card("sk", "always", "r1") == 0
    assert not pending.event.is_set()
    assert resolve_gateway_approval_card("sk", "deny", "r1") == 1
    assert pending.result == "deny"
