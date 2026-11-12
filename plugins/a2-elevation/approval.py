import contextvars
import logging
import threading
import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 120.0


class Outcome(str, Enum):
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    SUPERSEDED = "superseded"


DECISIVE_OUTCOMES = frozenset({Outcome.APPROVED, Outcome.DENIED, Outcome.FAILED})


@dataclass(frozen=True)
class ApprovalRequest:
    reason: str
    scope: str
    scope_label: str
    needs_password: bool
    timeout_seconds: float = APPROVAL_TIMEOUT_SECONDS
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass(frozen=True)
class ApprovalResult:
    outcome: Outcome
    channel: str
    password: str = field(default="", repr=False)
    detail: str = ""
    actor: str = ""

    @property
    def decisive(self) -> bool:
        return self.outcome in DECISIVE_OUTCOMES


class Approver(ABC):
    channel: str

    def supports(self, request: ApprovalRequest) -> bool:
        return True

    @abstractmethod
    def ask(self, request: ApprovalRequest, stop: threading.Event) -> ApprovalResult:
        ...

    def conclude(self, request: ApprovalRequest, final: ApprovalResult) -> None:
        return None


class _Race:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.stop = threading.Event()
        self.winner: ApprovalResult | None = None

    def offer(self, result: ApprovalResult) -> None:
        if not result.decisive:
            return
        with self._lock:
            if self.winner is None:
                self.winner = result
                self.stop.set()


def _fallback(results: Sequence[ApprovalResult]) -> ApprovalResult:
    for result in results:
        if result.outcome is Outcome.TIMED_OUT:
            return result
    details = "; ".join(f"{result.channel}: {result.detail}" for result in results if result.detail)
    return ApprovalResult(Outcome.UNAVAILABLE, channel="none", detail=details)


class FirstAnswerApprover:
    def __init__(self, approvers: Sequence[Approver]) -> None:
        self._approvers = tuple(approvers)

    def ask(self, request: ApprovalRequest) -> ApprovalResult:
        candidates = [approver for approver in self._approvers if approver.supports(request)]
        if not candidates:
            return ApprovalResult(Outcome.UNAVAILABLE, channel="none")
        race = _Race()
        with ThreadPoolExecutor(max_workers=len(candidates), thread_name_prefix="a2-elevation") as pool:
            futures = [
                pool.submit(contextvars.copy_context().run, self._run, approver, request, race)
                for approver in candidates
            ]
            results = [future.result() for future in futures]
        final = race.winner or _fallback(results)
        for approver in candidates:
            self._conclude(approver, request, final)
        return final

    @staticmethod
    def _run(approver: Approver, request: ApprovalRequest, race: _Race) -> ApprovalResult:
        try:
            result = approver.ask(request, race.stop)
        except Exception as error:
            logger.warning("a2-elevation: %s approver failed", approver.channel, exc_info=True)
            result = ApprovalResult(Outcome.UNAVAILABLE, channel=approver.channel, detail=str(error))
        race.offer(result)
        return result

    @staticmethod
    def _conclude(approver: Approver, request: ApprovalRequest, final: ApprovalResult) -> None:
        try:
            approver.conclude(request, final)
        except Exception:
            logger.warning("a2-elevation: %s approver could not conclude", approver.channel, exc_info=True)
