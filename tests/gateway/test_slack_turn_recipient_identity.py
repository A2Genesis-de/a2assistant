"""Per-turn Slack egress identity: _thread_metadata_for_source stamps the authentic per-turn
recipient identity from the turn's OWN source, so two users with overlapping turns in one channel
never share a stream recipient."""

from types import SimpleNamespace

from gateway.platforms.base import Platform
from gateway.run import GatewayRunner


def _slack_source(user_id: str, chat_id: str = "C_SHARED") -> SimpleNamespace:
    return SimpleNamespace(
        platform=Platform.SLACK,
        chat_id=chat_id,
        thread_id="1700.100",
        chat_type="channel",
        message_id="1700.100",
        scope_id="T_TEAM",
        user_id=user_id,
    )


def test_thread_metadata_stamps_per_turn_user_and_scope():
    runner = object.__new__(GatewayRunner)
    meta = runner._thread_metadata_for_source(_slack_source("U_ALICE"))
    assert meta is not None
    assert meta["user_id"] == "U_ALICE"
    assert meta["scope_id"] == "T_TEAM"
    assert meta["slack_team_id"] == "T_TEAM"


def test_concurrent_turns_carry_their_own_identity():
    """The R3-5 interleaving: U2's turn starting must not change what U1's
    already-built metadata carries — identity is per-turn source data, not
    shared per-chat state."""
    runner = object.__new__(GatewayRunner)
    meta_alice = runner._thread_metadata_for_source(_slack_source("U_ALICE"))
    # U2's turn begins in the SAME channel before U1's stream opens.
    meta_bob = runner._thread_metadata_for_source(_slack_source("U_BOB"))
    assert meta_alice is not None and meta_bob is not None
    assert meta_alice["user_id"] == "U_ALICE"
    assert meta_bob["user_id"] == "U_BOB"


