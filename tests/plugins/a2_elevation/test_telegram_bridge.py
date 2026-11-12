"""Telegram approval channel: inline buttons in the home channel, only allowlisted users decide, the
message is edited to the final outcome, and no gateway binding means the channel is unavailable."""

import asyncio
import re
import sys
import threading
from types import ModuleType, SimpleNamespace

import pytest

from tests.plugins.a2_elevation.conftest import load

bridge_module = load("telegram_bridge")
approval = load("approval")
texts = load("texts")
Outcome = approval.Outcome

WAIT_LIMIT = 10.0
JOEL = "4242"


class FakeTransport(bridge_module.TelegramTransport):
    def __init__(self, usable=True, send_error=None):
        self._usable = usable
        self._send_error = send_error
        self.sent = []
        self.edits = []
        self.prompt_sent = threading.Event()

    def usable(self):
        return self._usable

    def send(self, text, buttons):
        if self._send_error is not None:
            raise self._send_error
        self.sent.append((text, buttons))
        self.prompt_sent.set()
        return bridge_module.SentPrompt(chat_id="-100", message_id=len(self.sent))

    def edit(self, prompt, text):
        self.edits.append((prompt, text))

    def callback_data(self, action):
        return next(data for _, data in self.sent[-1][1] if f":{action}:" in data)


def _request(needs_password=False, timeout_seconds=WAIT_LIMIT):
    return approval.ApprovalRequest(reason="Deploy auf a2-server", scope="protected", scope_label="Geschützt",
                                    needs_password=needs_password, timeout_seconds=timeout_seconds)


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def bridge(transport):
    bridge = bridge_module.TelegramBridge()
    bridge.bind(transport, frozenset({JOEL}))
    return bridge


def _ask_in_background(approver, request, stop=None):
    outcome = {}
    worker = threading.Thread(target=lambda: outcome.update(result=approver.ask(request, stop or threading.Event())))
    worker.start()
    return worker, outcome


@pytest.mark.parametrize(("action", "expected", "toast"), [
    ("approve", Outcome.APPROVED, "Freigegeben"), ("deny", Outcome.DENIED, "Abgelehnt"),
])
def test_button_tap_by_allowed_user_decides(bridge, transport, action, expected, toast):
    approver = bridge_module.TelegramApprover(bridge)
    worker, outcome = _ask_in_background(approver, _request())
    assert transport.prompt_sent.wait(WAIT_LIMIT)

    assert bridge.resolve(transport.callback_data(action), JOEL, "Joel") == toast
    worker.join(WAIT_LIMIT)

    result = outcome["result"]
    assert (result.outcome, result.channel, result.actor) == (expected, "telegram", "Joel")
    text, buttons = transport.sent[0]
    assert text.startswith(f"🔐 {texts.REQUEST_TITLE}: Deploy auf a2-server – gilt 10 Minuten")
    assert [label for label, _ in buttons] == ["Freigeben", "Ablehnen"]


def test_other_users_cannot_decide(bridge, transport):
    approver = bridge_module.TelegramApprover(bridge)
    stop = threading.Event()
    worker, outcome = _ask_in_background(approver, _request(), stop)
    assert transport.prompt_sent.wait(WAIT_LIMIT)

    assert bridge.resolve(transport.callback_data("approve"), "999", "Mallory") == texts.TOAST_UNAUTHORIZED
    assert bridge.resolve(transport.callback_data("approve"), "", "") == texts.TOAST_UNAUTHORIZED
    stop.set()
    worker.join(WAIT_LIMIT)

    assert outcome["result"].outcome is Outcome.SUPERSEDED


