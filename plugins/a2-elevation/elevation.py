import logging
from collections.abc import Callable
from typing import Any

from . import texts
from .approval import ApprovalRequest, FirstAnswerApprover, Outcome
from .grants import GRANT_SECONDS, GrantStore
from .policy import SCOPE_ADMIN, ProtectedRule, required_scope

logger = logging.getLogger(__name__)

SudoGranter = Callable[[str, float], None]


class InvalidRequest(ValueError):
    pass


class ElevationService:
    def __init__(self, store: GrantStore, approver: FirstAnswerApprover, grant_sudo: SudoGranter) -> None:
        self._store = store
        self._approver = approver
        self._grant_sudo = grant_sudo

    def blocking_rule(self, tool_name: str, args: Any) -> ProtectedRule | None:
        rule = required_scope(tool_name, args)
        if rule is None:
            return None
        grant = self._store.current()
        if grant is not None and grant.covers(rule.scope, self._store.now()):
            return None
        return rule

    def request(self, reason: str, scope: str) -> dict[str, Any]:
        reason = reason.strip()
        if scope not in texts.SCOPE_LABELS:
            raise InvalidRequest(f"scope must be one of {sorted(texts.SCOPE_LABELS)}")
        if not reason:
            raise InvalidRequest("reason is required")
        existing = self._store.current()
        if existing is not None and existing.covers(scope, self._store.now()):
            return {"status": "already_granted", "scope": existing.scope,
                    "seconds_left": existing.seconds_left(self._store.now())}
        result = self._approver.ask(ApprovalRequest(
            reason=reason, scope=scope, scope_label=texts.SCOPE_LABELS[scope], needs_password=scope == SCOPE_ADMIN,
        ))
        if result.outcome is not Outcome.APPROVED:
            self._store.audit(result.outcome.value, scope, reason, channel=result.channel, actor=result.actor)
            if result.detail:
                logger.warning("a2-elevation %s: %s", result.channel, result.detail)
            return {"status": result.outcome.value, "channel": result.channel,
                    "message": texts.AGENT_MESSAGES.get(result.outcome, texts.AGENT_MESSAGES[Outcome.UNAVAILABLE])}
        grant = self._store.grant(scope, reason, channel=result.channel, actor=result.actor)
        if scope == SCOPE_ADMIN:
            self._grant_sudo(result.password, GRANT_SECONDS)
        return {"status": "granted", "scope": grant.scope, "channel": result.channel, "seconds_left": GRANT_SECONDS}

    def status(self) -> dict[str, Any]:
        grant = self._store.current()
        if grant is None:
            return {"active": False}
        return {"active": True, "scope": grant.scope, "reason": grant.reason, "channel": grant.channel,
                "seconds_left": grant.seconds_left(self._store.now())}

    def revoke(self) -> bool:
        grant = self._store.revoke()
        if grant is not None and grant.scope == SCOPE_ADMIN:
            self._grant_sudo("", 0)
        return grant is not None
