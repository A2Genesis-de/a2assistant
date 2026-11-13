"""Cron origin capture keeps the session's thread: Telegram forum topics and DM topics deliver back
into the topic the job was created from."""

import json
from unittest.mock import patch

from tools.cronjob_tools import _origin_from_env


def _session_env(env: dict):
    """Patch gateway.session_context.get_session_env with a dict lookup."""
    return patch(
        "gateway.session_context.get_session_env",
        side_effect=lambda name, default="": env.get(name, default),
    )


_TOPIC = {
    "HERMES_SESSION_PLATFORM": "telegram",
    "HERMES_SESSION_CHAT_ID": "-1003941067111",
    "HERMES_SESSION_THREAD_ID": "2203",
    "HERMES_SESSION_MESSAGE_ID": "2203",
}


def test_topic_thread_is_captured():
    with _session_env(_TOPIC):
        origin = _origin_from_env()
    assert origin is not None
    assert origin["platform"] == "telegram"
    assert origin["chat_id"] == "-1003941067111"
    assert origin["thread_id"] == "2203"


def test_no_thread_captures_none():
    env = {k: v for k, v in _TOPIC.items() if k != "HERMES_SESSION_THREAD_ID"}
    with _session_env(env):
        origin = _origin_from_env()
    assert origin is not None
    assert origin["thread_id"] is None


def test_create_handler_stores_the_topic_thread(tmp_path, monkeypatch, make_cron_provider):
    from cron import jobs
    from tools import cronjob_tools

    provider = make_cron_provider()
    monkeypatch.setattr("cron.scheduler_provider.resolve_cron_scheduler", lambda: provider)
    with jobs.use_cron_store(tmp_path / "cron"), _session_env(_TOPIC):
        result = json.loads(cronjob_tools.registry.dispatch("cronjob_manage", {
            "action": "create", "schedule": "every 2h", "prompt": "remind me"}))
        assert result["success"], result
        stored = jobs.get_job(result["job_id"])
    assert stored["origin"]["thread_id"] == "2203"