def test_wildcard_allowlist_never_grants(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", f"*, {JOEL} ,77")

    assert bridge_module.allowed_user_ids() == frozenset({JOEL, "77"})


def test_stale_or_forged_callbacks_are_ignored(bridge, transport):
    assert bridge.resolve("a2el:approve:0123456789abcdef", JOEL, "Joel") == texts.TOAST_ALREADY_DECIDED
    assert bridge.resolve("a2el:grant:0123456789abcdef", JOEL, "Joel") == texts.TOAST_ALREADY_DECIDED
    assert bridge.resolve("ea:once:1", JOEL, "Joel") == texts.TOAST_ALREADY_DECIDED


def test_second_tap_finds_the_request_already_decided(bridge, transport):
    approver = bridge_module.TelegramApprover(bridge)
    worker, _ = _ask_in_background(approver, _request())
    assert transport.prompt_sent.wait(WAIT_LIMIT)
    data = transport.callback_data("approve")

    bridge.resolve(data, JOEL, "Joel")
    worker.join(WAIT_LIMIT)

    assert bridge.resolve(data, JOEL, "Joel") == texts.TOAST_ALREADY_DECIDED


def test_mac_winning_edits_the_telegram_message(bridge, transport):
    approver = bridge_module.TelegramApprover(bridge)
    request = _request()
    stop = threading.Event()
    worker, outcome = _ask_in_background(approver, request, stop)
    assert transport.prompt_sent.wait(WAIT_LIMIT)
    stop.set()
    worker.join(WAIT_LIMIT)

    approver.conclude(request, approval.ApprovalResult(Outcome.APPROVED, "mac"))

    assert outcome["result"].outcome is Outcome.SUPERSEDED
    (prompt, text), = transport.edits
    assert prompt.message_id == 1
    assert text == "✅ Freigegeben am Mac\n\nDeploy auf a2-server"
    assert bridge.resolve(transport.callback_data("approve"), JOEL, "Joel") == texts.TOAST_ALREADY_DECIDED


def test_unanswered_prompt_times_out_and_is_marked_expired(bridge, transport):
    approver = bridge_module.TelegramApprover(bridge)
    request = _request(timeout_seconds=0.1)

    result = approver.ask(request, threading.Event())
    approver.conclude(request, result)

    assert result.outcome is Outcome.TIMED_OUT
    assert transport.edits[0][1].startswith("⌛ Abgelaufen, keine Antwort über Telegram")


def test_telegram_decision_is_shown_with_its_actor(bridge, transport):
    approver = bridge_module.TelegramApprover(bridge)
    request = _request()
    worker, outcome = _ask_in_background(approver, request)
    assert transport.prompt_sent.wait(WAIT_LIMIT)
    bridge.resolve(transport.callback_data("deny"), JOEL, "Joel")
    worker.join(WAIT_LIMIT)

    approver.conclude(request, outcome["result"])

    assert transport.edits[0][1] == "❌ Abgelehnt über Telegram von Joel\n\nDeploy auf a2-server"


@pytest.mark.parametrize("make_bridge", [
    lambda: bridge_module.TelegramBridge(),
    lambda: _bound(FakeTransport(usable=False)),
    lambda: _bound(FakeTransport(send_error=RuntimeError("Forbidden: bot was blocked"))),
])
def test_unreachable_telegram_is_unavailable(make_bridge):
    approver = bridge_module.TelegramApprover(make_bridge())
    request = _request()

    result = approver.ask(request, threading.Event())
    approver.conclude(request, result)

    assert (result.outcome, result.channel) == (Outcome.UNAVAILABLE, "telegram")


def _bound(transport):
    bridge = bridge_module.TelegramBridge()
    bridge.bind(transport, frozenset({JOEL}))
    return bridge


def test_password_requests_never_go_to_telegram(bridge):
    approver = bridge_module.TelegramApprover(bridge)

    assert approver.supports(_request())
    assert not approver.supports(_request(needs_password=True))


class _Button:
    def __init__(self, text, callback_data=None):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


class _CallbackQueryHandler:
    def __init__(self, callback, pattern=None):
        self.callback = callback
        self.pattern = re.compile(pattern)


@pytest.fixture
def ptb(monkeypatch):
    telegram = ModuleType("telegram")
    telegram.InlineKeyboardButton = _Button
    telegram.InlineKeyboardMarkup = _Markup
    ext = ModuleType("telegram.ext")
    ext.CallbackQueryHandler = _CallbackQueryHandler
    monkeypatch.setitem(sys.modules, "telegram", telegram)
    monkeypatch.setitem(sys.modules, "telegram.ext", ext)


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, **kwargs):
        self.calls.append(("send", kwargs))
        return SimpleNamespace(chat_id=kwargs["chat_id"], message_id=7)

    async def edit_message_text(self, **kwargs):
        self.calls.append(("edit", kwargs))


class FakeApplication:
    def __init__(self):
        self.bot = FakeBot()
        self.handlers = []

    def add_handler(self, handler):
        self.handlers.append(handler)


def _adapter(chat_id="-1001", thread_id=None):
    home = SimpleNamespace(chat_id=chat_id, thread_id=thread_id) if chat_id else None
    return SimpleNamespace(config=SimpleNamespace(home_channel=home))


def _run_loop_in_thread():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    return loop, thread


def test_wiring_binds_the_home_channel_and_a_scoped_callback_handler(monkeypatch, ptb):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", JOEL)
    bridge = bridge_module.TelegramBridge()
    application = FakeApplication()
    loop, thread = _run_loop_in_thread()
    try:
        asyncio.run_coroutine_threadsafe(_wire(bridge, application), loop).result(WAIT_LIMIT)
        (handler,) = application.handlers
        assert handler.pattern.pattern == bridge_module.CALLBACK_PATTERN
        transport = bridge.transport
        assert transport.usable()

        prompt = transport.send("Freigabe?", [("Freigeben", "a2el:approve:0123456789abcdef")])
        transport.edit(prompt, "erledigt")

        (send_kind, send), (edit_kind, edit) = application.bot.calls
        assert (send_kind, send["chat_id"], send["message_thread_id"]) == ("send", "-1001", None)
        assert send["reply_markup"].inline_keyboard[0][0].callback_data == "a2el:approve:0123456789abcdef"
        assert (edit_kind, edit["message_id"], edit["text"], edit["reply_markup"]) == ("edit", 7, "erledigt", None)
        assert not asyncio.run_coroutine_threadsafe(_usable_on_loop(transport), loop).result(WAIT_LIMIT)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(WAIT_LIMIT)
        loop.close()


async def _wire(bridge, application):
    bridge_module.handler_factory(bridge)(application, _adapter())


async def _usable_on_loop(transport):
    return transport.usable()


def test_without_home_channel_nothing_is_bound(ptb):
    bridge = bridge_module.TelegramBridge()
    application = FakeApplication()

    asyncio.run(_wire_without_home(bridge, application))

    assert bridge.transport is None
    assert application.handlers == []


async def _wire_without_home(bridge, application):
    bridge_module.handler_factory(bridge)(application, _adapter(chat_id=None))


def test_callback_handler_answers_with_the_decision_toast(bridge, transport):
    approver = bridge_module.TelegramApprover(bridge)
    worker, outcome = _ask_in_background(approver, _request())
    assert transport.prompt_sent.wait(WAIT_LIMIT)
    answers = []

    async def answer(text=None):
        answers.append(text)

    query = SimpleNamespace(data=transport.callback_data("approve"), from_user=SimpleNamespace(id=int(JOEL), first_name="Joel"),
                            answer=answer)
    on_callback = bridge_module.callback_handler(bridge)
    asyncio.run(on_callback(SimpleNamespace(callback_query=query), None))
    worker.join(WAIT_LIMIT)

    assert answers == ["Freigegeben"]
    assert outcome["result"].outcome is Outcome.APPROVED

