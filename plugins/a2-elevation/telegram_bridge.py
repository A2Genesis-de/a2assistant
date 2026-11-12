import asyncio
import logging
import re
import secrets
import threading
from abc import ABC, abstractmethod
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any

from gateway.platforms._shared import platform_gate_env

from . import texts
from .approval import ApprovalRequest, ApprovalResult, Approver, Outcome

logger = logging.getLogger(__name__)

CALLBACK_PREFIX = "a2el"
CALLBACK_PATTERN = rf"^{CALLBACK_PREFIX}:(approve|deny):[0-9a-f]{{16}}$"
_CALLBACK_RE = re.compile(CALLBACK_PATTERN)
SEND_TIMEOUT_SECONDS = 15.0
POLL_SECONDS = 0.25


@dataclass(frozen=True)
class SentPrompt:
    chat_id: str
    message_id: int


@dataclass(frozen=True)
class TelegramAnswer:
    approved: bool
    actor: str


class TelegramTransport(ABC):
    @abstractmethod
    def usable(self) -> bool:
        ...

    @abstractmethod
    def send(self, text: str, buttons: list[tuple[str, str]]) -> SentPrompt:
        ...

    @abstractmethod
    def edit(self, prompt: SentPrompt, text: str) -> None:
        ...


class PtbTransport(TelegramTransport):
    def __init__(self, bot: Any, loop: asyncio.AbstractEventLoop, chat_id: str, thread_id: str | None) -> None:
        self._bot = bot
        self._loop = loop
        self._chat_id = chat_id
        self._thread_id = int(thread_id) if thread_id else None

    def usable(self) -> bool:
        if not self._loop.is_running() or self._loop.is_closed():
            return False
        try:
            return asyncio.get_running_loop() is not self._loop
        except RuntimeError:
            return True

    def send(self, text: str, buttons: list[tuple[str, str]]) -> SentPrompt:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        markup = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=data) for label, data in buttons]])
        message = self._call(self._bot.send_message(
            chat_id=self._chat_id, text=text, reply_markup=markup, message_thread_id=self._thread_id,
        ))
        return SentPrompt(chat_id=str(message.chat_id), message_id=int(message.message_id))

    def edit(self, prompt: SentPrompt, text: str) -> None:
        self._call(self._bot.edit_message_text(
            chat_id=prompt.chat_id, message_id=prompt.message_id, text=text, reply_markup=None,
        ))

    def _call(self, coroutine: Any) -> Any:
        return asyncio.run_coroutine_threadsafe(coroutine, self._loop).result(SEND_TIMEOUT_SECONDS)


def allowed_user_ids() -> frozenset[str]:
    raw = platform_gate_env("TELEGRAM_ALLOWED_USERS")
    return frozenset(item.strip() for item in raw.split(",") if item.strip() and item.strip() != "*")


class TelegramBridge:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._transport: TelegramTransport | None = None
        self._allowed: frozenset[str] = frozenset()
        self._pending: dict[str, Future] = {}

    @property
    def transport(self) -> TelegramTransport | None:
        return self._transport

    def bind(self, transport: TelegramTransport, allowed: frozenset[str]) -> None:
        with self._lock:
            self._transport = transport
            self._allowed = allowed

    def open(self, token: str) -> Future:
        decision: Future = Future()
        with self._lock:
            self._pending[token] = decision
        return decision

    def close(self, token: str) -> None:
        with self._lock:
            self._pending.pop(token, None)

    def resolve(self, data: str, user_id: str, actor: str) -> str:
        match = _CALLBACK_RE.match(data or "")
        if match is None:
            return texts.TOAST_ALREADY_DECIDED
        with self._lock:
            if str(user_id) not in self._allowed:
                return texts.TOAST_UNAUTHORIZED
            decision = self._pending.pop(data.rsplit(":", 1)[1], None)
        if decision is None:
            return texts.TOAST_ALREADY_DECIDED
        approved = match.group(1) == "approve"
        decision.set_result(TelegramAnswer(approved=approved, actor=actor))
        return texts.TOAST_APPROVED if approved else texts.TOAST_DENIED


class TelegramApprover(Approver):
    channel = "telegram"

    def __init__(self, bridge: TelegramBridge) -> None:
        self._bridge = bridge
        self._prompts: dict[str, SentPrompt] = {}

    def supports(self, request: ApprovalRequest) -> bool:
        return not request.needs_password

    def ask(self, request: ApprovalRequest, stop: threading.Event) -> ApprovalResult:
        transport = self._bridge.transport
        if transport is None or not transport.usable():
            return ApprovalResult(Outcome.UNAVAILABLE, self.channel, detail="telegram gateway not bound")
        token = secrets.token_hex(8)
        decision = self._bridge.open(token)
        try:
            self._prompts[request.request_id] = transport.send(texts.telegram_prompt(request), [
                (texts.APPROVE_LABEL, f"{CALLBACK_PREFIX}:approve:{token}"),
                (texts.DENY_LABEL, f"{CALLBACK_PREFIX}:deny:{token}"),
            ])
            return self._await(decision, request, stop)
        except Exception as error:  # health: allow BLE001 -- any send failure falls back to the Mac dialog; tracebacks may carry the bot token
            logger.warning("a2-elevation: telegram prompt failed: %s", type(error).__name__)
            return ApprovalResult(Outcome.UNAVAILABLE, self.channel, detail=type(error).__name__)
        finally:
            self._bridge.close(token)

    def _await(self, decision: Future, request: ApprovalRequest, stop: threading.Event) -> ApprovalResult:
        waited = 0.0
        while not stop.is_set() and waited < request.timeout_seconds:
            try:
                answer = decision.result(timeout=POLL_SECONDS)
            except FutureTimeout:
                waited += POLL_SECONDS
                continue
            outcome = Outcome.APPROVED if answer.approved else Outcome.DENIED
            return ApprovalResult(outcome, self.channel, actor=answer.actor)
        return ApprovalResult(Outcome.SUPERSEDED if stop.is_set() else Outcome.TIMED_OUT, self.channel)

    def conclude(self, request: ApprovalRequest, final: ApprovalResult) -> None:
        prompt = self._prompts.pop(request.request_id, None)
        transport = self._bridge.transport
        if prompt is not None and transport is not None:
            transport.edit(prompt, texts.telegram_outcome(request, final))


def callback_handler(bridge: TelegramBridge):
    async def on_callback(update: Any, _context: Any) -> None:
        query = update.callback_query
        user = query.from_user
        toast = bridge.resolve(query.data or "", str(getattr(user, "id", "")), getattr(user, "first_name", "") or "")
        await query.answer(text=toast)

    return on_callback


def handler_factory(bridge: TelegramBridge):
    on_callback = callback_handler(bridge)

    def wire_elevation_buttons(native: Any, adapter: Any) -> None:
        from telegram.ext import CallbackQueryHandler

        home = getattr(getattr(adapter, "config", None), "home_channel", None)
        if home is None or not home.chat_id:
            logger.info("a2-elevation: no Telegram home channel, approvals stay on the Mac")
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("a2-elevation: Telegram handlers wired outside the gateway loop, not binding")
            return
        bridge.bind(PtbTransport(native.bot, loop, str(home.chat_id), home.thread_id), allowed_user_ids())
        native.add_handler(CallbackQueryHandler(on_callback, pattern=CALLBACK_PATTERN))

    return wire_elevation_buttons
