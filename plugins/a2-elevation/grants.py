import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from .policy import SCOPE_ADMIN, SCOPE_PROTECTED

GRANT_SECONDS = 600

Clock = Callable[[], float]


@dataclass(frozen=True)
class Grant:
    scope: str
    reason: str
    granted_at: float
    expires_at: float
    channel: str = ""

    def covers(self, scope: str, now: float) -> bool:
        if self.expires_at <= now:
            return False
        return self.scope == SCOPE_ADMIN or scope == SCOPE_PROTECTED

    def seconds_left(self, now: float) -> int:
        return max(0, int(self.expires_at - now))


class GrantStore:
    def __init__(self, directory: Path, clock: Clock = time.time) -> None:
        self._directory = directory
        self._clock = clock

    @property
    def _grant_file(self) -> Path:
        return self._directory / "grant.json"

    @property
    def _audit_file(self) -> Path:
        return self._directory / "audit.jsonl"

    def now(self) -> float:
        return self._clock()

    def current(self) -> Grant | None:
        try:
            grant = Grant(**json.loads(self._grant_file.read_text(encoding="utf-8-sig")))
        except (OSError, ValueError, TypeError):
            return None
        if grant.expires_at <= self.now():
            self._grant_file.unlink(missing_ok=True)
            return None
        return grant

    def grant(self, scope: str, reason: str, *, channel: str, actor: str = "") -> Grant:
        now = self.now()
        grant = Grant(scope=scope, reason=reason, granted_at=now, expires_at=now + GRANT_SECONDS, channel=channel)
        self._ensure_directory()
        self._grant_file.write_text(json.dumps(asdict(grant)), encoding="utf-8")
        self._grant_file.chmod(0o600)
        self.audit("granted", scope, reason, channel=channel, actor=actor)
        return grant

    def revoke(self) -> Grant | None:
        grant = self.current()
        self._grant_file.unlink(missing_ok=True)
        if grant is not None:
            self.audit("revoked", grant.scope, grant.reason, channel="cli")
        return grant

    def audit(self, event: str, scope: str, reason: str, *, channel: str, actor: str = "") -> None:
        self._ensure_directory()
        entry = {
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(self.now())),
            "event": event,
            "scope": scope,
            "reason": reason,
            "channel": channel,
        }
        if actor:
            entry["actor"] = actor
        with self._audit_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._audit_file.chmod(0o600)

    def _ensure_directory(self) -> None:
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
