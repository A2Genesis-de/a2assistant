"""Cron thread-seed must key EXACTLY like the reply that will continue it.

The continuable cron thread seed must create its session row with the chat_type the adapter
puts on an in-thread reply (``_THREAD_REPLY_CHAT_TYPE``; DM threads key on ``dm``), or the
user's reply resolves to a session that never saw the brief.

Contract under test: the KEY of the seeded session equals the KEY the
user's in-thread reply will build. Asserting on build_session_key output —
not on SessionSource field shapes — pins the end-to-end contract.
"""

from unittest.mock import MagicMock, patch

from cron.scheduler_delivery import _seed_cron_thread_session
from gateway.config import Platform
from gateway.session import SessionSource, build_session_key


def _seeded_source(store):
    store.get_or_create_session.assert_called_once()
    return store.get_or_create_session.call_args[0][0]


def test_dm_thread_seed_key_matches_dm_reply_key():
    """A brief threaded under a Telegram DM must seed the same session row a
    DM in-thread reply resolves to (chat_type='dm', not 'thread')."""
    store = MagicMock()
    adapter = MagicMock()
    adapter._session_store = store

    with patch("gateway.mirror.mirror_to_session", return_value=True):
        _seed_cron_thread_session(
            {"id": "j1", "name": "digest"}, adapter, "telegram",
            "12345", "88", "Three bullets",
            chat_name=None, is_dm=True,
        )

    reply_source = SessionSource(
        platform=Platform.TELEGRAM,
        chat_id="12345",
        chat_type="dm",
        user_id="12345",
        thread_id="88",
    )
    assert build_session_key(_seeded_source(store)) == build_session_key(
        reply_source
    ), (
        "seeded key diverges from the DM reply's key — the brief lands in a "
        "row no reply ever resolves to (continuation amnesia)"
    )


def test_telegram_forum_topic_seed_key_matches_topic_reply_key():
    """The Telegram adapter types every supergroup message ``group`` (forum topics included), so a
    forum-topic cron seed typed ``thread`` is a row no topic reply ever resolves to."""
    store = MagicMock()
    adapter = MagicMock()
    adapter._session_store = store

    with patch("gateway.mirror.mirror_to_session", return_value=True):
        _seed_cron_thread_session(
            {"id": "j8", "name": "digest"}, adapter, "telegram",
            "-1001234567", "77", "Three bullets", chat_name="ops", is_dm=False,
        )

    reply_source = SessionSource(
        platform=Platform.TELEGRAM, chat_id="-1001234567", chat_type="group", user_id="42",
        thread_id="77",
    )
    assert build_session_key(_seeded_source(store)) == build_session_key(reply_source)
    assert build_session_key(_seeded_source(store)) == "agent:main:telegram:group:-1001234567:77"
