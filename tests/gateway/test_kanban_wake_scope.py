"""Kanban wake events must key to the same session as inbound messages.

The key built from the wake source byte-matches the key built from an inbound source for the same
conversation, and platforms without tenant scoping keep their exact key shape.
"""

import asyncio

from gateway.config import Platform
from gateway.kanban_watchers_notifier import _wake_scope_id
from gateway.run import GatewayRunner
from gateway.session import build_session_key
from hermes_cli import kanban_db as kb
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import kanban_db_notify as kbn

CHANNEL = "C0BCDG3H66P"


class UnscopedAdapter:
    """Push-capable adapter for a platform without tenant scoping."""

    def __init__(self):
        self.sent = []
        self.handled = []

    async def send(self, chat_id, text, metadata=None):
        self.sent.append({"chat_id": chat_id, "text": text, "metadata": metadata or {}})

    async def handle_message(self, event):
        self.handled.append(event)
        event._gateway_accepted = True


def _runner(adapter, platform):
    runner = GatewayRunner.__new__(GatewayRunner)
    runner._running = True
    runner.adapters = {platform: adapter}
    runner._kanban_sub_fail_counts = {}
    # A gateway whose dispatcher owns the singleton lock.
    runner._kanban_dispatcher_lock_handle = object()
    return runner


async def _one_notifier_tick(monkeypatch, runner):
    real_sleep = asyncio.sleep

    async def fake_sleep(delay):
        if delay == 5:
            return
        runner._running = False
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    await runner._kanban_notifier_watcher(interval=1)


def _completed_subscription(**sub_kwargs):
    conn = kbc.connect()
    try:
        tid = kb.create_task(
            conn,
            title="wake scope",
            assignee="worker",
            session_id="origin-session",
        )
        # Push-adapter wake injection is gated on the subscription's
        # delivery_mode ("notify+wake"/"wake") on current main; the plain
        # "notify" default would never reach the wake path under test.
        sub_kwargs.setdefault("delivery_mode", "notify+wake")
        kbn.add_notify_sub(conn, task_id=tid, **sub_kwargs)
        kb.complete_task(conn, tid, summary="done")
        return tid
    finally:
        conn.close()


def test_unscoped_platform_wake_key_is_byte_identical(tmp_path, monkeypatch):
    """Platforms without tenant scoping must keep their exact key shape."""
    monkeypatch.setenv("HERMES_KANBAN_DB", str(tmp_path / "wake-scope-telegram.db"))
    kb.init_db()
    _completed_subscription(
        platform="telegram",
        chat_id="chat-dm",
        chat_type="dm",
    )

    adapter = UnscopedAdapter()
    asyncio.run(_one_notifier_tick(monkeypatch, _runner(adapter, Platform.TELEGRAM)))

    assert len(adapter.handled) == 1
    wake = adapter.handled[0].source
    assert wake.scope_id is None
    assert build_session_key(wake) == "agent:main:telegram:dm:chat-dm"


def test_wake_scope_id_degrades_when_the_adapter_lookup_raises():
    class Exploding:
        def scope_id_for_chat(self, chat_id):
            raise RuntimeError("adapter state gone")

    assert _wake_scope_id(Exploding(), {"chat_id": CHANNEL}) is None
