import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from hermes_constants import get_hermes_home

from .policy import SCOPE_ADMIN, SCOPE_PROTECTED

GRANT_SECONDS = 600


@dataclass(frozen=True)
class Grant:
    scope: str
    reason: str
    granted_at: float
    expires_at: float

    def covers(self, scope: str, now: float) -> bool:
        if self.expires_at <= now:
            return False
        return self.scope == SCOPE_ADMIN or scope == SCOPE_PROTECTED

    def seconds_left(self, now: float) -> int:
        return max(0, int(self.expires_at - now))


class GrantStore:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory or get_hermes_home() / "elevation"

    @property
    def _grant_file(self) -> Path:
        return self._directory / "grant.json"

    @property
    def _audit_file(self) -> Path:
        return self._directory / "audit.jsonl"

    def current(self) -> Grant | None:
        try:
            grant = Grant(**json.loads(self._grant_file.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return None
        if grant.expires_at <= time.time():
            self._grant_file.unlink(missing_ok=True)
            return None
        return grant

    def grant(self, scope: str, reason: str) -> Grant:
        now = time.time()
        grant = Grant(scope=scope, reason=reason, granted_at=now, expires_at=now + GRANT_SECONDS)
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._grant_file.write_text(json.dumps(asdict(grant)), encoding="utf-8")
        self._grant_file.chmod(0o600)
        self.audit("granted", scope, reason)
        return grant

    def audit(self, event: str, scope: str, reason: str) -> None:
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        entry = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, "scope": scope, "reason": reason}
        with self._audit_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
